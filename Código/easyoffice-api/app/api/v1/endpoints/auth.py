import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status

from app.api.deps import CurrentUsuarioDep, DbDep, limiter
from app.core.config import settings
from app.core.email_utils import normalizar_email
from app.core.security import (
    create_2fa_pending_token,
    create_access_token,
    decode_2fa_pending_token,
    generar_refresh_token,
    generar_totp_secret,
    hash_refresh_token,
    totp_provisioning_uri,
    verificar_totp,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.usuario import Usuario
from app.schemas.auth import AccessToken, TwoFactorRequired, TwoFactorSetupResponse, UsuarioOut
from app.schemas.auth_requests import (
    LoginRequest,
    TwoFactorDisableRequest,
    TwoFactorEnableRequest,
    TwoFactorVerifyRequest,
)

logger = logging.getLogger("easyoffice.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_COOKIE = "refresh_token"
_REFRESH_COOKIE_PATH = "/api/v1/auth"

_CREDENCIALES_INVALIDAS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Email o contraseña incorrectos",
)
_CODIGO_INVALIDO = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Código de verificación inválido o expirado",
)


def _set_refresh_cookie(response: Response, token_plano: str) -> None:
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=token_plano,
        httponly=True,  # inaccesible desde JS -> mitiga robo por XSS
        secure=settings.cookie_secure,  # true en producción (HTTPS obligatorio)
        samesite="lax",  # mitiga CSRF sin romper navegación normal
        max_age=settings.refresh_token_expire_days * 24 * 3600,
        path=_REFRESH_COOKIE_PATH,  # el navegador solo la envía a /auth/*
    )


def _emitir_sesion(db: DbDep, response: Response, usuario: Usuario) -> AccessToken:
    token_plano, token_hash = generar_refresh_token()
    expira_en = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    db.add(RefreshToken(id_usuario=usuario.id_usuario, token_hash=token_hash, expira_en=expira_en))
    db.commit()

    _set_refresh_cookie(response, token_plano)
    access_token = create_access_token(subject=str(usuario.id_usuario), rol=usuario.rol_nombre)
    return AccessToken(access_token=access_token, expires_in_minutes=settings.access_token_expire_minutes)


def _verificar_no_bloqueado(usuario: Usuario | None) -> None:
    if usuario is None or usuario.bloqueado_hasta is None:
        return
    bloqueado_hasta = usuario.bloqueado_hasta.replace(tzinfo=timezone.utc)
    if bloqueado_hasta > datetime.now(timezone.utc):
        minutos_restantes = max(1, int((bloqueado_hasta - datetime.now(timezone.utc)).total_seconds() // 60) + 1)
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Cuenta bloqueada temporalmente. Intenta nuevamente en {minutos_restantes} minuto(s).",
        )


def _registrar_intento_fallido(db: DbDep, usuario: Usuario) -> None:
    """Cuenta tanto contraseñas como códigos 2FA incorrectos contra el MISMO
    contador: si no fuera así, alguien con la contraseña correcta podría
    probar códigos TOTP sin límite (reintentando el login, que no toca este
    contador, entre cada intento de código)."""
    usuario.intentos_fallidos += 1
    recien_bloqueada = usuario.intentos_fallidos >= settings.max_intentos_fallidos
    if recien_bloqueada:
        usuario.bloqueado_hasta = datetime.now(timezone.utc) + timedelta(minutes=settings.bloqueo_minutos)
        logger.warning("cuenta bloqueada por intentos fallidos: id_usuario=%s", usuario.id_usuario)
    db.commit()
    if recien_bloqueada:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Cuenta bloqueada temporalmente. Intenta nuevamente en {settings.bloqueo_minutos} minuto(s).",
        )


def _registrar_intento_exitoso(db: DbDep, usuario: Usuario) -> None:
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.ultimo_login = datetime.now(timezone.utc)
    db.commit()


@router.post("/login")
@limiter.limit("10/minute")
def login(request: Request, datos: LoginRequest, db: DbDep, response: Response) -> AccessToken | TwoFactorRequired:
    email = normalizar_email(datos.email)
    usuario = db.query(Usuario).filter(Usuario.email == email).first()

    # Timing-safe: siempre se hace un hash+verify, exista o no el usuario,
    # para que la respuesta no delate (por latencia) si el email está
    # registrado. verify_password ya usa un hash señuelo si usuario es None.
    password_hash = usuario.password_hash if usuario else None
    password_ok = verify_password(datos.password, password_hash)

    _verificar_no_bloqueado(usuario)

    if usuario is None or not usuario.activo or not password_ok:
        if usuario is not None and usuario.activo:
            _registrar_intento_fallido(db, usuario)
        logger.info("login fallido: email=%s", email)
        raise _CREDENCIALES_INVALIDAS

    if usuario.totp_habilitado:
        # OJO: a propósito NO se resetean intentos_fallidos/ultimo_login acá.
        # El login todavía no terminó -> se completa en /2fa/verify.
        logger.info("login con password OK, pendiente 2FA: id_usuario=%s", usuario.id_usuario)
        return TwoFactorRequired(ticket=create_2fa_pending_token(str(usuario.id_usuario)))

    _registrar_intento_exitoso(db, usuario)
    logger.info("login ok: email=%s id_usuario=%s", email, usuario.id_usuario)
    return _emitir_sesion(db, response, usuario)


