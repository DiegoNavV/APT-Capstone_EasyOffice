"""Lógica del flujo de firma.

  1. create_document: recibe el PDF, lo guarda, calcula su SHA-256, fija el plazo
     para firmar y crea los firmantes (las personas en orden + la organización al final).
  2. record_client_signature: registra la aceptación del cliente como su firma
     electrónica simple (con IP, navegador, hora y hash del documento).
  3. Cuando todas las personas firmaron, _complete aplica la firma automática de
     la organización: agrega la hoja de evidencias, sella el PDF (PAdES), guarda
     el PDF firmado y avisa al CRM por webhook.
  4. record_client_rejection: el cliente rechaza firmar -> "rejected".
  5. Si nadie firma antes de expires_at -> "expired" (expire_due_documents, y
     también al consultar un documento vencido).

Cada cambio de estado final genera un aviso (webhook) al CRM:
document.completed, document.rejected, document.expired, document.cancelled.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.core.config import get_settings
from app.schemas import ClientRejectionIn, ClientSignatureIn, DocumentCreate
from app.services import audit, pdf, webhooks
from app.services.storage import Storage

logger = logging.getLogger("firma.signing")

METODO_CLIENTE = "Aceptación en el sitio web del cliente (firma electrónica simple)"
METODO_ORGANIZACION = "Firma automática con certificado de la plataforma (sello PAdES)"


class FlowError(Exception):
    """Operación no permitida en el estado actual (se responde 409)."""


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: datetime | None) -> datetime | None:
    """SQLite devuelve fechas sin zona horaria; se asumen en UTC para poder comparar."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _fmt(dt: datetime | None) -> str:
    dt = _utc(dt)
    return "-" if dt is None else f"{dt:%Y-%m-%d %H:%M:%S} UTC"


def _encolar_pendientes(db: Session, documento: models.Document) -> None:
    """Encola los avisos pendientes del documento (después del commit)."""
    for entrega in db.query(models.WebhookDelivery).filter_by(document_id=documento.id, status="pending").all():
        webhooks.enqueue(entrega.id)


# ---------- Crear ----------

def create_document(db: Session, storage: Storage, client_id: str, file_bytes: bytes, data: DocumentCreate) -> models.Document:
    settings = get_settings()
    pdf.validate_pdf(file_bytes, settings.max_pdf_bytes)
    if data.callback_url:
        webhooks.validate_callback_url(data.callback_url)

    dias = data.expires_in_days or settings.document_default_expiration_days
    documento = models.Document(
        id=models.nuevo_id(),
        client_id=client_id,
        title=data.title,
        external_ref=data.external_ref,
        status=models.DOC_PENDING,
        client_verification=data.client_verification,
        original_sha256=pdf.sha256_hex(file_bytes),
        original_key="",
        callback_url=data.callback_url,
        metadata_json=data.metadata,
        expires_at=_ahora() + timedelta(days=dias),
    )
    documento.original_key = f"documents/{documento.id}/original.pdf"
    for i, s in enumerate(data.signers, start=1):
        documento.signers.append(models.Signer(
            id=models.nuevo_id(), order_index=i, kind=models.KIND_PERSON, name=s.name, email=s.email,
            rut=s.rut, represents_name=s.represents_name, represents_rut=s.represents_rut, evidence={},
        ))
    if data.auto_organization_signature:
        documento.signers.append(models.Signer(
            id=models.nuevo_id(), order_index=len(data.signers) + 1, kind=models.KIND_ORGANIZATION_AUTO,
            name=settings.organization_signer_name, rut=settings.organization_signer_rut or None, evidence={},
        ))

    # Primero el archivo: si el almacenamiento falla no queda un documento sin PDF.
    storage.put(documento.original_key, file_bytes)
    db.add(documento)
    db.flush()
    audit.record(db, "document.created", documento.id, {
        "client_id": client_id,
        "original_sha256": documento.original_sha256,
        "signers": len(documento.signers),
        "external_ref": documento.external_ref,
        "expires_at": _fmt(documento.expires_at),
    })
    db.commit()
    db.refresh(documento)
    return documento


# ---------- Expiración ----------

