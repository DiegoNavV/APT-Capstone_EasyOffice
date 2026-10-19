"""Autenticación servidor a servidor con API key (header X-API-Key).

Versión de pruebas: las claves válidas vienen de la variable de entorno API_KEYS.
Cada clave identifica a un "cliente" de la API (client_id = huella de la clave),
y un cliente solo ve sus propios documentos. La gestión completa (organizaciones,
claves con hash en base de datos, rotación, sandbox/producción) es la Fase 1.
"""
import hashlib
import hmac

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from app.core.config import get_settings

_header = APIKeyHeader(name="X-API-Key", auto_error=False, description="API key del cliente (ej. el CRM).")

_NO_AUTORIZADO = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="API key inválida o ausente.",
    headers={"WWW-Authenticate": "ApiKey"},
)


def client_id_for(api_key: str) -> str:
    """Huella corta y estable de la clave; nunca se guarda ni se loguea la clave."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]


def require_api_key(api_key: str | None = Depends(_header)) -> str:
    """Dependencia: devuelve el client_id o responde 401."""
    if not api_key:
        raise _NO_AUTORIZADO
    valida = False
    for candidata in get_settings().api_key_list:
        # compare_digest: el tiempo de respuesta no revela cuántos caracteres coinciden.
        if hmac.compare_digest(api_key.encode("utf-8"), candidata.encode("utf-8")):
            valida = True
    if not valida:
        raise _NO_AUTORIZADO
    return client_id_for(api_key)
