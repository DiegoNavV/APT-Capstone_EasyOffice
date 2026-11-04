"""
Verificacion de los avisos (webhook) de la API de firma. Contrato: easyoffice-firma-api/CONTRATO_INTEGRACION.md, seccion 6.

La API firma cada aviso con HMAC-SHA256 sobre "<timestamp>." + cuerpo (los bytes exactos que llegaron), usando el secreto compartido 
FIRMA_WEBHOOK_SECRET. La ruta es publica, asi que esta revision es lo unico que impide que cualquiera le diga al CRM que 
un tramite ya esta firmado.

Se rechaza el aviso si:
  - la firma no coincide (se compara en tiempo constante), o
  - la marca de tiempo difiere en mas de 5 minutos de la hora actual (evita reenviar avisos viejos).
"""
import hashlib
import hmac
import os
import time

TOLERANCIA_S = 300


def _secreto() -> bytes:
    # Se lee en cada uso (no al importar) para que las pruebas puedan cambiarlo.
    return os.getenv("FIRMA_WEBHOOK_SECRET", "dev-inseguro-cambiar").encode()


def firmar(cuerpo: bytes, timestamp: str) -> str:
    """Firma que la API de firma deberia haber enviado para este cuerpo y esta marca de tiempo."""
    calculada = hmac.new(_secreto(), timestamp.encode() + b"." + cuerpo, hashlib.sha256).hexdigest()
    return "sha256=" + calculada


def aviso_valido(cuerpo: bytes, timestamp: str, firma: str, ahora: float | None = None) -> bool:
    """True si el aviso es autentico y reciente. Nunca lanza: ante cualquier dato raro devuelve False."""
    try:
        marca = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs((time.time() if ahora is None else ahora) - marca) > TOLERANCIA_S:
        return False
    # Se comparan como bytes: con texto, un caracter no ASCII haria lanzar un error en vez de rechazar.
    return hmac.compare_digest(firmar(cuerpo, timestamp).encode(), (firma or "").encode())