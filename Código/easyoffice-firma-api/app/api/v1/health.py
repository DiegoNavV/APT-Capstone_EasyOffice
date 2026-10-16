"""Health checks.

  GET /api/v1/health        vida del proceso (no toca dependencias)
  GET /api/v1/health/ready  la API puede atender: base de datos, Redis y MinIO
"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.services.health import Check, get_checks, run_checks

router = APIRouter(prefix="/health", tags=["health"])

API_VERSION = "0.1.0"


@router.get("")
def liveness() -> dict:
    return {"status": "ok", "version": API_VERSION, "env": get_settings().app_env}


@router.get("/ready")
def readiness(checks: dict[str, Check] = Depends(get_checks)) -> JSONResponse:
    todo_ok, resultados = run_checks(checks)
    return JSONResponse(
        status_code=200 if todo_ok else 503,
        content={"status": "ok" if todo_ok else "degraded", "checks": resultados},
    )