def expire_if_due(db: Session, documento: models.Document) -> bool:
    """Si el documento sigue pendiente y ya venció, lo marca "expired". Devuelve True si expiró ahora.
    Deja los cambios en la sesión: quien llama hace commit."""
    if documento.status != models.DOC_PENDING or documento.expires_at is None:
        return False
    if _utc(documento.expires_at) > _ahora():
        return False
    documento.status = models.DOC_EXPIRED
    documento.expired_at = _ahora()
    audit.record(db, "document.expired", documento.id, {"expires_at": _fmt(documento.expires_at)})
    webhooks.create_delivery(db, documento, "document.expired")
    return True


def refresh_expiration(db: Session, documento: models.Document) -> models.Document:
    """Usado al consultar: aplica la expiración vencida y la guarda."""
    if expire_if_due(db, documento):
        db.commit()
        db.refresh(documento)
        _encolar_pendientes(db, documento)
    return documento


def expire_due_documents(db: Session) -> int:
    """Tarea periódica: expira todos los documentos pendientes vencidos. Devuelve cuántos."""
    vencidos = db.execute(
        select(models.Document).where(
            models.Document.status == models.DOC_PENDING,
            models.Document.expires_at.is_not(None),
            models.Document.expires_at <= _ahora(),
        )
    ).scalars().all()
    total = 0
    for documento in vencidos:
        if expire_if_due(db, documento):
            total += 1
    db.commit()
    for documento in vencidos:
        _encolar_pendientes(db, documento)
    return total


# ---------- Firma y rechazo del cliente ----------

def _verificar_pendiente(db: Session, documento: models.Document) -> None:
    if expire_if_due(db, documento):
        db.commit()
        _encolar_pendientes(db, documento)
        raise FlowError("El plazo para firmar venció: el documento expiró.")
    if documento.status != models.DOC_PENDING:
        raise FlowError(f"El documento está '{documento.status}' y no admite más firmas.")


def _siguiente_persona(documento: models.Document) -> models.Signer | None:
    for s in documento.signers:
        if s.kind == models.KIND_PERSON and s.status == models.SIGNER_PENDING:
            return s
    return None


def _firmante_en_turno(documento: models.Document, signer_id: str | None) -> models.Signer:
    siguiente = _siguiente_persona(documento)
    if siguiente is None:
        raise FlowError("No hay firmantes pendientes.")
    if signer_id and signer_id != siguiente.id:
        objetivo = next((s for s in documento.signers if s.id == signer_id), None)
        if objetivo is None or objetivo.kind != models.KIND_PERSON:
            raise FlowError("El firmante indicado no pertenece a este documento.")
        if objetivo.status != models.SIGNER_PENDING:
            raise FlowError("Ese firmante ya respondió.")
        # Orden secuencial: no puede firmar antes que los anteriores.
        raise FlowError("Aún no es el turno de ese firmante (las firmas son en orden).")
    return siguiente


def record_client_signature(db: Session, storage: Storage, documento: models.Document, data: ClientSignatureIn) -> models.Document:
    _verificar_pendiente(db, documento)
    firmante = _firmante_en_turno(documento, data.signer_id)

    ahora = _ahora()
    firmante.status = models.SIGNER_SIGNED
    firmante.signed_at = data.accepted_at or ahora
    firmante.evidence = {
        "method": METODO_CLIENTE,
        "ip": data.ip,
        "user_agent": data.user_agent,
        "consent": True,
        "document_sha256": documento.original_sha256,
        "accepted_at": _fmt(firmante.signed_at),
        "recorded_at": _fmt(ahora),
    }
    audit.record(db, "signer.signed", documento.id, {
        "signer_id": firmante.id, "kind": firmante.kind, "ip": data.ip,
        "document_sha256": documento.original_sha256,
    })

    if _siguiente_persona(documento) is None:
        _complete(db, storage, documento)
    db.commit()
    db.refresh(documento)
    _encolar_pendientes(db, documento)
    return documento


