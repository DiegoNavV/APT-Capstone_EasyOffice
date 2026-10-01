from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import solicitudes, tramites

app = FastAPI(
    title="CRM Easy Office - API",
    description="Módulo: formulario de contacto -> solicitud -> trámite (seguimiento).",
    version="0.1.0",
)

# Mientras no esté definido el dominio final, se permite el frontend local
# de desarrollo (Vite). Ajustar cuando se despliegue.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(solicitudes.router)
app.include_router(tramites.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}