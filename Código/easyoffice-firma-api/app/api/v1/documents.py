"""Documentos y flujo de firma (requieren X-API-Key).

  POST /api/v1/documents                          subir PDF + firmantes  -> 201
  GET  /api/v1/documents/{id}                     estado del documento
  POST /api/v1/documents/{id}/client-signature    aceptación del cliente -> firma y completa
  POST /api/v1/documents/{id}/client-rejection    el cliente rechaza -> rejected
  GET  /api/v1/documents/{id}/download            PDF (?version=signed|original)
  GET  /api/v1/documents/{id}/evidence            bitácora de auditoría del documento
  POST /api/v1/documents/{id}/cancel              cancelar un documento pendiente

Los POST aceptan el header Idempotency-Key: si se repite con el mismo contenido
se devuelve la misma respuesta, sin duplicar nada.
"""
import json
import re
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.core.auth import require_api_key
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas import (
    AuditEventOut,
    ClientRejectionIn,
    ClientSignatureIn,
    DocumentCreate,
    DocumentLinks,
    DocumentOut,
    EvidenceOut,
    SignerOut,
)
from app.services import audit, idempotency, signing
from app.services.pdf import InvalidPdf
from app.services.storage import Storage, get_storage
from app.services.webhooks import CallbackUrlNotAllowed

router = APIRouter(prefix="/documents", tags=["documents"])


# ---------- Helpers ----------

def to_out(documento: models.Document) -> DocumentOut:
    base = f"{get_settings().api_prefix}/documents/{documento.id}"
    return DocumentOut(
        id=documento.id,
        title=documento.title,
        external_ref=documento.external_ref,
        status=documento.status,
        client_verification=documento.client_verification,
        original_sha256=documento.original_sha256,
        signed_sha256=documento.signed_sha256,
        signature_type=documento.signature_type,
        created_at=documento.created_at,
        expires_at=documento.expires_at,
        completed_at=documento.completed_at,
        cancelled_at=documento.cancelled_at,
        rejected_at=documento.rejected_at,
        expired_at=documento.expired_at,
        rejection_reason=signing.rejection_reason(documento),
        signers=[
            SignerOut(
                id=s.id, order=s.order_index, kind=s.kind, name=s.name, rut=s.rut,
                represents_name=s.represents_name, represents_rut=s.represents_rut,
                status=s.status, signed_at=s.signed_at,
            )
            for s in documento.signers
        ],
        links=DocumentLinks(
            document=base,
            download_original=f"{base}/download?version=original",
            download_signed=f"{base}/download?version=signed" if documento.signed_key else None,
            evidence=f"{base}/evidence",
            verify=f"{get_settings().api_prefix}/verify/{documento.signed_sha256 or documento.original_sha256}",
        ),
    )


def _obtener(db: Session, client_id: str, document_id: str, bloquear: bool = False) -> models.Document:
    """Busca un documento del cliente. Un documento de otro cliente responde 404 (no se revela que existe)."""
    consulta = select(models.Document).where(
        models.Document.id == document_id, models.Document.client_id == client_id
    )
    if bloquear:
        # Evita que dos peticiones simultáneas completen el mismo documento (Postgres).
        consulta = consulta.with_for_update()
    documento = db.execute(consulta).scalar_one_or_none()
    if documento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado.")
    return documento


def _respuesta_json(status_code: int, cuerpo: dict, repetida: bool = False) -> JSONResponse:
    headers = {"Idempotent-Replayed": "true"} if repetida else {}
    return JSONResponse(status_code=status_code, content=cuerpo, headers=headers)


def _leer_pdf(file: UploadFile) -> bytes:
    maximo = get_settings().max_pdf_bytes
    datos = file.file.read(maximo + 1)
    if len(datos) > maximo:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"El PDF supera {maximo // (1024 * 1024)} MB.")
    return datos


# ---------- Endpoints ----------

@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentOut,
    summary="Subir un PDF para firmar",
)
def create_document(
    file: UploadFile = File(..., description="PDF a firmar"),
    data: str = Form(..., description="JSON con title, external_ref, signers, callback_url, metadata"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    client_id: str = Depends(require_api_key),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    try:
        datos = DocumentCreate.model_validate(json.loads(data))
    except json.JSONDecodeError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El campo 'data' debe ser un JSON válido.") from None
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()],
        ) from None

    pdf_bytes = _leer_pdf(file)
    req_hash = idempotency.request_hash(pdf_bytes, data.encode("utf-8"))
    previa = idempotency.lookup(db, client_id, "create_document", idempotency_key, req_hash)
    if previa:
        return _respuesta_json(*previa, repetida=True)

    try:
        documento = signing.create_document(db, storage, client_id, pdf_bytes, datos)
    except InvalidPdf as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    except CallbackUrlNotAllowed as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None

    cuerpo = to_out(documento).model_dump(mode="json")
    idempotency.save(db, client_id, "create_document", idempotency_key, req_hash, 201, cuerpo)
    return _respuesta_json(201, cuerpo)