def record_client_rejection(db: Session, documento: models.Document, data: ClientRejectionIn) -> models.Document:
    _verificar_pendiente(db, documento)
    firmante = _firmante_en_turno(documento, data.signer_id)

    ahora = _ahora()
    firmante.status = models.SIGNER_REJECTED
    firmante.evidence = {
        "method": "Rechazo en el sitio web del cliente",
        "ip": data.ip,
        "user_agent": data.user_agent,
        "reason": data.reason,
        "document_sha256": documento.original_sha256,
        "recorded_at": _fmt(ahora),
    }
    documento.status = models.DOC_REJECTED
    documento.rejected_at = ahora
    audit.record(db, "signer.rejected", documento.id, {"signer_id": firmante.id, "ip": data.ip})
    audit.record(db, "document.rejected", documento.id, {})
    webhooks.create_delivery(db, documento, "document.rejected")
    db.commit()
    db.refresh(documento)
    _encolar_pendientes(db, documento)
    return documento


def rejection_reason(documento: models.Document) -> str | None:
    for s in documento.signers:
        if s.status == models.SIGNER_REJECTED:
            return (s.evidence or {}).get("reason")
    return None


# ---------- Completar (firma automática de la organización) ----------

def _complete(db: Session, storage: Storage, documento: models.Document) -> None:
    """Firma automática de la organización + hoja de evidencias + sello PAdES."""
    settings = get_settings()
    ahora = _ahora()
    clave, cert = pdf.ensure_platform_certificate(settings.certs_dir, settings.organization_signer_name)
    huella = pdf.certificate_fingerprint(cert)

    for s in documento.signers:
        if s.kind == models.KIND_ORGANIZATION_AUTO and s.status == models.SIGNER_PENDING:
            s.status = models.SIGNER_SIGNED
            s.signed_at = ahora
            s.evidence = {
                "method": METODO_ORGANIZACION,
                "certificate_sha256": huella,
                "document_sha256": documento.original_sha256,
                "recorded_at": _fmt(ahora),
            }
            audit.record(db, "signer.signed", documento.id, {
                "signer_id": s.id, "kind": s.kind, "certificate_sha256": huella,
            })

    firmantes = [
        pdf.EvidenceSigner(
            name=s.name, rut=s.rut, represents_name=s.represents_name, represents_rut=s.represents_rut,
            method=s.evidence.get("method", ""), signed_at=_fmt(s.signed_at),
            ip=s.evidence.get("ip"), user_agent=s.evidence.get("user_agent"),
        )
        for s in documento.signers
    ]
    hoja = pdf.build_evidence_page(
        document_id=documento.id,
        title=documento.title,
        external_ref=documento.external_ref,
        original_sha256=documento.original_sha256,
        signers=firmantes,
        verify_url=f"{settings.public_base_url.rstrip('/')}{settings.api_prefix}/verify/{documento.original_sha256}",
        generated_at=ahora,
    )
    original = storage.get(documento.original_key)
    con_evidencias = pdf.append_pdf(original, hoja)

    try:
        firmado = pdf.sign_pades(
            con_evidencias, clave, cert,
            reason=f"Firma electrónica simple - {settings.organization_signer_name}",
        )
        tipo = "pades"
    except Exception as exc:  # noqa: BLE001
        # Si el sello falla, el documento igual se entrega con su hoja de
        # evidencias, pero queda registrado que NO tiene sello digital.
        logger.error("Falló el sello PAdES del documento %s: %s", documento.id, type(exc).__name__)
        audit.record(db, "document.seal_failed", documento.id, {"error": type(exc).__name__})
        firmado, tipo = con_evidencias, "none"

    documento.signed_key = f"documents/{documento.id}/signed.pdf"
    storage.put(documento.signed_key, firmado)
    documento.signed_sha256 = pdf.sha256_hex(firmado)
    documento.signature_type = tipo
    documento.status = models.DOC_COMPLETED
    documento.completed_at = ahora
    audit.record(db, "document.completed", documento.id, {
        "signed_sha256": documento.signed_sha256, "signature_type": tipo,
    })
    webhooks.create_delivery(db, documento, "document.completed")


# ---------- Cancelar ----------

def cancel(db: Session, documento: models.Document) -> models.Document:
    _verificar_pendiente(db, documento)
    documento.status = models.DOC_CANCELLED
    documento.cancelled_at = _ahora()
    audit.record(db, "document.cancelled", documento.id, {})
    webhooks.create_delivery(db, documento, "document.cancelled")
    db.commit()
    db.refresh(documento)
    _encolar_pendientes(db, documento)
    return documento
