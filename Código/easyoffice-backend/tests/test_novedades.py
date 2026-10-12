"""
Pruebas de GET /api/solicitudes-contacto/novedades (aviso "hay solicitudes nuevas" del panel). Solo devuelve números, 
nunca datos de las solicitudes.
"""
import pytest

from app import models
from app.seguridad import crear_access_token

URL = "/api/solicitudes-contacto/novedades"


@pytest.fixture()
def auth(seed):
    """Header Bearer de la cuenta semilla (mismo token que entrega /api/auth/login)."""
    u = seed["usuario"]
    return {"Authorization": f"Bearer {crear_access_token(u.id_usuario, 'agente')}"}


class TestAcceso:

    def test_sin_token_401(self, client):
        assert client.get(URL).status_code == 401

    def test_token_invalido_401(self, client):
        resp = client.get(URL, headers={"Authorization": "Bearer basura"})
        assert resp.status_code == 401

    def test_cuenta_desactivada_401(self, client, auth, seed, db_session):
        u = db_session.get(models.Usuario, seed["usuario"].id_usuario)
        u.activo = False
        db_session.commit()
        assert client.get(URL, headers=auth).status_code == 401

    def test_no_queda_publico_aunque_haya_solicitudes(self, client, crear_solicitud):
        crear_solicitud()
        assert client.get(URL, params={"desde_id": 0}).status_code == 401


class TestConteo:

    def test_sin_solicitudes(self, client, auth):
        resp = client.get(URL, headers=auth)
        assert resp.status_code == 200
        assert resp.json() == {"nuevas": 0, "ultimo_id": 0}

    def test_sin_desde_id_solo_informa_el_ultimo_id(self, client, auth, crear_solicitud):
        crear_solicitud()
        ultima = crear_solicitud(nombre="Otra", rut="9876543-2")
        resp = client.get(URL, headers=auth)
        assert resp.json() == {"nuevas": 0, "ultimo_id": ultima["id_solicitud"]}

    def test_cuenta_las_posteriores_al_punto_de_partida(self, client, auth, crear_solicitud):
        primera = crear_solicitud()
        base = client.get(URL, headers=auth).json()["ultimo_id"]
        assert base == primera["id_solicitud"]

        crear_solicitud(nombre="B", rut="11111111-1")
        ultima = crear_solicitud(nombre="C", rut="22222222-2")

        resp = client.get(URL, headers=auth, params={"desde_id": base})
        assert resp.json() == {"nuevas": 2, "ultimo_id": ultima["id_solicitud"]}

    def test_al_dia_devuelve_cero(self, client, auth, crear_solicitud):
        ultima = crear_solicitud()
        resp = client.get(URL, headers=auth, params={"desde_id": ultima["id_solicitud"]})
        assert resp.json() == {"nuevas": 0, "ultimo_id": ultima["id_solicitud"]}

    def test_desde_id_cero_cuenta_todas(self, client, auth, crear_solicitud):
        crear_solicitud()
        crear_solicitud(nombre="B", rut="11111111-1")
        assert client.get(URL, headers=auth, params={"desde_id": 0}).json()["nuevas"] == 2

    def test_cuenta_sobre_toda_la_tabla_incluidas_las_convertidas(self, client, auth, crear_solicitud, convertir, seed):
        a = crear_solicitud()
        base = a["id_solicitud"]
        b = crear_solicitud(nombre="B", rut="11111111-1")
        assert convertir(b["id_solicitud"], seed["usuario"].id_usuario).status_code == 200
        # una pendiente y una convertida posteriores al punto de partida: ambas cuentan
        assert client.get(URL, headers=auth, params={"desde_id": base}).json()["nuevas"] == 1
        c = crear_solicitud(nombre="C", rut="22222222-2")
        resp = client.get(URL, headers=auth, params={"desde_id": base})
        assert resp.json() == {"nuevas": 2, "ultimo_id": c["id_solicitud"]}

    def test_convertir_no_cambia_el_conteo(self, client, auth, crear_solicitud, convertir, seed):
        a = crear_solicitud()
        antes = client.get(URL, headers=auth, params={"desde_id": 0}).json()
        convertir(a["id_solicitud"], seed["usuario"].id_usuario)
        assert client.get(URL, headers=auth, params={"desde_id": 0}).json() == antes


class TestValidacion:

    @pytest.mark.parametrize("valor", ["-1", "abc", "1.5"])
    def test_desde_id_invalido_422(self, client, auth, valor):
        assert client.get(URL, headers=auth, params={"desde_id": valor}).status_code == 422

    def test_respuesta_solo_tiene_numeros(self, client, auth, crear_solicitud):
        crear_solicitud()
        data = client.get(URL, headers=auth, params={"desde_id": 0}).json()
        assert set(data) == {"nuevas", "ultimo_id"}
        assert all(isinstance(v, int) for v in data.values())


class TestConvivenciaConElResto:

    def test_la_ruta_no_choca_con_el_listado_ni_con_convertir(self, client, auth, crear_solicitud, seed):
        sol = crear_solicitud()
        assert client.get("/api/solicitudes-contacto", headers=auth).status_code == 200
        resp = client.post(
            f"/api/solicitudes-contacto/{sol['id_solicitud']}/convertir",
            json={"id_usuario_responsable": seed["usuario"].id_usuario},
        )
        assert resp.status_code == 200