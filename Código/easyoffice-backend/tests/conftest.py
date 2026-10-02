"""
Fixtures compartidos para la suite de pruebas del CRM Easy Office.

- SQLite en memoria con StaticPool: una sola conexión compartida entre el
  hilo del test y el hilo donde TestClient ejecuta los endpoints. Sin
  StaticPool, cada conexión nueva a ":memory:" ve una base VACÍA y los
  tests fallan con "no such table".
- PRAGMA foreign_keys=ON: SQLite NO valida claves foráneas por defecto,
  Postgres sí. Activarlo hace que los tests se comporten como producción
  (por ejemplo, con id_usuario_responsable inexistente).
- Tablas creadas y destruidas en cada test → aislamiento total.
"""
import os

# Debe definirse ANTES de importar app.*, porque app/database.py crea el
# engine al importarse. Así nunca se intenta conectar al Postgres de Docker.
os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite://"


@pytest.fixture()
def engine():
    eng = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng, "connect")
    def _activar_fk(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=eng)
    yield eng
    # NO se usa drop_all: las FK cruzadas solicitud_contacto <-> tramite
    # forman un ciclo y, con FK activas, drop_all falla (ver
    # test_drop_all_falla_por_fk_circular). Como la BD vive en memoria,
    # cerrar el engine la destruye por completo.
    eng.dispose()


@pytest.fixture()
def TestingSessionLocal(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def db_session(TestingSessionLocal):
    """Sesión para que los tests inspeccionen/preparen datos directamente."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def seed(db_session):
    """Datos semilla mínimos: un servicio activo, uno inactivo y un usuario."""
    servicio = models.ServicioContratado(
        nombre="Constitución de Sociedad",
        descripcion="Formalización de empresa en un día",
        requiere_revision_humana=False,
        activo=True,
    )
    servicio_inactivo = models.ServicioContratado(
        nombre="Servicio descontinuado",
        activo=False,
    )
    usuario = models.Usuario(nombre="Agente Prueba", email="agente@easyoffice.cl")
    db_session.add_all([servicio, servicio_inactivo, usuario])
    db_session.commit()
    for obj in (servicio, servicio_inactivo, usuario):
        db_session.refresh(obj)
    return {
        "servicio": servicio,
        "servicio_inactivo": servicio_inactivo,
        "usuario": usuario,
    }


@pytest.fixture()
def client(TestingSessionLocal, seed):
    """TestClient con get_db sobreescrito. Cada request usa su propia sesión,
    igual que en producción (no se comparte la sesión del test)."""

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def client_500(client):
    """Cliente que devuelve las excepciones no controladas como HTTP 500
    (como lo vería el frontend) en vez de relanzarlas dentro del test."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers como fixtures (factories) para no repetir payloads en cada test
# ---------------------------------------------------------------------------

@pytest.fixture()
def crear_solicitud(client, seed):
    def _crear(**overrides):
        payload = {
            "nombre": "Juan Pérez",
            "rut": "12345678-9",
            "email": "juan@example.com",
            "telefono": "+56912345678",
            "servicio_id": seed["servicio"].id_servicio,
            "mensaje": "Quiero formalizar mi emprendimiento",
        }
        payload.update(overrides)
        resp = client.post("/api/solicitudes-contacto", json=payload)
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _crear


@pytest.fixture()
def convertir(client):
    def _convertir(id_solicitud, id_usuario_responsable=None):
        body = {}
        if id_usuario_responsable is not None:
            body["id_usuario_responsable"] = id_usuario_responsable
        return client.post(
            f"/api/solicitudes-contacto/{id_solicitud}/convertir", json=body
        )

    return _convertir