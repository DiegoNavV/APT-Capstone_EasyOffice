"""Lógica de negocio del módulo: crear solicitud, convertirla a trámite
(generando el código de 8 caracteres) y consultar un trámite por código.
"""
import random
import string

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


def _generar_codigo_unico(db: Session) -> str:
    alfabeto = string.ascii_uppercase + string.digits
    for _ in range(20):
        codigo = "".join(random.choices(alfabeto, k=8))
        existe = db.query(models.Tramite).filter_by(codigo_seguimiento=codigo).first()
        if not existe:
            return codigo
    # Extremadamente improbable con 36^8 combinaciones, pero no lo dejamos colgado.
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