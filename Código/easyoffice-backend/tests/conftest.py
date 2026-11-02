"""
Fixtures compartidos para la suite de pruebas del CRM Easy Office.

Corre contra una base Postgres REAL (crm_easyoffice_test), no contra SQLite: así los CHECK,
triggers, funciones e índices parciales del esquema real se prueban de verdad, igual que en
producción. Antes la suite creaba las tablas con Base.metadata.create_all() en SQLite en
memoria, que no sabe nada de esas reglas -- un test podía pasar ahí y romper contra el Postgres
real (pasó de verdad: ver tests/test_solicitudes.py, revisión del esquema v4 del 2026-10-31).

- Antes de CADA test se recrea crm_easyoffice_test desde cero (DROP + CREATE DATABASE) y se
  cargan 01_schema.sql + 02_funciones.sql + 03_catalogos.sql: los MISMOS archivos que usa
  Docker en desarrollo/producción, no una reconstrucción aparte en Python que se puede
  desincronizar del esquema real. Aislamiento total entre tests, igual que con la base en
  memoria de antes.
- Requiere un Postgres alcanzable: por defecto el servicio "db" de docker-compose (así corren
  los tests con `docker compose exec backend pytest`), o el que indiquen las variables de
  entorno TEST_DB_HOST / TEST_DB_PORT / TEST_DB_USER / TEST_DB_PASSWORD / TEST_DB_NAME. En CI
  lo levanta un servicio postgres (ver .github/workflows/tests.yml).
"""
import os
import pathlib
from datetime import datetime, timezone

import psycopg2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base, get_db
from app.main import app
from app.seguridad import crear_access_token, hash_password, limiter

DB_INIT_DIR = pathlib.Path(__file__).resolve().parent.parent / "db" / "init"
# En ese orden: tablas, luego funciones/triggers/vistas, luego catálogos fijos (FK de
# tramite/historial_estado/servicio_ofrecido). NO se cargan 04_datos_base.sql ni
# 05_seed_dev.sql: cada test arma sus propios datos con los fixtures de abajo.
_ARCHIVOS_ESQUEMA = ("01_schema.sql", "02_funciones.sql", "03_catalogos.sql")

PG_HOST = os.getenv("TEST_DB_HOST", "db")
PG_PORT = os.getenv("TEST_DB_PORT", "5432")
PG_USER = os.getenv("TEST_DB_USER", "easyoffice")
PG_PASSWORD = os.getenv("TEST_DB_PASSWORD", "easyoffice")
TEST_DB_NAME = os.getenv("TEST_DB_NAME", "crm_easyoffice_test")

# Debe definirse ANTES de que algo más importe app.database, porque ese módulo crea su
# engine al importarse (acá ya se importó arriba, pero se deja explícito por si el orden
# de imports cambia después).
TEST_DATABASE_URL = f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{TEST_DB_NAME}"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

# Contraseña del usuario semilla. El hash se calcula una sola vez (Argon2 es
# lento a propósito) y se reutiliza en cada test.
PASSWORD_PRUEBA = "clave-de-prueba-123"
_PASSWORD_HASH_PRUEBA = hash_password(PASSWORD_PRUEBA)

# Sin esto, los tests que hacen muchos logins chocan con el límite de
# 10/minuto por IP de /api/auth/login.
limiter.enabled = False


