"""Retención y anonimización de datos personales (Ley 21.719).

Una solicitud de contacto descartada (ver crud.descartar_solicitud) conserva sus datos de
contacto por si el cliente vuelve y paga. Pasado el plazo de retención sin ninguna novedad,
se anonimiza: se borran nombre/run/email/numero_contacto/mensaje y se marca
fecha_anonimizacion, dejando la fila (estado, fechas, historial) para trazabilidad.

El resultado exacto de anonimizar lo exige ck_solicitud_anonimizacion en
db/init/01_schema.sql: estado = 'descartada' y los 5 campos en NULL cuando
fecha_anonimizacion no es NULL. Esta función solo implementa esa regla con un criterio de
cuándo aplicarla; la pensada para correr periódicamente es
scripts/anonimizar_solicitudes_vencidas.py, no para llamarse desde un endpoint.
"""
from calendar import monthrange
from datetime import datetime

from sqlalchemy.orm import Session

from app import models
from app.crud import SOLICITUD_DESCARTADA, ahora_utc

# Plazo de retención tras la última actualización de una solicitud descartada.
MESES_RETENCION_SOLICITUD_DESCARTADA = 6


def _hace_n_meses(fecha: datetime, meses: int) -> datetime:
    """`fecha` menos `meses` meses, conservando el día (o el último día válido de ese mes,
    p. ej. 31 de marzo menos 1 mes cae en el 28 o 29 de febrero)."""
    mes_total = fecha.month - 1 - meses
    anio = fecha.year + mes_total // 12
    mes = mes_total % 12 + 1
    dia = min(fecha.day, monthrange(anio, mes)[1])
    return fecha.replace(year=anio, month=mes, day=dia)


def anonimizar_solicitudes_vencidas(
    db: Session, meses: int = MESES_RETENCION_SOLICITUD_DESCARTADA
) -> int:
    """Anonimiza las solicitudes descartadas sin novedad desde hace más de `meses` meses.

    No toca las pendientes, las convertidas ni las ya anonimizadas. Devuelve cuántas filas
    anonimizó."""
    limite = _hace_n_meses(ahora_utc(), meses)
    solicitudes = (
        db.query(models.SolicitudContacto)
        .filter(
            models.SolicitudContacto.estado == SOLICITUD_DESCARTADA,
            models.SolicitudContacto.fecha_anonimizacion.is_(None),
            models.SolicitudContacto.fecha_actualizacion < limite,
        )
        .all()
    )
    for solicitud in solicitudes:
        solicitud.nombre = None
        solicitud.rut = None
        solicitud.email = None
        solicitud.telefono = None
        solicitud.mensaje = None
        solicitud.fecha_anonimizacion = ahora_utc()
    db.commit()
    return len(solicitudes)
