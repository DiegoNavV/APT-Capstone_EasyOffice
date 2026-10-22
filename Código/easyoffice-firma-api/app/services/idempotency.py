"""Idempotencia: si el cliente repite un POST con el mismo Idempotency-Key, se
devuelve la misma respuesta en vez de crear un documento duplicado.

  - misma clave + mismo contenido  -> se repite la respuesta guardada
  - misma clave + contenido distinto -> 409 (error del cliente)
"""
import hashlib

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models

MAX_LARGO_CLAVE = 100


def _clave(client_id: str, endpoint: str, idempotency_key: str) -> str:
    if len(idempotency_key) > MAX_LARGO_CLAVE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Idempotency-Key no puede superar {MAX_LARGO_CLAVE} caracteres.")
    return f"{client_id}:{endpoint}:{idempotency_key}"


def request_hash(*partes: bytes) -> str:
    h = hashlib.sha256()
    for p in partes:
        h.update(hashlib.sha256(p).digest())
    return h.hexdigest()


def lookup(db: Session, client_id: str, endpoint: str, idempotency_key: str | None, req_hash: str):
    """Devuelve (status, body) guardados si la petición ya se procesó; None si es nueva."""
    if not idempotency_key:
        return None
    registro = db.get(models.IdempotencyKey, _clave(client_id, endpoint, idempotency_key))
    if registro is None:
        return None
    if registro.request_hash != req_hash:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Este Idempotency-Key ya se usó con un contenido distinto.",
        )
    return registro.response_status, registro.response_body


def save(db: Session, client_id: str, endpoint: str, idempotency_key: str | None, req_hash: str,
         response_status: int, response_body: dict) -> None:
    if not idempotency_key:
        return
    db.add(models.IdempotencyKey(
        key=_clave(client_id, endpoint, idempotency_key),
        request_hash=req_hash,
        response_status=response_status,
        response_body=response_body,
    ))
    try:
        db.commit()
    except IntegrityError:
        # Otra petición con la misma clave ganó la carrera: su respuesta ya quedó guardada.
        db.rollback()
