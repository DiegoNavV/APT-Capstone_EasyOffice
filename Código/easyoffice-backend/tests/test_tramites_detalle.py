"""
Pruebas de GET /api/tramites/{id} (detalle), POST /api/tramites/{id}/cancelar y
POST /api/tramites/{id}/reenviar-firma -- mockup Figma, pantalla "4 · Detalle de trámite
(firma + seguimiento)". Los tres requieren login.
"""
import pytest

from app import models
from tests.conftest import crear_tramite


def _url(id_tramite):
    return f"/api/tramites/{id_tramite}"


class TestDetalle:

    def test_sin_token_401(self, client, seed, db_session):
        t = crear_tramite(db_session, seed["servicio"], seed["usuario"])
        assert client.get(_url(t.id_tramite)).status_code == 401

    def test_no_encontrado_404(self, client, headers_agente):
        assert client.get(_url(999999), headers=headers_agente).status_code == 404

    def test_forma_con_historial(self, client, headers_agente, seed, db_session):
        t = crear_tramite(db_session, seed["servicio"], seed["usuario"])
        db_session.add(models.HistorialEstado(
            id_tramite=t.id_tramite, estado="esperando_datos", origen="agente",
            comentario="Trámite generado al confirmar el pago.", id_usuario=seed["usuario"].id_usuario,
        ))
        db_session.commit()

        datos = client.get(_url(t.id_tramite), headers=headers_agente).json()

        assert datos["id_tramite"] == t.id_tramite
        assert datos["codigo_seguimiento"] == t.codigo_seguimiento
        assert datos["estado_actual"] == "esperando_datos"
        assert datos["nombre_agente"] == "Agente Prueba"
        assert datos["tiene_documento"] is False
        assert len(datos["historial"]) == 1
        assert datos["historial"][0]["estado"] == "esperando_datos"
        assert datos["historial"][0]["origen"] == "agente"
        assert datos["historial"][0]["comentario"] == "Trámite generado al confirmar el pago."
        assert datos["historial"][0]["nombre_usuario"] == "Agente Prueba"

    def test_sin_historial_no_revienta(self, client, headers_agente, seed, db_session):
        t = crear_tramite(db_session, seed["servicio"], seed["usuario"])
        resp = client.get(_url(t.id_tramite), headers=headers_agente)
        assert resp.status_code == 200
        assert resp.json()["historial"] == []

    def test_historial_queda_en_orden(self, client, headers_agente, seed, db_session):
        t = crear_tramite(db_session, seed["servicio"], seed["usuario"])
        db_session.add_all([
            models.HistorialEstado(
                id_tramite=t.id_tramite, estado="esperando_datos", origen="agente",
                id_usuario=seed["usuario"].id_usuario,
            ),
            models.HistorialEstado(id_tramite=t.id_tramite, estado="procesando_firma", origen="cliente"),
        ])
        db_session.commit()

        historial = client.get(_url(t.id_tramite), headers=headers_agente).json()["historial"]

        assert [h["estado"] for h in historial] == ["esperando_datos", "procesando_firma"]


class TestCancelar:

    def test_sin_token_401(self, client, seed, db_session):
        t = crear_tramite(db_session, seed["servicio"], seed["usuario"])
        assert client.post(f"{_url(t.id_tramite)}/cancelar", json={}).status_code == 401

    def test_no_encontrado_404(self, client, headers_agente):
        assert client.post(f"{_url(999999)}/cancelar", headers=headers_agente, json={}).status_code == 404

    def test_cancela_desde_esperando_datos(self, client, headers_agente, seed, db_session):
        t = crear_tramite(db_session, seed["servicio"], seed["usuario"])

        resp = client.post(f"{_url(t.id_tramite)}/cancelar", headers=headers_agente, json={"comentario": "Cliente desistió."})

        assert resp.status_code == 200, resp.text
        datos = resp.json()
        assert datos["estado_actual"] == "cancelado"
        assert datos["historial"][-1]["estado"] == "cancelado"
        assert datos["historial"][-1]["origen"] == "agente"
        assert datos["historial"][-1]["comentario"] == "Cliente desistió."
        assert datos["historial"][-1]["nombre_usuario"] == "Agente Prueba"
        db_session.refresh(t)
        assert t.estado_actual == "cancelado"

    def test_sin_comentario_usa_uno_por_defecto(self, client, headers_agente, seed, db_session):
        t = crear_tramite(db_session, seed["servicio"], seed["usuario"])
        resp = client.post(f"{_url(t.id_tramite)}/cancelar", headers=headers_agente, json={})
        assert resp.json()["historial"][-1]["comentario"] == "Trámite anulado por el agente."

    @pytest.mark.parametrize("estado", ["firmado", "entregado", "cancelado"])
    def test_no_se_puede_cancelar_en_estados_finales(self, client, headers_agente, seed, db_session, estado):
        t = crear_tramite(db_session, seed["servicio"], seed["usuario"], estado_actual=estado)
        resp = client.post(f"{_url(t.id_tramite)}/cancelar", headers=headers_agente, json={})
        assert resp.status_code == 409


class TestReenviarFirma:

    def test_sin_token_401(self, client, seed, db_session):
        t = crear_tramite(db_session, seed["servicio"], seed["usuario"])
        assert client.post(f"{_url(t.id_tramite)}/reenviar-firma").status_code == 401

    def test_no_encontrado_404(self, client, headers_agente):
        assert client.post(f"{_url(999999)}/reenviar-firma", headers=headers_agente).status_code == 404

    def test_fuera_de_procesando_firma_409(self, client, headers_agente, seed, db_session):
        t = crear_tramite(db_session, seed["servicio"], seed["usuario"])  # esperando_datos
        resp = client.post(f"{_url(t.id_tramite)}/reenviar-firma", headers=headers_agente)
        assert resp.status_code == 409

    def test_sin_firmante_mantiene_el_aviso(self, client, headers_agente, seed, db_session):
        t = crear_tramite(db_session, seed["servicio"], seed["usuario"], estado_actual="procesando_firma")

        resp = client.post(f"{_url(t.id_tramite)}/reenviar-firma", headers=headers_agente)

        assert resp.status_code == 200, resp.text
        datos = resp.json()
        assert datos["estado_actual"] == "procesando_firma"
        assert datos["aviso_firma"] == "Falta el correo del firmante."
