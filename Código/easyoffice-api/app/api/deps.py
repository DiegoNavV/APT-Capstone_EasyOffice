from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.usuario import Usuario

# "auto_error=False": si no hay token devolvemos nuestro propio 401 genérico
# en vez de que fastapi lo haga, para mantener el mismo formato de error.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

limiter = Limiter(key_func=get_remote_address)

DbDep = Annotated[Session, Depends(get_db)]


def get_current_usuario(token: Annotated[str | None, Depends(oauth2_scheme)], db: DbDep) -> Usuario:
    credenciales_invalidas = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas o expiradas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credenciales_invalidas
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise credenciales_invalidas

    id_usuario = payload.get("sub")
    if id_usuario is None:
        raise credenciales_invalidas

    usuario = db.get(Usuario, int(id_usuario))
    if usuario is None or not usuario.activo:
        raise credenciales_invalidas
    return usuario


CurrentUsuarioDep = Annotated[Usuario, Depends(get_current_usuario)]
