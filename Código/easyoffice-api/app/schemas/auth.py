from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class TwoFactorRequired(BaseModel):
    """Login con password correcta pero cuenta con 2FA activo: todavía no
    hay sesión. El frontend debe pedir el código y llamar a /auth/2fa/verify
    con este ticket."""

    requiere_2fa: bool = True
    ticket: str


class TwoFactorSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_usuario: int
    nombre: str
    email: EmailStr
    rol_nombre: str
    ultimo_login: datetime | None
    totp_habilitado: bool
