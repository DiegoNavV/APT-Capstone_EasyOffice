"""Lógica de negocio del módulo: crear solicitud, convertirla a trámite
(generando el código de 8 caracteres) y consultar un trámite por código.
"""
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, contains_eager, joinedload

from app import models, schemas
from app.utils import normalizar_rut

ESTADOS_DOCUMENTO_DISPONIBLE = {"firmado", "entregado"}

# Agrupación de estados para los KPIs del panel de trámites.
ESTADOS_PENDIENTES_DATOS = ("generado",)
ESTADOS_EN_PROCESO = ("procesando_firma", "en_revision")


def servicio_existe(db: Session, id_servicio: int) -> bool:
    return db.get(models.ServicioContratado, id_servicio) is not None


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
    id_usuario_responsable: int,
) -> models.Tramite:
    """Confirma el pago manual de una solicitud y la convierte en un trámite real, generando su código de seguimiento. 
    Acción exclusiva de un agente/admin: el responsable es siempre quien la ejecuta (lo valida get_usuario_actual en el router, por eso 
    aquí no se vuelve a comprobar que exista)."""

    if solicitud.estado == "convertido":
        raise ValueError("Esta solicitud ya fue convertida en un trámite.")
    if not solicitud.id_servicio:
        raise ValueError("La solicitud no tiene un servicio definido; no se puede convertir.")

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


# ---------------------------------------------------------------------------
# Listado de trámites del panel (agentes y administradores)
# ---------------------------------------------------------------------------

def _datos_cliente_listado(tramite: models.Tramite) -> schemas.ClienteListadoOut:
    """ÚNICO lugar que decide qué "cliente" se muestra en el listado.

    Hoy: los datos de contacto de quien pidió el trámite, con `datos_pendientes=True` porque la empresa aún no completa sus datos.
    Cuando exista el formulario posterior al código, aquí se devolverán la razón social y el RUT de la empresa (y `datos_pendientes=False`). 
    El filtro de búsqueda (`_filtro_busqueda`) debe actualizarse junto con esta función."""
    cliente = tramite.cliente
    return schemas.ClienteListadoOut(
        nombre=cliente.nombre,
        rut=cliente.rut,
        datos_pendientes=True,
    )


def _escapar_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _filtro_busqueda(texto: str):
    """Coincidencia parcial por nombre o RUT del cliente, o por código del
    trámite. El RUT se compara tal como se guarda (sin puntos, DV en mayúscula)."""
    patron = f"%{_escapar_like(texto.strip())}%"
    patron_rut = f"%{_escapar_like(normalizar_rut(texto) or texto.strip())}%"
    return or_(
        models.Cliente.nombre.ilike(patron, escape="\\"),
        models.Cliente.rut.ilike(patron_rut, escape="\\"),
        models.Tramite.codigo_seguimiento.ilike(patron, escape="\\"),
    )


def listar_tramites(
    db: Session,
    servicio_id: int | None = None,
    estado: str | None = None,
    agente_id: int | None = None,
    q: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> schemas.TramitesPaginaOut:
    """Trámites con filtros opcionales, los más recientemente actualizados
    primero. `total` cuenta todos los que cumplen los filtros (para paginar)."""
    base = db.query(models.Tramite).join(models.Tramite.cliente)
    if servicio_id is not None:
        base = base.filter(models.Tramite.id_servicio == servicio_id)
    if estado:
        base = base.filter(models.Tramite.estado_actual == estado)
    if agente_id is not None:
        base = base.filter(models.Tramite.id_usuario_responsable == agente_id)
    if q and q.strip():
        base = base.filter(_filtro_busqueda(q))

    total = base.count()
    tramites = (
        base.options(
            contains_eager(models.Tramite.cliente),
            joinedload(models.Tramite.servicio),
            joinedload(models.Tramite.usuario_responsable),
        )
        # id_tramite como desempate: la fecha tiene resolución de segundos.
        .order_by(models.Tramite.fecha_actualizacion.desc(), models.Tramite.id_tramite.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return schemas.TramitesPaginaOut(
        total=total,
        items=[
            schemas.TramiteListadoOut(
                id_tramite=t.id_tramite,
                codigo_seguimiento=t.codigo_seguimiento,
                cliente=_datos_cliente_listado(t),
                id_servicio=t.id_servicio,
                nombre_servicio=t.servicio.nombre,
                estado_actual=t.estado_actual,
                id_usuario_responsable=t.id_usuario_responsable,
                nombre_agente=t.usuario_responsable.nombre if t.usuario_responsable else None,
                fecha_actualizacion=t.fecha_actualizacion,
            )
            for t in tramites
        ],
    )


def _contar_tramites_en(db: Session, estados: tuple[str, ...]) -> int:
    return (
        db.query(func.count(models.Tramite.id_tramite))
        .filter(models.Tramite.estado_actual.in_(estados))
        .scalar()
    )


def resumen_tramites(db: Session) -> schemas.TramitesResumenOut:
    """KPIs del panel y opciones de los filtros (servicios y agentes activos)."""
    # "Firmados" = trámites que pasaron a ese estado en las últimas 24 horas,
    # según el historial. Las fechas de la base son UTC (sin zona), igual que
    # `desde`. Se evita "hoy" calendario para no depender de la zona horaria.
    desde = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
    firmados_24h = (
        db.query(func.count(func.distinct(models.HistorialEstado.id_tramite)))
        .filter(
            models.HistorialEstado.estado == "firmado",
            models.HistorialEstado.fecha >= desde,
        )
        .scalar()
    )

    servicios = (
        db.query(models.ServicioContratado)
        .filter(models.ServicioContratado.activo.is_(True))
        .order_by(models.ServicioContratado.id_servicio)
        .all()
    )
    agentes = (
        db.query(models.Usuario)
        .filter(models.Usuario.activo.is_(True))
        .order_by(models.Usuario.nombre, models.Usuario.id_usuario)
        .all()
    )

    return schemas.TramitesResumenOut(
        kpis=schemas.TramitesKpisOut(
            pendientes_datos=_contar_tramites_en(db, ESTADOS_PENDIENTES_DATOS),
            en_proceso=_contar_tramites_en(db, ESTADOS_EN_PROCESO),
            firmados_24h=firmados_24h,
            entregados=_contar_tramites_en(db, ("entregado",)),
        ),
        servicios=[
            schemas.OpcionServicioOut(id_servicio=s.id_servicio, nombre=s.nombre)
            for s in servicios
        ],
        agentes=[
            schemas.OpcionAgenteOut(id_usuario=u.id_usuario, nombre=u.nombre)
            for u in agentes
        ],
    )