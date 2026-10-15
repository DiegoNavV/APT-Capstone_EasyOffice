"""Límite de peticiones de la consulta pública de seguimiento: GET /api/tramites/codigo/{codigo}.

El código de seguimiento es la única credencial del cliente, así que quien pruebe códigos a ciegas debe toparse con un 429 
(30 consultas por minuto por IP).
"""
import pytest

from app import models
from app.seguridad import limiter


def _consultar(client, codigo):
    return client.get(f"/api/tramites/codigo/{codigo}")


@pytest.fixture()
def tramite_de(crear_solicitud, convertir, db_session):
    """Crea un trámite (por el flujo real: solicitud -> convertir) y lo devuelve."""
    def _crear():
        resp = convertir(crear_solicitud()["id_solicitud"])
        assert resp.status_code == 200
        return db_session.get(models.Tramite, resp.json()["id_tramite"])

    return _crear


@pytest.fixture()
def limite_activo():
    # La suite lo desactiva globalmente (ver conftest); aquí se activa y se restaura.
    limiter.reset()
    limiter.enabled = True
    yield
    limiter.enabled = False
    limiter.reset()


def test_pasadas_30_consultas_por_minuto_responde_429(client, tramite_de, limite_activo):
    codigo = tramite_de().codigo_seguimiento
    respuestas = [_consultar(client, codigo).status_code for _ in range(31)]
    assert respuestas[:30] == [200] * 30
    assert respuestas[30] == 429


def test_los_intentos_con_codigo_inexistente_tambien_cuentan(client, limite_activo):
    respuestas = [_consultar(client, "ZZZZZZZZ").status_code for _ in range(31)]
    assert respuestas[:30] == [404] * 30
    assert respuestas[30] == 429


def test_consulta_normal_no_se_ve_afectada(client, tramite_de, limite_activo):
    tramite = tramite_de()
    resp = _consultar(client, tramite.codigo_seguimiento)
    assert resp.status_code == 200
    assert resp.json()["codigo_seguimiento"] == tramite.codigo_seguimiento