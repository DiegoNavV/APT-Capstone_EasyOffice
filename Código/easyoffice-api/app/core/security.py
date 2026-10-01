import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
import pyotp
from passlib.context import CryptContext

from app.core.config import settings

# Argon2id es la recomendación #1 de OWASP para almacenamiento de contraseñas
# (resistente a ataques por GPU/ASIC, a diferencia de bcrypt/PBKDF2).
# Parámetros mínimos recomendados por OWASP: m=19456 KiB, t=2, p=1.
_pwd_context = CryptContext(
    schemes=["argon2"],
    argon2__type="ID",
    argon2__memory_cost=19456,
    argon2__time_cost=2,
    argon2__parallelism=1,
)

# Hash "señuelo" precalculado: se usa cuando el email no existe, para que
# verificar login con un usuario inexistente tome el mismo tiempo que con uno
# real y así no se pueda enumerar cuentas midiendo la latencia de la respuesta.
_DUMMY_HASH = _pwd_context.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    return _pwd_context.verify(password, password_hash or _DUMMY_HASH)


def create_access_token(subject: str, rol: str) -> str:
    ahora = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "rol": rol,
        "type": "access",
        "iat": ahora,
        "exp": ahora + timedelta(minutes=settings.access_token_expire_minutes),
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Tipo de token incorrecto")
    return payload


def create_2fa_pending_token(subject: str) -> str:
    """Token intermedio de 5 min: certifica que la contraseña ya fue
    validada, pero NO es un access token (no sirve para entrar a nada hasta
    que se confirme el segundo factor en /auth/2fa/verify)."""
    ahora = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": "2fa_pending",
        "iat": ahora,
        "exp": ahora + timedelta(minutes=5),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_2fa_pending_token(token: str) -> dict:
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != "2fa_pending":
        raise jwt.InvalidTokenError("Tipo de token incorrecto")
    return payload


def generar_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, email: str) -> str:
    """URI otpauth:// que cualquier app autenticadora (Google Authenticator,
    Authy, etc.) convierte en QR o acepta pegada directamente."""
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name="Easy Office CRM")


def verificar_totp(secret: str, codigo: str) -> bool:
    # valid_window=1: tolera 1 paso de 30s de desfase de reloj (antes/después).
    return pyotp.totp.TOTP(secret).verify(codigo, valid_window=1)


def generar_refresh_token() -> tuple[str, str]:
    """Devuelve (token_plano, hash). Solo el hash se guarda en la base de datos.

    El token en sí nunca se persiste: si la base de datos se filtra, no sirve
    para robar sesiones (igual que una contraseña, pero con SHA-256 porque es
    un valor aleatorio de alta entropía, no algo adivinable por fuerza bruta).
    """
    token_plano = secrets.token_urlsafe(48)
    return token_plano, hash_refresh_token(token_plano)


def hash_refresh_token(token_plano: str) -> str:
    return hashlib.sha256(token_plano.encode("utf-8")).hexdigest()
