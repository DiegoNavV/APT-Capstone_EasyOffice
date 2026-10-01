from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    # Solo se valida longitud acá; la fortaleza real la da el hash (Argon2id).
    # Exigir "complejidad" (mayúsculas/símbolos) en vez de longitud está
    # desaconsejado por NIST/OWASP: empuja a patrones predecibles (Clave1!).
    password: str = Field(min_length=1, max_length=128)


class TwoFactorVerifyRequest(BaseModel):
    ticket: str
    codigo: str = Field(pattern=r"^\d{6}$")


class TwoFactorEnableRequest(BaseModel):
    codigo: str = Field(pattern=r"^\d{6}$")


class TwoFactorDisableRequest(BaseModel):
    # Reautenticación (step-up): apagar 2FA exige la contraseña de nuevo,
    # para que una sesión robada (access token filtrado) no pueda desactivarlo.
    password: str = Field(min_length=1, max_length=128)