@router.get("/{document_id}", response_model=DocumentOut, summary="Consultar un documento")
def get_document(document_id: str, client_id: str = Depends(require_api_key), db: Session = Depends(get_db)):
    # Si venció el plazo sin firmas, se marca "expired" en este momento.
    return to_out(signing.refresh_expiration(db, _obtener(db, client_id, document_id)))


@router.post(
    "/{document_id}/client-signature",
    response_model=DocumentOut,
    summary="Registrar la aceptación (firma) del cliente",
    description=(
        "El CRM la envía en nombre del cliente cuando este acepta en el sitio web. "
        "`ip` y `user_agent` deben ser los del navegador del cliente. "
        "Cuando todas las personas firmaron, se aplica la firma automática de la organización "
        "y el documento queda `completed`."
    ),
)
def client_signature(
    document_id: str,
    body: ClientSignatureIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    client_id: str = Depends(require_api_key),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    endpoint = f"client_signature:{document_id}"
    req_hash = idempotency.request_hash(body.model_dump_json().encode("utf-8"))
    previa = idempotency.lookup(db, client_id, endpoint, idempotency_key, req_hash)
    if previa:
        return _respuesta_json(*previa, repetida=True)

    documento = _obtener(db, client_id, document_id, bloquear=True)
    try:
        documento = signing.record_client_signature(db, storage, documento, body)
    except signing.FlowError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None

    cuerpo = to_out(documento).model_dump(mode="json")
    idempotency.save(db, client_id, endpoint, idempotency_key, req_hash, 200, cuerpo)
    return _respuesta_json(200, cuerpo)


@router.post(
    "/{document_id}/client-rejection",
    response_model=DocumentOut,
    summary="Registrar que el cliente rechazó firmar",
    description="El documento queda `rejected` y se avisa al CRM con el webhook `document.rejected`.",
)
def client_rejection(
    document_id: str,
    body: ClientRejectionIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    client_id: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    endpoint = f"client_rejection:{document_id}"
    req_hash = idempotency.request_hash(body.model_dump_json().encode("utf-8"))
    previa = idempotency.lookup(db, client_id, endpoint, idempotency_key, req_hash)
    if previa:
        return _respuesta_json(*previa, repetida=True)

    documento = _obtener(db, client_id, document_id, bloquear=True)
    try:
        documento = signing.record_client_rejection(db, documento, body)
    except signing.FlowError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None

    cuerpo = to_out(documento).model_dump(mode="json")
    idempotency.save(db, client_id, endpoint, idempotency_key, req_hash, 200, cuerpo)
    return _respuesta_json(200, cuerpo)


_NOMBRE_SEGURO = re.compile(r"[^A-Za-z0-9._-]+")


@router.get(
    "/{document_id}/download",
    summary="Descargar el PDF",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
def download(
    document_id: str,
    version: Literal["signed", "original"] = Query(default="signed"),
    client_id: str = Depends(require_api_key),
    db: Session = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    documento = _obtener(db, client_id, document_id)
    if version == "signed":
        if not documento.signed_key:
            raise HTTPException(status.HTTP_409_CONFLICT, "El documento aún no está firmado.")
        clave = documento.signed_key
    else:
        clave = documento.original_key
    nombre = _NOMBRE_SEGURO.sub("_", documento.external_ref or documento.id)[:80]
    return Response(
        content=storage.get(clave),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre}-{version}.pdf"'},
    )


@router.get("/{document_id}/evidence", response_model=EvidenceOut, summary="Bitácora de auditoría del documento")
def evidence(document_id: str, client_id: str = Depends(require_api_key), db: Session = Depends(get_db)):
    documento = _obtener(db, client_id, document_id)
    eventos = db.execute(
        select(models.AuditEvent).where(models.AuditEvent.document_id == documento.id).order_by(models.AuditEvent.id)
    ).scalars().all()
    integra, _ = audit.verify_chain(db)
    return EvidenceOut(
        document_id=documento.id,
        chain_valid=integra,
        events=[
            AuditEventOut(id=e.id, event_type=e.event_type, payload=e.payload, created_at=e.created_at, hash=e.hash)
            for e in eventos
        ],
    )


@router.post("/{document_id}/cancel", response_model=DocumentOut, summary="Cancelar un documento pendiente")
def cancel(document_id: str, client_id: str = Depends(require_api_key), db: Session = Depends(get_db)):
    documento = _obtener(db, client_id, document_id, bloquear=True)
    try:
        return to_out(signing.cancel(db, documento))
    except signing.FlowError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
