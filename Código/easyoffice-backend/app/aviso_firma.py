"""
Aplica los avisos (webhook) de la API de firma al tramite. Contrato: easyoffice-firma-api/CONTRATO_INTEGRACION.md

Esta pieza asume que el aviso ya se verifico (app/firma_webhook.py). El tramite se busca por el id del documento en la API 
(`tramite.documento_firma_id`), y se comprueba que el folio coincida.

  document.completed  -> descarga el PDF firmado, lo guarda como copia oficial y el tramite pasa a `firmado`.
  document.rejected   -> el tramite pasa a `rechazado` (el cliente lo rechazo en la firma).
  document.expired    -> el tramite pasa a `rechazado` (vencio el plazo para firmar).
  cualquier otro      -> se ignora (el CRM mismo cancela, no necesita que le avisen).

La API puede mandar el mismo aviso mas de una vez: si el tramite ya esta en el estado que corresponde, no se hace nada. Los cambios de 
estado quedan en el historial con origen `sistema`.
"""
import hashlib
import logging
import os
import uuid

from sqlalchemy.exc import IntegrityError, InternalError
from sqlalchemy.orm import Session

from app import documentos, firma_client, models

log = logging.getLogger("easyoffice.aviso_firma")

# Resultados de procesar_aviso.
FIRMADO = "firmado"
RECHAZADO = "rechazado"
SIN_CAMBIOS = "sin_cambios"
IGNORADO = "ignorado"

# Con la copia firmada ya guardada, o con el tramite cerrado, un aviso nuevo no cambia nada.
ESTADOS_CON_COPIA_FIRMADA = ("firmado", "entregado")
ESTADOS_QUE_NO_SE_RECHAZAN = ("firmado", "entregado", "rechazado", "cancelado")

MAX_MOTIVO = 500


class AvisoNoProcesable(Exception):
    """El aviso es autentico pero no se pudo aplicar (ej. el PDF que entrega la API no es valido).
    La API de firma debe reintentarlo: el estado del tramite no cambio."""


def _cambiar_estado(db: Session, tramite: models.Tramite, estado: str, comentario: str) -> bool:
    """Registra el cambio en el historial (un trigger actualiza el estado del tramite).
    False si otro aviso se adelanto y el estado ya era ese."""
    try:
        db.add(models.HistorialEstado(
            id_tramite=tramite.id_tramite, estado=estado, origen="sistema", comentario=comentario,
        ))
        db.commit()
    except (IntegrityError, InternalError):
        # fn_historial_no_duplicado (02_funciones.sql) no deja repetir el mismo estado dos veces seguidas.
        db.rollback()
        return False
    db.refresh(tramite)
    return True


def _guardar_copia_firmada(tramite: models.Tramite, pdf: bytes) -> None:
    """Reemplaza el PDF sin firmar por el firmado (misma ruta). Escribe a un temporal y lo mueve,
    para que nunca quede a medias."""
    if not tramite.ruta_documento_generado:
        raise AvisoNoProcesable("El tramite no tiene un documento generado donde guardar la copia firmada.")
    base = documentos.directorio_documentos().resolve()
    destino = (base / tramite.ruta_documento_generado).resolve()
    if base not in destino.parents:
        raise AvisoNoProcesable("La ruta del documento queda fuera de la carpeta de documentos.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(f".{uuid.uuid4().hex}.tmp")
    temporal.write_bytes(pdf)
    os.replace(temporal, destino)


def _completado(db: Session, tramite: models.Tramite, evento: dict) -> str:
    if tramite.estado_actual in ESTADOS_CON_COPIA_FIRMADA:
        return SIN_CAMBIOS

    # Si la API no entrega el PDF, ErrorFirma sube hasta quien llama y la API reintenta el aviso.
    pdf = firma_client.descargar_firmado(tramite.documento_firma_id)

    if not pdf.startswith(b"%PDF"):
        raise AvisoNoProcesable("La API de firma entrego un archivo que no es un PDF.")
    esperado = evento.get("signed_sha256")
    if esperado and hashlib.sha256(pdf).hexdigest() != str(esperado).lower():
        raise AvisoNoProcesable("La huella del PDF descargado no coincide con la que informo la API de firma.")

    _guardar_copia_firmada(tramite, pdf)
    if not _cambiar_estado(
        db, tramite, "firmado", "La firma quedó completa. Se guardó la copia firmada como documento oficial."
    ):
        return SIN_CAMBIOS
    log.info("Tramite %s firmado.", tramite.id_tramite)
    return FIRMADO


def _rechazado(db: Session, tramite: models.Tramite, evento: dict) -> str:
    if tramite.estado_actual in ESTADOS_QUE_NO_SE_RECHAZAN:
        return SIN_CAMBIOS

    if evento.get("event") == "document.expired":
        comentario = "Venció el plazo para firmar el documento."
    else:
        comentario = "El cliente rechazó el documento en la firma."
        motivo = evento.get("rejection_reason")
        if isinstance(motivo, str) and motivo.strip():
            comentario += f" Motivo: {motivo.strip()[:MAX_MOTIVO]}"

    if not _cambiar_estado(db, tramite, "rechazado", comentario):
        return SIN_CAMBIOS
    log.info("Tramite %s rechazado (%s).", tramite.id_tramite, evento.get("event"))
    return RECHAZADO


def procesar_aviso(db: Session, evento: dict) -> str:
    """Aplica un aviso ya verificado. Devuelve FIRMADO, RECHAZADO, SIN_CAMBIOS o IGNORADO.
    Lanza ErrorFirma (la API no entrego el PDF) o AvisoNoProcesable: en ambos casos hay que
    responder con error para que la API de firma reintente."""
    tipo = evento.get("event")
    id_documento = evento.get("document_id")
    if not isinstance(tipo, str) or not isinstance(id_documento, str):
        return IGNORADO

    tramite = db.query(models.Tramite).filter(models.Tramite.documento_firma_id == id_documento).first()
    if tramite is None:
        log.warning("Aviso %s de un documento desconocido; se ignora.", tipo)
        return IGNORADO

    folio = evento.get("external_ref")
    if folio and tramite.folio and folio != tramite.folio:
        log.error("Aviso %s: el folio no coincide con el del tramite %s; se ignora.", tipo, tramite.id_tramite)
        return IGNORADO

    if tipo == "document.completed":
        return _completado(db, tramite, evento)
    if tipo in ("document.rejected", "document.expired"):
        return _rechazado(db, tramite, evento)
    return IGNORADO