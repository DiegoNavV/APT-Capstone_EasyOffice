"""Punto de entrada de la API de firma electrónica (FES) para pruebas del CRM.

Fase 0: esqueleto. Solo expone health checks; los módulos de organizaciones,
documentos, firma, webhooks y verificación se agregan en las fases siguientes.
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import health
from app.core.config import get_settings
from app.core.logging_config import configure_logging
from app.core.middleware import RequestIdMiddleware, SecurityHeadersMiddleware

logger = logging.getLogger("firma.api")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        description=(
            "API REST de firma electrónica simple (FES) para pruebas del CRM Easy Office. "
            "No es un Prestador de Servicios de Certificación acreditado: la FEA queda fuera de alcance."
        ),
        version=health.API_VERSION,
        # En producción no se publica la documentación interactiva.
        docs_url=None if settings.app_env == "production" else "/docs",
        redoc_url=None,
        openapi_url=None if settings.app_env == "production" else "/openapi.json",
    )

    # Orden: el último agregado es el más externo.
    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=settings.app_env == "production")
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
        )
    app.add_middleware(RequestIdMiddleware)

    app.include_router(health.router, prefix=settings.api_prefix)

    logger.info("API iniciada (env=%s)", settings.app_env)
    return app


app = create_app()
