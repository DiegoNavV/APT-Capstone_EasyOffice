"""Esquemas de entrada y salida de la API (validados con Pydantic)."""
import ipaddress
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from app.utils import email_valido, normalizar_rut, rut_valido


def _validar_rut_opcional(valor: str | None) -> str | None:
    valor = normalizar_rut(valor)
    if valor is not None and not rut_valido(valor):
        raise ValueError("RUT inválido.")
    return valor


# ---------- Entrada ----------

class SignerIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=150)
    email: str | None = Field(default=None, max_length=150)
    rut: str | None = Field(default=None, max_length=15)
    # Si firma en representación de una persona jurídica.
    represents_name: str | None = Field(default=None, max_length=200)
    represents_rut: str | None = Field(default=None, max_length=15)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        v = v.lower()
        if not email_valido(v):
            raise ValueError("Correo inválido.")
        return v

    @field_validator("rut", "represents_rut")
    @classmethod
    def _rut(cls, v: str | None) -> str | None:
        return _validar_rut_opcional(v)


class DocumentCreate(BaseModel):
    """Datos que acompañan al PDF en POST /documents (campo de formulario `data`, en JSON)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    # El FOLIO del trámite (ej. LF-0152-2026). Nunca el código de seguimiento del cliente.
    external_ref: str | None = Field(default=None, max_length=100)
    # Días para firmar antes de que expire (por defecto DOCUMENT_DEFAULT_EXPIRATION_DAYS).
    expires_in_days: int | None = Field(default=None, ge=1, le=90)
    # Firmantes personas, en orden. La firma de la organización se agrega al final.
    signers: list[SignerIn] = Field(min_length=1, max_length=10)
    # Agrega la firma automática de la organización (Easy Office) al completar.
    auto_organization_signature: bool = True
    # "ninguna": la aceptación del cliente en el sitio es su firma.
    # "otp": exigirá un código por correo (aún no disponible en esta versión).
    client_verification: Literal["ninguna", "otp"] = "ninguna"
    # A dónde avisar cuando el documento se complete (webhook). Opcional.
    callback_url: str | None = Field(default=None, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("client_verification")
    @classmethod
    def _otp_no_disponible(cls, v: str) -> str:
        if v == "otp":
            raise ValueError("La verificación por OTP aún no está disponible en esta versión.")
        return v

    @field_validator("metadata")
    @classmethod
    def _metadata_acotada(cls, v: dict) -> dict:
        if len(str(v)) > 4000:
            raise ValueError("metadata no puede superar 4000 caracteres.")
        return v


class ClientSignatureIn(BaseModel):
    """Aceptación del cliente, que el CRM registra en su nombre (servidor a servidor)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # Firmante que acepta. Si se omite, se usa el siguiente firmante persona pendiente.
    signer_id: str | None = Field(default=None, max_length=36)
    # IP y navegador del CLIENTE (no del servidor del CRM): son la evidencia.
    ip: str = Field(max_length=45)
    user_agent: str = Field(min_length=1, max_length=500)
    # Debe ser exactamente true.
    consent: StrictBool
    # Momento en que el cliente aceptó en el sitio (si se omite, ahora).
    accepted_at: datetime | None = None

    @field_validator("ip")
    @classmethod
    def _ip(cls, v: str) -> str:
        try:
            return str(ipaddress.ip_address(v))
        except ValueError as exc:
            raise ValueError("IP inválida.") from exc

    @field_validator("consent")
    @classmethod
    def _consent(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("El consentimiento del cliente es obligatorio.")
        return v


class ClientRejectionIn(BaseModel):
    """El cliente rechaza firmar. El CRM lo registra en su nombre."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    signer_id: str | None = Field(default=None, max_length=36)
    ip: str = Field(max_length=45)
    user_agent: str = Field(min_length=1, max_length=500)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("ip")
    @classmethod
    def _ip(cls, v: str) -> str:
        try:
            return str(ipaddress.ip_address(v))
        except ValueError as exc:
            raise ValueError("IP inválida.") from exc


# ---------- Salida ----------

class SignerOut(BaseModel):
    id: str
    order: int
    kind: str
    name: str
    rut: str | None
    represents_name: str | None
    represents_rut: str | None
    status: str
    signed_at: datetime | None


class DocumentLinks(BaseModel):
    document: str
    download_original: str
    download_signed: str | None
    evidence: str
    verify: str


class DocumentOut(BaseModel):
    id: str
    title: str
    external_ref: str | None
    status: str
    client_verification: str
    original_sha256: str
    signed_sha256: str | None
    signature_type: str | None
    created_at: datetime
    expires_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    rejected_at: datetime | None
    expired_at: datetime | None
    rejection_reason: str | None
    signers: list[SignerOut]
    links: DocumentLinks


class AuditEventOut(BaseModel):
    id: int
    event_type: str
    payload: dict
    created_at: datetime
    hash: str


class EvidenceOut(BaseModel):
    document_id: str
    chain_valid: bool
    events: list[AuditEventOut]


class VerifyOut(BaseModel):
    found: bool
    # "signed": coincide con el PDF firmado; "original": con el PDF antes de firmar.
    match: Literal["signed", "original"] | None = None
    status: str | None = None
    signature_type: str | None = None
    completed_at: datetime | None = None
    signers_signed: int | None = None
