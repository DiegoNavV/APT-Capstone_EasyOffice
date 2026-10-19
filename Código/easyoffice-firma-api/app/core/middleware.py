"""Middlewares transversales: id de petición, log de acceso y headers de seguridad."""
import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging_config import request_id_var

# Solo se acepta un X-Request-ID entrante si es corto y seguro; si no, se genera uno.
_REQUEST_ID_VALIDO = re.compile(r"^[A-Za-z0-9-]{8,64}$")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
    # La API devuelve JSON y PDF; no necesita cargar nada.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cache-Control": "no-store",
}

# HSTS solo tiene sentido detrás de HTTPS (producción).
HSTS_VALUE = "max-age=31536000; includeSubDomains"


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        entrante = request.headers.get("X-Request-ID", "")
        request_id = entrante if _REQUEST_ID_VALIDO.match(entrante) else str(uuid.uuid4())
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response


_access_logger = logging.getLogger("firma.access")


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Log de acceso propio: método, ruta SIN query string, estado y duración.

    Reemplaza al log de acceso de uvicorn (desactivado con --no-access-log), que
    escribía la URL completa sin pasar por el filtro de datos sensibles."""

    async def dispatch(self, request: Request, call_next) -> Response:
        inicio = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            _access_logger.info(
                "%s %s %s %.0fms",
                request.method,
                request.url.path,  # nunca request.url completa: la query puede traer datos privados
                status_code,
                (time.perf_counter() - inicio) * 1000,
            )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, enable_hsts: bool = False):
        super().__init__(app)
        self.enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        # La documentación OpenAPI (/docs) necesita cargar JS y CSS.
        es_docs = request.url.path in ("/docs", "/redoc") or request.url.path.startswith("/docs/")
        for nombre, valor in SECURITY_HEADERS.items():
            if es_docs and nombre == "Content-Security-Policy":
                continue
            response.headers.setdefault(nombre, valor)
        if self.enable_hsts:
            response.headers.setdefault("Strict-Transport-Security", HSTS_VALUE)
        return response