@router.post("/2fa/verify")
@limiter.limit("10/minute")
def verificar_2fa(request: Request, datos: TwoFactorVerifyRequest, db: DbDep, response: Response) -> AccessToken:
    try:
        payload = decode_2fa_pending_token(datos.ticket)
    except jwt.PyJWTError:
        raise _CODIGO_INVALIDO

    usuario = db.get(Usuario, int(payload["sub"]))
    if usuario is None or not usuario.activo or not usuario.totp_habilitado or not usuario.totp_secret:
        raise _CODIGO_INVALIDO

    _verificar_no_bloqueado(usuario)

    if not verificar_totp(usuario.totp_secret, datos.codigo):
        _registrar_intento_fallido(db, usuario)
        logger.info("código 2FA incorrecto: id_usuario=%s", usuario.id_usuario)
        raise _CODIGO_INVALIDO

    _registrar_intento_exitoso(db, usuario)
    logger.info("login ok (con 2FA): id_usuario=%s", usuario.id_usuario)
    return _emitir_sesion(db, response, usuario)


@router.post("/2fa/setup")
def setup_2fa(usuario_actual: CurrentUsuarioDep, db: DbDep) -> TwoFactorSetupResponse:
    """Genera un secreto nuevo (reemplaza cualquiera anterior sin confirmar).
    Todavía NO activa 2FA: falta confirmar un código en /2fa/enable."""
    secret = generar_totp_secret()
    usuario_actual.totp_secret = secret
    usuario_actual.totp_habilitado = False
    db.commit()
    return TwoFactorSetupResponse(
        secret=secret,
        provisioning_uri=totp_provisioning_uri(secret, usuario_actual.email),
    )


@router.post("/2fa/enable", status_code=status.HTTP_204_NO_CONTENT)
def enable_2fa(datos: TwoFactorEnableRequest, usuario_actual: CurrentUsuarioDep, db: DbDep) -> None:
    """Confirma que el secreto de /2fa/setup quedó bien cargado en la app
    autenticadora antes de exigirlo en cada login futuro."""
    if not usuario_actual.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Primero llama a /auth/2fa/setup para generar un secreto",
        )
    if not verificar_totp(usuario_actual.totp_secret, datos.codigo):
        raise _CODIGO_INVALIDO
    usuario_actual.totp_habilitado = True
    db.commit()


@router.post("/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
def disable_2fa(datos: TwoFactorDisableRequest, usuario_actual: CurrentUsuarioDep, db: DbDep) -> None:
    if not verify_password(datos.password, usuario_actual.password_hash):
        raise _CREDENCIALES_INVALIDAS
    usuario_actual.totp_habilitado = False
    usuario_actual.totp_secret = None
    db.commit()


@router.post("/refresh")
def refresh(
    db: DbDep,
    response: Response,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> AccessToken:
    sesion_invalida = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sesión inválida, inicia sesión nuevamente",
    )
    if refresh_token is None:
        raise sesion_invalida

    token_hash = hash_refresh_token(refresh_token)
    registro = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()

    if registro is None:
        raise sesion_invalida

    ahora = datetime.now(timezone.utc)

    if registro.revocado:
        # Un refresh token revocado que vuelve a aparecer significa que fue
        # robado y usado después de que el dueño legítimo ya rotó su sesión
        # (o que se está reusando tras logout). Se asume la cuenta
        # comprometida y se cierran TODAS sus sesiones activas.
        logger.warning(
            "reuso de refresh token revocado detectado: id_usuario=%s -> se revocan todas sus sesiones",
            registro.id_usuario,
        )
        db.query(RefreshToken).filter(
            RefreshToken.id_usuario == registro.id_usuario, RefreshToken.revocado.is_(False)
        ).update({"revocado": True})
        db.commit()
        response.delete_cookie(_REFRESH_COOKIE, path=_REFRESH_COOKIE_PATH)
        raise sesion_invalida

    if registro.expira_en.replace(tzinfo=timezone.utc) < ahora:
        raise sesion_invalida

    usuario = db.get(Usuario, registro.id_usuario)
    if usuario is None or not usuario.activo:
        raise sesion_invalida

    # Rotación: el token usado se invalida y se emite uno nuevo. Si alguien
    # más tenía una copia de este token (robado), su próximo intento de
    # refrescar caerá en la rama de arriba y se revocará todo.
    nuevo_token_plano, nuevo_hash = generar_refresh_token()
    nuevo_registro = RefreshToken(
        id_usuario=usuario.id_usuario,
        token_hash=nuevo_hash,
        expira_en=ahora + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(nuevo_registro)
    db.flush()

    registro.revocado = True
    registro.reemplazado_por_id = nuevo_registro.id_refresh_token
    db.commit()

    _set_refresh_cookie(response, nuevo_token_plano)
    access_token = create_access_token(subject=str(usuario.id_usuario), rol=usuario.rol_nombre)
    return AccessToken(access_token=access_token, expires_in_minutes=settings.access_token_expire_minutes)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    db: DbDep,
    response: Response,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> None:
    if refresh_token is not None:
        token_hash = hash_refresh_token(refresh_token)
        db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).update({"revocado": True})
        db.commit()
    response.delete_cookie(_REFRESH_COOKIE, path=_REFRESH_COOKIE_PATH)


@router.get("/me")
def leer_usuario_actual(usuario_actual: CurrentUsuarioDep) -> UsuarioOut:
    return UsuarioOut.model_validate(usuario_actual)
