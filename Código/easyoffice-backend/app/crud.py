"""Lógica de negocio del módulo: crear solicitud, convertirla a trámite
(generando el código de 8 caracteres) y consultar un trámite por código.
"""
import secrets

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas

ESTADOS_DOCUMENTO_DISPONIBLE = {"firmado", "entregado"}


def servicio_existe(db: Session, id_servicio: int) -> bool:
    return db.get(models.ServicioContratado, id_servicio) is not None


def usuario_existe(db: Session, id_usuario: int) -> bool:
    return db.get(models.Usuario, id_usuario) is not None


def crear_solicitud(db: Session, datos: schemas.SolicitudContactoCreate) -> models.SolicitudContacto:
    solicitud = models.SolicitudContacto(
        nombre=datos.nombre,
        rut=datos.rut,
        email=datos.email,
        telefono=datos.telefono,
        id_servicio=datos.servicio_id,
        mensaje=datos.mensaje,
        estado="pendiente",
    )
    db.add(solicitud)
    db.commit()
    db.refresh(solicitud)
    return solicitud


def obtener_solicitud(db: Session, id_solicitud: int) -> models.SolicitudContacto | None:
    return db.get(models.SolicitudContacto, id_solicitud)


def listar_solicitudes(
    db: Session,
    estado: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[schemas.SolicitudListadoOut]:
    """Solicitudes de contacto, las más recientes primero. Para cada una ya
    convertida incluye el código de seguimiento de su trámite."""
    consulta = db.query(models.SolicitudContacto)
    if estado:
        consulta = consulta.filter(models.SolicitudContacto.estado == estado)
    # id_solicitud como desempate: fecha_creacion tiene resolución de segundos.
    solicitudes = (
        consulta.order_by(
            models.SolicitudContacto.fecha_creacion.desc(),
            models.SolicitudContacto.id_solicitud.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Una sola consulta extra para todos los códigos (evita N+1).
    ids_tramite = [s.id_tramite_generado for s in solicitudes if s.id_tramite_generado]
    codigos: dict[int, str] = {}
    if ids_tramite:
        filas = (
            db.query(models.Tramite.id_tramite, models.Tramite.codigo_seguimiento)
            .filter(models.Tramite.id_tramite.in_(ids_tramite))
            .all()
        )
        codigos = {fila.id_tramite: fila.codigo_seguimiento for fila in filas}

    return [
        schemas.SolicitudListadoOut(
            id_solicitud=s.id_solicitud,
            nombre=s.nombre,
            rut=s.rut,
            email=s.email,
            telefono=s.telefono,
            mensaje=s.mensaje,
            estado=s.estado,
            id_servicio=s.id_servicio,
            nombre_servicio=s.servicio.nombre if s.servicio else None,
            id_tramite_generado=s.id_tramite_generado,
            codigo_seguimiento=codigos.get(s.id_tramite_generado),
            fecha_creacion=s.fecha_creacion,
        )
        for s in solicitudes
    ]


def contar_novedades(db: Session, desde_id: int | None = None) -> schemas.NovedadesSolicitudesOut:
    """Para el aviso "N solicitudes nuevas" del panel (consulta periódica).
    No devuelve datos de las solicitudes, solo números: el id más alto que existe
    y cuántas hay con id mayor a `desde_id`. Sin `desde_id` (primera consulta
    del panel) solo se informa el id más alto, que el panel guarda como punto
    de partida. Cuenta sobre toda la tabla, sin depender del filtro ni de la
    página que el agente esté viendo."""
    ultimo_id = db.query(func.max(models.SolicitudContacto.id_solicitud)).scalar() or 0
    nuevas = 0
    if desde_id is not None:
        nuevas = (
            db.query(func.count(models.SolicitudContacto.id_solicitud))
            .filter(models.SolicitudContacto.id_solicitud > desde_id)
            .scalar()
        )
    return schemas.NovedadesSolicitudesOut(nuevas=nuevas, ultimo_id=ultimo_id)


# Alfabeto del código de seguimiento: 31 caracteres, sin 0/O/1/I/L para que no se confundan al dictarlos por teléfono o 
# copiarlos desde un mensaje.
ALFABETO_CODIGO = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
LARGO_CODIGO = 8


def _generar_codigo() -> str:
    """Un código aleatorio (sin verificar unicidad). Usa `secrets` porque el
    código es la única credencial del cliente para ver su trámite."""
    return "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(LARGO_CODIGO))

def _generar_codigo_unico(db: Session) -> str:
    for _ in range(20):
        codigo = _generar_codigo()
        existe = db.query(models.Tramite).filter_by(codigo_seguimiento=codigo).first()
        if not existe:
            return codigo
    # Extremadamente improbable con 31^8 combinaciones, pero no lo dejamos colgado.
    raise RuntimeError("No se pudo generar un código de seguimiento único. Intenta nuevamente.")

def convertir_solicitud_a_tramite(
    db: Session,
    solicitud: models.SolicitudContacto,
    id_usuario_responsable: int | None,
) -> models.Tramite:
    """Confirma el pago manual de una solicitud y la convierte en un trámite real,
    generando su código de seguimiento. Acción exclusiva de un agente/admin."""

    if solicitud.estado == "convertido":
        raise ValueError("Esta solicitud ya fue convertida en un trámite.")
    if not solicitud.id_servicio:
        raise ValueError("La solicitud no tiene un servicio definido; no se puede convertir.")
    if id_usuario_responsable is not None and not usuario_existe(db, id_usuario_responsable):
        raise ValueError(f"El usuario responsable {id_usuario_responsable} no existe.")

    # El cliente no tiene cuenta; se busca o se crea por RUT (ya normalizado por
    # el schema al crear la solicitud) para no duplicarlo si ya había hecho una
    # solicitud antes.
    cliente = None
    if solicitud.rut:
        cliente = db.query(models.Cliente).filter_by(rut=solicitud.rut).first()
    if not cliente:
        cliente = models.Cliente(
            nombre=solicitud.nombre,
            rut=solicitud.rut,
            email=solicitud.email,
            telefono=solicitud.telefono,
        )
        db.add(cliente)
        db.flush()  # para obtener id_cliente sin cerrar la transacción

    tramite = models.Tramite(
        id_cliente=cliente.id_cliente,
        id_servicio=solicitud.id_servicio,
        id_usuario_responsable=id_usuario_responsable,
        id_solicitud_origen=solicitud.id_solicitud,
        codigo_seguimiento=_generar_codigo_unico(db),
        estado_actual="generado",
    )
    db.add(tramite)
    db.flush()

    db.add(models.HistorialEstado(
        id_tramite=tramite.id_tramite,
        estado="generado",
        comentario="Trámite generado al confirmar el pago de la solicitud de contacto.",
        id_usuario=id_usuario_responsable,
    ))

    solicitud.estado = "convertido"
    solicitud.id_tramite_generado = tramite.id_tramite

    db.commit()
    db.refresh(tramite)
    return tramite


def obtener_tramite_por_codigo(db: Session, codigo: str) -> models.Tramite | None:
    return (
        db.query(models.Tramite)
        .filter(models.Tramite.codigo_seguimiento == codigo.strip().upper())
        .first()
    )


def documento_disponible(tramite: models.Tramite) -> bool:
    return tramite.estado_actual in ESTADOS_DOCUMENTO_DISPONIBLE