"""Chequeos de dependencias para /health/ready.

Cada chequeo devuelve (ok, detalle). El detalle nunca incluye credenciales ni
URLs completas: solo el tipo de error.
"""
from collections.abc import Callable

from sqlalchemy import text

from app.core.config import get_settings

Check = Callable[[], tuple[bool, str]]


def check_database() -> tuple[bool, str]:
    from app.db.session import engine

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:  # noqa: BLE001 - se informa el tipo, no el mensaje
        return False, type(exc).__name__


def check_redis() -> tuple[bool, str]:
    try:
        import redis

        timeout = get_settings().dependency_timeout_seconds
        cliente = redis.Redis.from_url(
            get_settings().redis_url, socket_timeout=timeout, socket_connect_timeout=timeout
        )
        cliente.ping()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, type(exc).__name__


def check_storage() -> tuple[bool, str]:
    try:
        from app.core.storage import get_storage_client

        if not get_storage_client().bucket_exists(get_settings().s3_bucket_documents):
            return False, "bucket_missing"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, type(exc).__name__


DEFAULT_CHECKS: dict[str, Check] = {
    "database": check_database,
    "redis": check_redis,
    "storage": check_storage,
}


def get_checks() -> dict[str, Check]:
    """Dependencia de FastAPI; los tests la reemplazan por chequeos falsos."""
    return DEFAULT_CHECKS


def run_checks(checks: dict[str, Check]) -> tuple[bool, dict[str, str]]:
    resultados: dict[str, str] = {}
    todo_ok = True
    for nombre, chequeo in checks.items():
        ok, detalle = chequeo()
        resultados[nombre] = detalle
        todo_ok = todo_ok and ok
    return todo_ok, resultados
