import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.deps import limiter
from app.api.v1.router import api_router
from app.core.config import settings

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="CRM Easy Office — API")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# allow_credentials=True es necesario para que el navegador mande la cookie
# httpOnly del refresh token; por eso allowed_origins NO puede ser "*"
# (los navegadores rechazan esa combinación).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if settings.cookie_secure:
        # Solo tiene sentido si la API ya corre detrás de HTTPS (producción).
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


app.include_router(api_router)


@app.exception_handler(Exception)
async def error_generico(request: Request, exc: Exception) -> JSONResponse:
    # Nunca devolver el detalle interno/stacktrace al cliente.
    logging.getLogger("easyoffice.error").exception("error no manejado")
    return JSONResponse(status_code=500, content={"detail": "Error interno del servidor"})


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
