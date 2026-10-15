"""Configuración de la API, leída solo desde variables de entorno.

Reglas:
- Ningún secreto vive en el código. En desarrollo hay valores por defecto
  cómodos; en producción (APP_ENV=production) la app se niega a arrancar si
  algún secreto sigue con su valor de desarrollo.
- Los plazos y requisitos legales son parámetros, marcados "VALIDAR CON ABOGADO".
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valor marcador para secretos de desarrollo. Si llega a producción, se rechaza.
DEV_SECRET = "dev-inseguro-cambiar"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---------- General ----------
    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "EasyOffice Firma API"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    # Orígenes permitidos para CORS (separados por coma). La API se consume
    # servidor a servidor, así que por defecto no se permite ninguno.
    cors_origins: str = ""
    # IPs de proxies confiables para X-Forwarded-For. La IP del firmante es
    # evidencia legal: nunca aceptar ese header desde cualquier origen.
    forwarded_allow_ips: str = "127.0.0.1"
    # Segundos máximos de espera de cada chequeo de dependencias.
    dependency_timeout_seconds: int = Field(default=3, ge=1, le=30)

    # ---------- Base de datos ----------
    database_url: str = "postgresql+psycopg2://firma:firma@db:5432/firma_api"

    # ---------- Redis (rate limit y colas) ----------
    redis_url: str = "redis://redis:6379/0"

    # ---------- Almacenamiento S3/MinIO ----------
    s3_endpoint: str = "minio:9000"
    s3_access_key: str = "firma-minio"
    s3_secret_key: str = DEV_SECRET
    s3_bucket_documents: str = "firma-documents"
    s3_secure: bool = False

    # ---------- Correo (OTP). En desarrollo va a Mailpit ----------
    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    smtp_from: str = "no-responder@firma.local"

    # ---------- Secretos de la plataforma ----------
    # Clave maestra para cifrar secretos en reposo (AES-256-GCM): 32 bytes en
    # hex (64 caracteres). Generar con: python -c "import secrets;print(secrets.token_hex(32))"
    master_key_hex: str = DEV_SECRET
    # Pimienta para el hash de API keys y tokens de firma.
    token_pepper: str = DEV_SECRET

    # ---------- Parámetros legales (VALIDAR CON ABOGADO) ----------
    # Años de retención de documentos y evidencias.
    retention_years: int = Field(default=6, ge=1)
    # Días por defecto antes de que un documento sin firmar expire.
    document_default_expiration_days: int = Field(default=30, ge=1)

    @model_validator(mode="after")
    def _validar_secretos_en_produccion(self) -> "Settings":
        if self.app_env != "production":
            return self
        con_valor_dev = [
            nombre
            for nombre in ("s3_secret_key", "master_key_hex", "token_pepper")
            if getattr(self, nombre) == DEV_SECRET
        ]
        if con_valor_dev:
            raise ValueError(
                "En producción estos secretos deben definirse por variable de entorno: "
                + ", ".join(sorted(con_valor_dev))
            )
        if len(self.master_key_hex) != 64:
            raise ValueError("MASTER_KEY_HEX debe tener 64 caracteres hex (32 bytes).")
        try:
            bytes.fromhex(self.master_key_hex)
        except ValueError as exc:
            raise ValueError("MASTER_KEY_HEX no es hexadecimal válido.") from exc
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
