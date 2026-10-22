"""Verificación pública de documentos por hash (no requiere API key).

Cualquiera con el PDF puede calcular su SHA-256 y comprobar si fue firmado en
la plataforma. No devuelve nombres, RUT ni contenido: solo el estado.
"""
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import models
from app.db.session import get_db
from app.schemas import VerifyOut

router = APIRouter(prefix="/verify", tags=["verify"])

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@router.get("/{sha256}", response_model=VerifyOut, summary="Verificar un documento por su SHA-256")
def verify(sha256: str, db: Session = Depends(get_db)):
    sha256 = sha256.strip().lower()
    if not _SHA256.match(sha256):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Debe ser un SHA-256 en hexadecimal (64 caracteres).")
    documento = db.execute(
        select(models.Document)
        .where(or_(models.Document.signed_sha256 == sha256, models.Document.original_sha256 == sha256))
        .order_by(models.Document.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if documento is None:
        return VerifyOut(found=False)
    return VerifyOut(
        found=True,
        match="signed" if documento.signed_sha256 == sha256 else "original",
        status=documento.status,
        signature_type=documento.signature_type,
        completed_at=documento.completed_at,
        signers_signed=sum(1 for s in documento.signers if s.status == models.SIGNER_SIGNED),
    )
