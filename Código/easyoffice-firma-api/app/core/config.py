"""Configuración de la API, leída solo desde variables de entorno.

Reglas:
- Ningún secreto vive en el código. En desarrollo hay valores por defecto
  cómodos; en producción (APP_ENV=production) la app se niega a arrancar si
  algún secreto sigue con su valor de desarrollo.
- Los plazos y requisitos legales son parámetros, marcados "VALIDAR CON ABOGADO".
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valor marcador para secretos de desarrollo. Si llega a producción, se rechaza.
DEV_SECRET = "dev-inseguro-cambiar"
# Clave maestra SOLO para desarrollo: hex válido de 64 caracteres, para que el
# cifrado AES-256-GCM funcione igual que en producción. Es pública (está en el
# repo), por eso en producción se rechaza.
DEV_MASTER_KEY_HEX = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"


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
    master_key_hex: str = DEV_MASTER_KEY_HEX
    # Pimienta para el hash de API keys y tokens de firma.
    token_pepper: str = DEV_SECRET

    # ---------- Acceso de clientes de la API (CRM) ----------
    # API keys aceptadas, separadas por coma. Versión de pruebas: una clave por
    # cliente definida por variable de entorno. (La gestión completa de
    # organizaciones y API keys con hash y rotación es la Fase 1.)
    api_keys: str = "fk_test_dev-inseguro-cambiar"

    # ---------- Firma y documentos ----------
    # Nombre que firma automáticamente ("firma desatendida"). VALIDAR CON ABOGADO.
    organization_signer_name: str = "Easy Office SpA"
    organization_signer_rut: str = ""
    # Carpeta donde se guarda (o se crea la primera vez) el certificado de la
    # plataforma para el sello PAdES. NO es un certificado de un PSC acreditado.
    certs_dir: str = "/app/certs"
    max_pdf_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    # URL pública de la API, para imprimir el enlace de verificación en la hoja de evidencias.
    public_base_url: str = "http://localhost:8100"

    # ---------- Webhooks ----------
    # Secreto para firmar los webhooks (HMAC-SHA256). El CRM usa el mismo valor para verificarlos.
    webhook_secret: str = DEV_SECRET
    # Hosts a los que se permite enviar webhooks (evita SSRF). Separados por coma.
    webhook_allowed_hosts: str = "backend,localhost,127.0.0.1,host.docker.internal"
    webhook_max_attempts: int = Field(default=6, ge=1, le=20)

    # ---------- Parámetros legales (VALIDAR CON ABOGADO) ----------
    # Años de retención de documentos y evidencias.
    retention_years: int = Field(default=6, ge=1)
    # Días por defecto antes de que un documento sin firmar expire.
    document_default_expiration_days: int = Field(default=30, ge=1)

    @field_validator("master_key_hex")
    @classmethod
    def _master_key_formato(cls, v: str) -> str:
        """En TODOS los entornos: 32 bytes en hex (64 caracteres)."""
        v = v.strip().lower()
        if len(v) != 64:
            raise ValueError("MASTER_KEY_HEX debe tener 64 caracteres hex (32 bytes).")
        try:
            bytes.fromhex(v)
        except ValueError as exc:
            raise ValueError("MASTER_KEY_HEX no es hexadecimal válido.") from exc
        return v

    @model_validator(mode="after")
    def _validar_secretos_en_produccion(self) -> "Settings":
        if self.app_env != "production":
            return self
        con_valor_dev = [
            nombre
            for nombre in ("s3_secret_key", "token_pepper", "webhook_secret")
            if getattr(self, nombre) == DEV_SECRET
        ]
        if self.master_key_hex == DEV_MASTER_KEY_HEX:
            con_valor_dev.append("master_key_hex")
        if con_valor_dev:
            raise ValueError(
                "En producción estos secretos deben definirse por variable de entorno: "
                + ", ".join(sorted(con_valor_dev))
            )
        if any("dev-inseguro" in k for k in self.api_key_list) or not self.api_key_list:
            raise ValueError("En producción API_KEYS debe definirse con claves propias.")
        return self

    @property
    def api_key_list(self) -> list[str]:
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]

    @property
    def webhook_allowed_host_list(self) -> list[str]:
        return [h.strip().lower() for h in self.webhook_allowed_hosts.split(",") if h.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
