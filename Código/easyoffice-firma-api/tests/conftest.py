"""Fixtures compartidos.

Las variables de entorno se fijan ANTES de importar `app`, porque la
configuración y el engine se crean al importar. Los tests usan SQLite en
memoria y nunca tocan Postgres, Redis ni MinIO reales.
"""
import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["LOG_LEVEL"] = "WARNING"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services.health import get_checks  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def fake_checks():
    """Reemplaza los chequeos reales por funciones controladas por el test."""

    def _aplicar(**estados: bool):
        checks = {
            nombre: (lambda ok=ok: (ok, "ok" if ok else "ConnectionError"))
            for nombre, ok in estados.items()
        }
        app.dependency_overrides[get_checks] = lambda: checks

    return _aplicar
