"""Pruebas de GET /api/tramites/reporte (conteos agregados para la vista de
Reportes del panel). Exclusivo de administradores -- confirmado con el
cliente, no es un supuesto (ver Resumen_Alcance_Proyecto_EasyOffice.docx)."""
import pytest

from app import models
from app.seguridad import crear_access_token, hash_password

URL = "/api/tramites/reporte"


@pytest.fixture()
def headers_admin(db_session, seed):
    admin = models.Usuario(
        nombre="Admin Prueba",
        email="admin.reportes@easyoffice.cl",
        password_hash=hash_password("otra-clave-123"),
        rol=models.Rol(nombre="administrador"),
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return {"Authorization": f"Bearer {crear_access_token(admin.id_usuario, 'administrador')}"}


@pytest.fixture()
def hacer_tramite(crear_solicitud, convertir, db_session):
    """Crea una solicitud y la convierte en trámite (responsable = el agente de la sesión)."""
    contador = {"n": 0}

    def _hacer(**overrides):
        contador["n"] += 1
        rut = overrides.pop("rut", f"{10000000 + contador['n']}-{contador['n'] % 10}")
        sol = crear_solicitud(rut=rut, **overrides)
        resp = convertir(sol["id_solicitud"])
        assert resp.status_code == 200, resp.text
        return resp.json()

    return _hacer


def _set_estado(db_session, id_tramite, estado):
    t = db_session.get(models.Tramite, id_tramite)
    t.estado_actual = estado
    db_session.commit()


class TestAcceso:
    def test_sin_token_401(self, client):
        assert client.get(URL).status_code == 401

    def test_token_invalido_401(self, client):
        assert client.get(URL, headers={"Authorization": "Bearer basura"}).status_code == 401

    def test_agente_no_ve_reportes(self, client, headers_agente):
        """El panel usa `puede_ver` (no un 403) para poder mostrar solo un aviso, igual que /api/plantillas/configuracion."""
        resp = client.get(URL, headers=headers_agente)
        assert resp.status_code == 200
        datos = resp.json()
        assert datos["puede_ver"] is False
        assert datos["total"] == 0
        assert datos["por_estado"] == []
        assert datos["por_servicio"] == []
        assert datos["por_agente"] == []


class TestSinDatos:
    def test_sin_tramites_queda_vacio(self, client, headers_admin):
        """La base semilla no tiene trámites: el panel debe mostrar el aviso de "sin suficiente información"."""
        resp = client.get(URL, headers=headers_admin)
        assert resp.status_code == 200
        datos = resp.json()
        assert datos["puede_ver"] is True
        assert datos["total"] == 0
        assert datos["por_estado"] == []
        assert datos["por_servicio"] == []
        assert datos["por_agente"] == []


class TestConDatos:
    def test_cuenta_por_estado_servicio_y_agente(self, client, headers_admin, hacer_tramite, db_session, seed):
        t1 = hacer_tramite()
        t2 = hacer_tramite()
        t3 = hacer_tramite()
        _set_estado(db_session, t1["id_tramite"], "generado")
        _set_estado(db_session, t2["id_tramite"], "generado")
        _set_estado(db_session, t3["id_tramite"], "firmado")

        resp = client.get(URL, headers=headers_admin)
        assert resp.status_code == 200
        datos = resp.json()
        assert datos["puede_ver"] is True
        assert datos["total"] == 3

        por_estado = {fila["etiqueta"]: fila["cantidad"] for fila in datos["por_estado"]}
        assert por_estado == {"generado": 2, "firmado": 1}

        por_servicio = {fila["etiqueta"]: fila["cantidad"] for fila in datos["por_servicio"]}
        assert por_servicio == {seed["servicio"].nombre: 3}

        por_agente = {fila["etiqueta"]: fila["cantidad"] for fila in datos["por_agente"]}
        assert por_agente == {seed["usuario"].nombre: 3}
