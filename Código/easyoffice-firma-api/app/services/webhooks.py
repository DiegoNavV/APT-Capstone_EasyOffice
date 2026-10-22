"""Webhooks: avisos al sistema cliente (CRM) cuando cambia un documento.

Cada aviso va firmado con HMAC-SHA256:
    X-Firma-Timestamp: <segundos Unix>
    X-Firma-Signature: sha256=<hex de HMAC(webhook_secret, "<timestamp>." + cuerpo)>
El CRM recalcula la firma con el mismo secreto y rechaza el aviso si no coincide
o si el timestamp tiene más de 5 minutos (evita que se reenvíe un aviso viejo).
Los envíos se hacen desde el worker de Celery, con reintentos y espera creciente.
"""
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app import models
from app.core.config import get_settings

logger = logging.getLogger("firma.webhooks")


class CallbackUrlNotAllowed(ValueError):
    pass


def validate_callback_url(url: str) -> str:
    """Solo http/https y hacia hosts permitidos (evita SSRF: que la API llame a lugares internos arbitrarios)."""
    partes = urlparse(url)
    if partes.scheme not in ("http", "https") or not partes.hostname:
        raise CallbackUrlNotAllowed("callback_url debe ser una URL http(s) válida.")
    if partes.username or partes.password:
        raise CallbackUrlNotAllowed("callback_url no puede incluir credenciales.")
    if partes.hostname.lower() not in get_settings().webhook_allowed_host_list:
        raise CallbackUrlNotAllowed(
            f"El host '{partes.hostname}' no está permitido para webhooks (WEBHOOK_ALLOWED_HOSTS)."
        )
    return url


def body_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")


def sign_body(body: bytes, timestamp: str, secret: str | None = None) -> str:
    """Firma "<timestamp>.<cuerpo>": el timestamp queda protegido junto con el cuerpo."""
    secret = secret if secret is not None else get_settings().webhook_secret
    mensaje = timestamp.encode("ascii") + b"." + body
    return "sha256=" + hmac.new(secret.encode("utf-8"), mensaje, hashlib.sha256).hexdigest()


def verify_signature(body: bytes, timestamp: str, signature: str, secret: str, tolerance_s: int = 300) -> bool:
    """Lo que debe hacer el receptor (el CRM). Se usa también en los tests."""
    try:
        if abs(time.time() - int(timestamp)) > tolerance_s:
            return False
    except ValueError:
        return False
    return hmac.compare_digest(sign_body(body, timestamp, secret), signature)


def create_delivery(db: Session, document: models.Document, event: str) -> models.WebhookDelivery | None:
    """Registra un aviso pendiente (en la misma transacción del cambio). None si no hay callback."""
    if not document.callback_url:
        return None
    payload = {
        "event": event,
        "document_id": document.id,
        "external_ref": document.external_ref,
        "status": document.status,
        "signed_sha256": document.signed_sha256,
        "signature_type": document.signature_type,
        "completed_at": document.completed_at.isoformat() if document.completed_at else None,
    }
    if event == "document.rejected":
        from app.services.signing import rejection_reason

        payload["rejection_reason"] = rejection_reason(document)
    entrega = models.WebhookDelivery(document_id=document.id, event=event, url=document.callback_url, payload=payload)
    db.add(entrega)
    db.flush()
    return entrega


def enqueue(delivery_id: str) -> None:
    """Encola el envío en Celery. Si la cola no está disponible, el aviso queda pendiente (no rompe la firma)."""
    try:
        from app.worker import deliver_webhook_task

        deliver_webhook_task.apply_async(args=[delivery_id], retry=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo encolar el webhook %s: %s", delivery_id, type(exc).__name__)


def deliver(db: Session, delivery_id: str) -> bool:
    """Envía un aviso una vez. Devuelve True si el CRM respondió 2xx."""
    import httpx

    entrega = db.get(models.WebhookDelivery, delivery_id)
    if entrega is None or entrega.status == "delivered":
        return True
    cuerpo = body_bytes(entrega.payload)
    marca = str(int(time.time()))
    entrega.attempts += 1
    try:
        respuesta = httpx.post(
            entrega.url,
            content=cuerpo,
            headers={
                "Content-Type": "application/json",
                "X-Firma-Event": entrega.event,
                "X-Firma-Delivery": entrega.id,
                "X-Firma-Timestamp": marca,
                "X-Firma-Signature": sign_body(cuerpo, marca),
            },
            timeout=10,
            follow_redirects=False,
        )
        entrega.last_status_code = respuesta.status_code
        ok = 200 <= respuesta.status_code < 300
        entrega.last_error = None if ok else f"HTTP {respuesta.status_code}"
    except httpx.HTTPError as exc:
        ok = False
        entrega.last_error = type(exc).__name__
    if ok:
        entrega.status = "delivered"
        entrega.delivered_at = datetime.now(timezone.utc)
    elif entrega.attempts >= get_settings().webhook_max_attempts:
        entrega.status = "failed"
    db.commit()
    return ok
