"""Modelos de datos de la API de firma.

  documents           un PDF enviado a firmar (original y firmado, con sus hashes)
  signers             quién firma y en qué orden; guarda la evidencia de cada firma
  audit_events        bitácora append-only con hash encadenado (ver services/audit.py)
  idempotency_keys    respuestas guardadas para que un reintento no duplique nada
  webhook_deliveries  avisos al CRM y sus reintentos

Los identificadores públicos son UUID en texto (no se pueden adivinar ni recorrer).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def nuevo_id() -> str:
    return str(uuid.uuid4())


# Estados del documento
DOC_PENDING = "pending"
DOC_COMPLETED = "completed"
DOC_CANCELLED = "cancelled"
DOC_REJECTED = "rejected"    # el cliente rechazó firmar
DOC_EXPIRED = "expired"      # nadie firmó antes de expires_at

# Estados del firmante
SIGNER_PENDING = "pending"
SIGNER_SIGNED = "signed"
SIGNER_REJECTED = "rejected"

# Tipos de firmante
KIND_PERSON = "person"                    # firma una persona (el cliente)
KIND_ORGANIZATION_AUTO = "organization_auto"  # firma automática de la organización (Easy Office)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    # Cliente de la API que lo creó (huella de su API key, nunca la clave).
    client_id: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(String(200))
    # Referencia del sistema que lo envía: el FOLIO del trámite (ej. LF-0152-2026).
    # Nunca el código de seguimiento del cliente (acordado con el equipo del CRM).
    external_ref: Mapped[str | None] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(20), default=DOC_PENDING)
    # "ninguna": la aceptación del cliente es su firma. "otp": requiere código por correo (futuro).
    client_verification: Mapped[str] = mapped_column(String(20), default="ninguna")
    original_key: Mapped[str] = mapped_column(String(200))
    original_sha256: Mapped[str] = mapped_column(String(64), index=True)
    signed_key: Mapped[str | None] = mapped_column(String(200))
    signed_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    # "pades" si el sello digital se aplicó; "none" si solo se agregó la hoja de evidencias.
    signature_type: Mapped[str | None] = mapped_column(String(20))
    callback_url: Mapped[str | None] = mapped_column(String(500))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)
    # Plazo para firmar; pasado este momento el documento queda "expired".
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    signers: Mapped[list["Signer"]] = relationship(
        back_populates="document", order_by="Signer.order_index", cascade="all, delete-orphan"
    )


class Signer(Base):
    __tablename__ = "signers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(30), default=KIND_PERSON)
    name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str | None] = mapped_column(String(150))
    rut: Mapped[str | None] = mapped_column(String(15))
    # Firma en representación de una persona jurídica (brecha B3 del análisis).
    represents_name: Mapped[str | None] = mapped_column(String(200))
    represents_rut: Mapped[str | None] = mapped_column(String(15))
    status: Mapped[str] = mapped_column(String(20), default=SIGNER_PENDING)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # IP, navegador, consentimiento y hash del documento al momento de firmar.
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)

    document: Mapped[Document] = relationship(back_populates="signers")


class AuditEvent(Base):
    """Append-only: nunca se edita ni se borra. Cada fila guarda el hash de la anterior."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    document_id: Mapped[str | None] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    # client_id + clave enviada por el cliente.
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=nuevo_id)
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    event: Mapped[str] = mapped_column(String(50))
    url: Mapped[str] = mapped_column(String(500))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | delivered | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
