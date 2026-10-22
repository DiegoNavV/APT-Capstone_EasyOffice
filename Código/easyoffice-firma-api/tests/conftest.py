"""Fixtures compartidos.

Las variables de entorno se fijan ANTES de importar `app`, porque la
configuración y el engine se crean al importar. Los tests usan SQLite en
memoria y almacenamiento en memoria: nunca tocan Postgres, Redis ni MinIO reales.
"""
import os
import tempfile

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["API_KEYS"] = "fk_test_clave-de-pruebas,fk_test_otro-cliente"
os.environ["WEBHOOK_SECRET"] = "secreto-de-pruebas"
os.environ["CERTS_DIR"] = tempfile.mkdtemp(prefix="firma-certs-")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402,F401  (registra las tablas en Base.metadata)
from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import webhooks  # noqa: E402
from app.services.health import get_checks  # noqa: E402
from app.services.storage import MemoryStorage, get_storage  # noqa: E402

from helpers import API_KEY, hacer_pdf  # noqa: E402


@pytest.fixture(autouse=True)
def _tablas():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture()
def storage():
    almacen = MemoryStorage()
    app.dependency_overrides[get_storage] = lambda: almacen
    yield almacen
    app.dependency_overrides.pop(get_storage, None)


@pytest.fixture(autouse=True)
def encolados(monkeypatch):
    """Reemplaza la cola de Celery: guarda los ids de webhook que se habrían encolado."""
    lista: list[str] = []
    monkeypatch.setattr(webhooks, "enqueue", lambda delivery_id: lista.append(delivery_id))
    return lista


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth():
    return {"X-API-Key": API_KEY}


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


@pytest.fixture()
def pdf_bytes():
    return hacer_pdf()
