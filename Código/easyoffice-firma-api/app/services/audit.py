"""Auditoría inmutable con hash encadenado.

Cada evento guarda el hash del evento anterior. Si alguien modifica o borra una
fila, la cadena deja de cuadrar y verify_chain() lo detecta. En Postgres además
un trigger impide UPDATE y DELETE sobre la tabla (ver migración 0002).
"""
import hashlib
import json

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import models

GENESIS = "0" * 64


def _canonico(event_type: str, document_id: str | None, payload: dict, prev_hash: str) -> bytes:
    return json.dumps(
        {"event_type": event_type, "document_id": document_id, "payload": payload, "prev_hash": prev_hash},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def record(db: Session, event_type: str, document_id: str | None, payload: dict | None = None) -> models.AuditEvent:
    """Agrega un evento al final de la cadena. Debe llamarse dentro de la transacción del cambio."""
    payload = payload or {}
    if db.get_bind().dialect.name == "postgresql":
        # Serializa la escritura de la cadena: dos transacciones simultáneas no
        # pueden tomar el mismo "último hash" (la cadena se bifurcaría).
        db.execute(text("SELECT pg_advisory_xact_lock(424242)"))
    ultimo =db.execute(select(models.AuditEvent).order_by(models.AuditEvent.id.desc()).limit(1)).scalar_one_or_none()
    prev_hash = ultimo.hash if ultimo else GENESIS
    evento = models.AuditEvent(
        document_id=document_id,
        event_type=event_type,
        payload=payload,
        prev_hash=prev_hash,
        hash=hashlib.sha256(_canonico(event_type, document_id, payload, prev_hash)).hexdigest(),
    )
    db.add(evento)
    db.flush()
    return evento


def verify_chain(db: Session) -> tuple[bool, int | None]:
    """Devuelve (True, None) si la cadena está íntegra, o (False, id del primer evento alterado)."""
    prev_hash = GENESIS
    for evento in db.execute(select(models.AuditEvent).order_by(models.AuditEvent.id)).scalars():
        esperado = hashlib.sha256(
            _canonico(evento.event_type, evento.document_id, evento.payload, prev_hash)
        ).hexdigest()
        if evento.prev_hash != prev_hash or evento.hash != esperado:
            return False, evento.id
        prev_hash = evento.hash
    return True, None