def _recrear_base_de_pruebas():
    """DROP + CREATE de la base de pruebas, contra la base de mantención 'postgres' (no se
    puede tocar una base a la que uno está conectado). autocommit=True porque CREATE/DROP
    DATABASE no puede correr dentro de una transacción."""
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, dbname="postgres")
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            # Por si un test anterior se cortó a medias y dejó una conexión colgada.
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (TEST_DB_NAME,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"')
            cur.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        conn.close()


@pytest.fixture()
def engine():
    """Una base Postgres real, recreada desde cero en cada test con los archivos reales de
    db/init/. Aislamiento total entre tests: el próximo test vuelve a recrearla, nunca
    reutiliza lo que este haya dejado (ni siquiera si este test hace drop_all, como
    test_tramites.py::test_drop_all_funciona_sin_ciclo_de_fk)."""
    _recrear_base_de_pruebas()
    eng = create_engine(TEST_DATABASE_URL)
    with eng.begin() as conn:
        for nombre in _ARCHIVOS_ESQUEMA:
            conn.execute(text((DB_INIT_DIR / nombre).read_text(encoding="utf-8")))
    yield eng
    eng.dispose()


def crear_tramite(db, servicio, usuario, rut_cliente=None, nombre_cliente="Cliente Prueba", **campos):
    """Crea un trámite directo en la base, con lo que el esquema exige: cliente (con RUN), la solicitud de
    la que nace y el agente responsable. `campos` va tal cual al trámite (codigo_seguimiento, folio,
    id_sucursal, id_empresa, condiciones, estado_actual...)."""
    if rut_cliente is None:
        rut_cliente = f"{10000000 + db.query(models.Cliente).count() + 1}-1"
    cliente = db.query(models.Cliente).filter_by(rut=rut_cliente).first()
    if cliente is None:
        cliente = models.Cliente(nombre=nombre_cliente, rut=rut_cliente, email="cliente@prueba.cl")
    solicitud = models.SolicitudContacto(
        nombre=nombre_cliente, rut=rut_cliente, email="cliente@prueba.cl", id_servicio=servicio.id_servicio,
        # estado "convertida" exige fecha_cierre (ck_solicitud_cierre); se salta la API porque
        # este helper arma el trámite directo en la base.
        estado="convertida", fecha_cierre=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add_all([cliente, solicitud])
    db.flush()
    campos.setdefault("codigo_seguimiento", f"T{solicitud.id_solicitud:07d}")
    tramite = models.Tramite(
        id_cliente=cliente.id_cliente, id_servicio=servicio.id_servicio,
        id_usuario_responsable=usuario.id_usuario, id_solicitud_origen=solicitud.id_solicitud, **campos
    )
    db.add(tramite)
    db.commit()
    db.refresh(tramite)
    return tramite


def crear_empresa(db, rut_empresa="76123456-0", razon_social="Comercial Prueba SpA",
                  representante_legal="Ana Soto Pérez", rut_representante="12345678-5", **campos):
    """Crea una empresa con su representante legal (obligatorio en el esquema). `campos` usa las mismas
    claves del formulario: giro_principal, email, celular, fecha_escritura (AAAA-MM-DD), notaria,
    domicilio_representante, comuna_representante, region_representante, datos."""
    from datetime import date

    representante = db.query(models.RepresentanteLegal).filter_by(rut=rut_representante).first()
    if representante is None:
        representante = models.RepresentanteLegal(rut=rut_representante, nombre=representante_legal)
    for clave, atributo in (("domicilio_representante", "domicilio"), ("comuna_representante", "comuna"),
                            ("region_representante", "region")):
        if clave in campos:
            setattr(representante, atributo, campos.pop(clave))
    if isinstance(campos.get("fecha_escritura"), str):
        campos["fecha_escritura"] = date.fromisoformat(campos["fecha_escritura"])
    campos.setdefault("datos", {})
    empresa = models.Empresa(
        rut_empresa=rut_empresa, razon_social=razon_social, representante=representante, **campos
    )
    db.add(empresa)
    db.commit()
    db.refresh(empresa)
    return empresa


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
    """Datos semilla mínimos: un servicio activo, uno inactivo y un usuario
    (rol agente, contraseña PASSWORD_PRUEBA)."""
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
    usuario = models.Usuario(
        nombre="Agente Prueba",
        email="agente@easyoffice.cl",
        password_hash=_PASSWORD_HASH_PRUEBA,
        rol=models.Rol(nombre="agente"),
    )
    db_session.add_all([servicio, servicio_inactivo, usuario])
    db_session.commit()
    for obj in (servicio, servicio_inactivo, usuario):
        db_session.refresh(obj)
    return {
        "servicio": servicio,
        "servicio_inactivo": servicio_inactivo,
        "usuario": usuario,
        "password": PASSWORD_PRUEBA,
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
def headers_agente(seed):
    """Header Bearer de la cuenta semilla (mismo token que entrega /api/auth/login)."""
    u = seed["usuario"]
    return {"Authorization": f"Bearer {crear_access_token(u.id_usuario, 'agente')}"}


@pytest.fixture()
def convertir(client, headers_agente):
    """Convierte una solicitud como el agente semilla (convertir exige login y el
    responsable del trámite es siempre quien lo convierte)."""
    def _convertir(id_solicitud):
        return client.post(
            f"/api/solicitudes-contacto/{id_solicitud}/convertir", headers=headers_agente
        )

    return _convertir
