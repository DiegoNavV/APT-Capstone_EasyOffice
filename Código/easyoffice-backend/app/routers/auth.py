"""Login del panel interno (agentes y administradores).

  POST /api/auth/login    correo + contraseña -> access token (+ cookie con refresh token)
  POST /api/auth/refresh  cookie del refresh token -> access token nuevo (rota el refresh token)
  POST /api/auth/logout   revoca el refresh token de la cookie
  GET  /api/auth/me       datos del usuario dueño del access token

Las piezas de bajo nivel (hash de contraseñas, JWT, dependencia
get_usuario_actual) están en app/seguridad.py.
"""
import logging
from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.seguridad import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    BLOQUEO_MINUTOS,
    COOKIE_SECURE,
    MAX_INTENTOS_FALLIDOS,
    REFRESH_TOKEN_EXPIRE_DAYS,
    ahora_utc,
    crear_access_token,
    generar_refresh_token,
    get_usuario_actual,
    hash_refresh_token,
    limiter,
    verificar_password,
)

logger = logging.getLogger("easyoffice.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])

_REFRESH_COOKIE = "refresh_token"
# El navegador solo manda la cookie a /api/auth/* (refresh y logout), no a
# todos los endpoints de la API.
_REFRESH_COOKIE_PATH = "/api/auth"

# Mismo mensaje si el email no existe o si la contraseña es incorrecta, para
# no revelar qué correos están registrados.
_CREDENCIALES_INVALIDAS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Email o contraseña incorrectos",
)
_SESION_INVALIDA = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Sesión inválida, inicia sesión nuevamente",
)


# ---------- Helpers ----------

def _emitir_sesion(
    db: Session,
    response: Response,
    usuario: models.Usuario,
    reemplaza: models.RefreshToken | None = None,
) -> schemas.AccessToken:
    """Crea un refresh token nuevo: guarda su hash en la BD, lo manda en una
    cookie httpOnly y devuelve el access token en el JSON.

    `reemplaza` (solo desde /refresh): el token anterior, que queda revocado y
    enlazado al nuevo en la misma transacción."""
    token_plano, token_hash = generar_refresh_token()
    nuevo = models.RefreshToken(
        id_usuario=usuario.id_usuario,
        token_hash=token_hash,
        expira_en=ahora_utc() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(nuevo)
    if reemplaza is not None:
        db.flush()  # asigna nuevo.id_refresh_token sin cerrar la transacción
        reemplaza.revocado = True
        reemplaza.reemplazado_por_id = nuevo.id_refresh_token
    db.commit()

    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=token_plano,
        httponly=True,  # JavaScript no puede leerla -> un XSS no la puede robar
        secure=COOKIE_SECURE,  # true en producción (solo viaja por HTTPS)
        samesite="lax",  # mitiga CSRF sin romper la navegación normal
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path=_REFRESH_COOKIE_PATH,
    )
    return schemas.AccessToken(
        access_token=crear_access_token(usuario.id_usuario, usuario.rol_nombre),
        expires_in_minutes=ACCESS_TOKEN_EXPIRE_MINUTES,
    )


def _verificar_no_bloqueado(usuario: models.Usuario | None) -> None:
    """Responde 423 si la cuenta está bloqueada por demasiados intentos fallidos."""
    if usuario is None or usuario.bloqueado_hasta is None:
        return
    restante = usuario.bloqueado_hasta - ahora_utc()
    if restante.total_seconds() > 0:
        minutos = int(restante.total_seconds() // 60) + 1
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Cuenta bloqueada temporalmente. Intenta nuevamente en {minutos} minuto(s).",
        )


def _registrar_intento_fallido(db: Session, usuario: models.Usuario) -> None:
    """Suma un intento fallido y, si se llegó al máximo, bloquea la cuenta."""
    usuario.intentos_fallidos += 1
    recien_bloqueada = usuario.intentos_fallidos >= MAX_INTENTOS_FALLIDOS
    if recien_bloqueada:
        usuario.bloqueado_hasta = ahora_utc() + timedelta(minutes=BLOQUEO_MINUTOS)
        logger.warning("cuenta bloqueada por intentos fallidos: id_usuario=%s", usuario.id_usuario)
    db.commit()
    if recien_bloqueada:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Cuenta bloqueada temporalmente. Intenta nuevamente en {BLOQUEO_MINUTOS} minuto(s).",
        )


def _registrar_intento_exitoso(db: Session, usuario: models.Usuario) -> None:
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.ultimo_login = ahora_utc()
    db.commit()


# ---------- Endpoints ----------

@router.post("/login", response_model=schemas.AccessToken)
@limiter.limit("10/minute")  # por IP; además está el bloqueo por cuenta
def login(request: Request, response: Response, datos: schemas.LoginRequest, db: Session = Depends(get_db)):
    usuario = db.query(models.Usuario).filter(models.Usuario.email == datos.email).first()

    # Se verifica la contraseña SIEMPRE, exista o no el usuario (contra un hash
    # señuelo si no existe), para que el tiempo de respuesta no delate si el
    # email está registrado.
    password_ok = verificar_password(datos.password, usuario.password_hash if usuario else None)

    _verificar_no_bloqueado(usuario)

    if usuario is None or not usuario.activo or not password_ok:
        if usuario is not None and usuario.activo:
            _registrar_intento_fallido(db, usuario)
        logger.info("login fallido: email=%s", datos.email)
        raise _CREDENCIALES_INVALIDAS

    _registrar_intento_exitoso(db, usuario)
    logger.info("login ok: id_usuario=%s", usuario.id_usuario)
    return _emitir_sesion(db, response, usuario)


@router.post("/refresh", response_model=schemas.AccessToken)
def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    if refresh_token is None:
        raise _SESION_INVALIDA

    registro = (
        db.query(models.RefreshToken)
        .filter(models.RefreshToken.token_hash == hash_refresh_token(refresh_token))
        .first()
    )
    if registro is None:
        raise _SESION_INVALIDA

    if registro.revocado:
        # Un token ya revocado que vuelve a aparecer significa que alguien lo
        # copió y lo usó después de que el dueño ya lo rotó (o tras un logout).
        # Se asume la cuenta comprometida y se cierran TODAS sus sesiones.
        logger.warning("reuso de refresh token revocado: id_usuario=%s", registro.id_usuario)
        db.query(models.RefreshToken).filter(
            models.RefreshToken.id_usuario == registro.id_usuario,
            models.RefreshToken.revocado.is_(False),
        ).update({"revocado": True})
        db.commit()
        response.delete_cookie(_REFRESH_COOKIE, path=_REFRESH_COOKIE_PATH)
        raise _SESION_INVALIDA

    if registro.expira_en < ahora_utc():
        raise _SESION_INVALIDA

    usuario = db.get(models.Usuario, registro.id_usuario)
    if usuario is None or not usuario.activo:
        raise _SESION_INVALIDA

    # Rotación: el token usado se revoca y se emite uno nuevo enlazado a él.
    return _emitir_sesion(db, response, usuario, reemplaza=registro)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    if refresh_token is not None:
        db.query(models.RefreshToken).filter(
            models.RefreshToken.token_hash == hash_refresh_token(refresh_token)
        ).update({"revocado": True})
        db.commit()
    response.delete_cookie(_REFRESH_COOKIE, path=_REFRESH_COOKIE_PATH)


@router.get("/me", response_model=schemas.UsuarioOut)
def leer_usuario_actual(usuario: models.Usuario = Depends(get_usuario_actual)):
    return usuario
