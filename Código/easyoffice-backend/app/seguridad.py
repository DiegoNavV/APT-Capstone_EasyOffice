"""Piezas de seguridad del login del panel interno (agentes y administradores):

- Contraseñas: hash Argon2id. Nunca se guarda la contraseña en texto plano.
- Access token: JWT de corta duración que el frontend manda en el header
  "Authorization: Bearer ...". El servidor solo verifica su firma.
- Refresh token: valor aleatorio que viaja en una cookie httpOnly y sirve para
  pedir un access token nuevo. En la BD se guarda solo su hash SHA-256.
- get_usuario_actual: dependencia para proteger endpoints que requieren login.

Los endpoints que usan estas piezas están en app/routers/auth.py.
"""
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app import models
from app.database import get_db

# ---------- Configuración (variables de entorno, ver docker-compose.yml) ----------

# Generar uno propio POR ENTORNO: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "cambiar-esto-en-cada-entorno")
JWT_ALGORITHM = "HS256"
# 90 min: el frontend debería renovarlo en segundo plano con /api/auth/refresh
# durante la jornada, no depender de que dure la jornada completa.
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "90"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Bloqueo de la cuenta tras N contraseñas incorrectas seguidas (fuerza bruta).
MAX_INTENTOS_FALLIDOS = int(os.getenv("MAX_INTENTOS_FALLIDOS", "5"))
BLOQUEO_MINUTOS = int(os.getenv("BLOQUEO_MINUTOS", "15"))

# true SOLO si la API corre detrás de HTTPS real. En localhost sin HTTPS debe
# quedar en false, o el navegador descarta la cookie del refresh token.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

# Límite de peticiones por IP (se aplica con @limiter.limit en cada endpoint).
limiter = Limiter(key_func=get_remote_address)


def ahora_utc() -> datetime:
    """Hora actual en UTC sin zona horaria, igual que las columnas TIMESTAMP
    de la BD (así se pueden comparar directamente)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------- Contraseñas ----------

# Argon2id es la recomendación #1 de OWASP para guardar contraseñas.
_hasher = PasswordHasher()

# Hash "señuelo": si el email no existe igual se verifica contra este hash, para
# que la respuesta tarde lo mismo y no se pueda averiguar qué correos están
# registrados midiendo el tiempo de respuesta.
_HASH_SENUELO = _hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verificar_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _HASH_SENUELO, password)
    except (VerificationError, InvalidHashError):
        # VerificationError: contraseña incorrecta.
        # InvalidHashError: el hash guardado no es Argon2 (ej. el usuario de
        # prueba de db/init/02_seed.sql); se trata igual que una incorrecta.
        return False


# ---------- Access token (JWT) ----------

def crear_access_token(id_usuario: int, rol: str) -> str:
    ahora = datetime.now(timezone.utc)
    payload = {
        "sub": str(id_usuario),
        "rol": rol,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decodificar_access_token(token: str) -> dict:
    """Lanza jwt.PyJWTError si el token es inválido, fue alterado o expiró."""
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


# ---------- Refresh token ----------

def generar_refresh_token() -> tuple[str, str]:
    """Devuelve (token_plano, hash). El token plano va a la cookie; en la BD
    solo se guarda el hash, así una filtración de la BD no permite robar
    sesiones. Se usa SHA-256 (y no Argon2) porque es un valor aleatorio largo,
    imposible de adivinar por fuerza bruta."""
    token_plano = secrets.token_urlsafe(48)
    return token_plano, hash_refresh_token(token_plano)


def hash_refresh_token(token_plano: str) -> str:
    return hashlib.sha256(token_plano.encode("utf-8")).hexdigest()


# ---------- Dependencia para proteger endpoints ----------

# auto_error=False: si no viene token respondemos con nuestro propio 401
# (mismo mensaje que un token inválido) en vez del error por defecto de FastAPI.
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_usuario_actual(
    token: str | None = Depends(_oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.Usuario:
    """Uso en un endpoint: `usuario: models.Usuario = Depends(get_usuario_actual)`.
    Responde 401 si no hay token, si es inválido/expiró o si la cuenta ya no
    está activa."""
    credenciales_invalidas = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas o expiradas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credenciales_invalidas
    try:
        payload = decodificar_access_token(token)
        id_usuario = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise credenciales_invalidas

    usuario = db.get(models.Usuario, id_usuario)
    if usuario is None or not usuario.activo:
        raise credenciales_invalidas
    return usuario
