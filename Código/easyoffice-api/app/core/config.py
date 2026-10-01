from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+psycopg://easyoffice:easyoffice@localhost:5432/crm_easyoffice"

    jwt_secret_key: str = "cambiar-esto-en-cada-entorno"
    jwt_algorithm: str = "HS256"
    # 90 min: pensado para que el frontend lo renueve solo en segundo plano
    # durante una jornada de 8-10h vía /auth/refresh, no para que dure la
    # jornada completa él mismo (ver app/api/v1/endpoints/auth.py).
    access_token_expire_minutes: int = 90
    refresh_token_expire_days: int = 7

    max_intentos_fallidos: int = 5
    bloqueo_minutos: int = 15

    allowed_origins: str = "http://localhost:5173,http://localhost:5174"
    cookie_secure: bool = False

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


settings = Settings()
