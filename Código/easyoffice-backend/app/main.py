from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.routers import auth, solicitudes, tramites
from app.seguridad import limiter

app = FastAPI(
    title="CRM Easy Office - API",
    description="Login del panel + módulo: formulario de contacto -> solicitud -> trámite (seguimiento).",
    version="0.1.0",
)

# Límite de peticiones por IP (ver @limiter.limit en app/routers/auth.py).
# Si se supera, responde 429 Too Many Requests.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Mientras no esté definido el dominio final, se permite el frontend local
# de desarrollo (Vite). Ajustar cuando se despliegue.
# allow_credentials=True es necesario para que el navegador mande y reciba la
# cookie httpOnly del refresh token; por eso allow_origins NO puede ser "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        # easyoffice-frontend servido por nginx en docker-compose (ver
        # Dockerfile y docker-compose.yml de easyoffice-frontend).
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(solicitudes.router)
app.include_router(tramites.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
