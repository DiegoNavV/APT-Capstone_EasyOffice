"""
Pruebas de GET /api/solicitudes-contacto (listado para el panel de agentes/admins).

El endpoint devuelve datos personales de clientes (RUT, email, teléfono), así
que gran parte de estas pruebas verifica que NO se pueda leer sin sesión.
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app import crud, models
from app.seguridad import JWT_ALGORITHM, JWT_SECRET_KEY, crear_access_token

URL = "/api/solicitudes-contacto"


@pytest.fixture()
def auth_headers(seed):
    """Header de un agente logueado (token firmado igual que en /api/auth/login)."""
    token = crear_access_token(seed["usuario"].id_usuario, "agente")
    return {"Authorization": f"Bearer {token}"}


def _convertir_directo(db_session, id_solicitud):
    """Convierte vía crud (no vía endpoint) para que estas pruebas no dependan
    de si /convertir exige o no sesión."""
    solicitud = crud.obtener_solicitud(db_session, id_solicitud)
    return crud.convertir_solicitud_a_tramite(db_session, solicitud, None)


# ===========================================================================
# 1. Autenticación: sin sesión válida no se puede leer nada
# ===========================================================================

class TestAutenticacion:

    def test_sin_token_401(self, client, crear_solicitud):
        crear_solicitud()
        resp = client.get(URL)
        assert resp.status_code == 401

    def test_sin_token_no_filtra_datos_personales(self, client, crear_solicitud):
        crear_solicitud()
        texto = client.get(URL).text
        for dato in ("12345678-9", "juan@example.com", "+56912345678", "Juan"):
            assert dato not in texto

    @pytest.mark.parametrize("header", [
        "Bearer token-inventado",
        "Bearer ",
        "Basic abc123",
        "abc",
    ])
    def test_token_invalido_401(self, client, header):
        assert client.get(URL, headers={"Authorization": header}).status_code == 401

    def test_token_firmado_con_otro_secreto_401(self, client, seed):
        falso = jwt.encode(
            {"sub": str(seed["usuario"].id_usuario), "rol": "admin",
             "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
            "otro-secreto", algorithm=JWT_ALGORITHM)
        resp = client.get(URL, headers={"Authorization": f"Bearer {falso}"})
        assert resp.status_code == 401

    def test_token_expirado_401(self, client, seed):
        expirado = jwt.encode(
            {"sub": str(seed["usuario"].id_usuario), "rol": "agente",
             "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
            JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        resp = client.get(URL, headers={"Authorization": f"Bearer {expirado}"})
        assert resp.status_code == 401

    def test_token_de_usuario_inexistente_401(self, client):
        token = crear_access_token(99999, "agente")
        resp = client.get(URL, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_usuario_desactivado_401(self, client, db_session, seed, auth_headers):
        usuario = db_session.get(models.Usuario, seed["usuario"].id_usuario)
        usuario.activo = False
        db_session.commit()
        assert client.get(URL, headers=auth_headers).status_code == 401

    def test_crear_solicitud_sigue_siendo_publico(self, client, seed):
        """Proteger el GET no debe afectar al formulario público (POST)."""
        resp = client.post(URL, json={"nombre": "Ana"})
        assert resp.status_code == 201


# ===========================================================================
# 2. Contenido del listado
# ===========================================================================

class TestListado:

    def test_lista_vacia_200(self, client, auth_headers):
        resp = client.get(URL, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_devuelve_la_solicitud_con_sus_campos(
            self, client, auth_headers, crear_solicitud, seed):
        sol = crear_solicitud()
        resp = client.get(URL, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        item = data[0]
        assert item["id_solicitud"] == sol["id_solicitud"]
        assert item["nombre"] == "Juan Pérez"
        assert item["rut"] == "12345678-9"
        assert item["email"] == "juan@example.com"
        assert item["telefono"] == "+56912345678"
        assert item["mensaje"] == "Quiero formalizar mi emprendimiento"
        assert item["estado"] == "pendiente"
        assert item["id_servicio"] == seed["servicio"].id_servicio
        assert item["nombre_servicio"] == "Constitución de Sociedad"
        assert item["id_tramite_generado"] is None
        assert item["codigo_seguimiento"] is None
        assert item["fecha_creacion"]

    def test_solicitud_sin_servicio_tiene_nombre_servicio_none(
            self, client, auth_headers, crear_solicitud):
        crear_solicitud(servicio_id=None)
        item = client.get(URL, headers=auth_headers).json()[0]
        assert item["id_servicio"] is None
        assert item["nombre_servicio"] is None

    def test_mas_recientes_primero(self, client, auth_headers, crear_solicitud):
        ids = [crear_solicitud(rut=f"{i}-{i}")["id_solicitud"] for i in range(1, 5)]
        resultado = [s["id_solicitud"] for s in client.get(URL, headers=auth_headers).json()]
        assert resultado == sorted(ids, reverse=True)

    def test_solicitud_convertida_muestra_codigo_de_seguimiento(
            self, client, auth_headers, crear_solicitud, db_session):
        sol = crear_solicitud()
        tramite = _convertir_directo(db_session, sol["id_solicitud"])

        item = client.get(URL, headers=auth_headers).json()[0]
        assert item["estado"] == "convertido"
        assert item["id_tramite_generado"] == tramite.id_tramite
        assert item["codigo_seguimiento"] == tramite.codigo_seguimiento
        assert len(item["codigo_seguimiento"]) == 8

    def test_cada_solicitud_muestra_su_propio_codigo(
            self, client, auth_headers, crear_solicitud, db_session):
        s1 = crear_solicitud(rut="1-1")
        s2 = crear_solicitud(rut="2-2")
        s3 = crear_solicitud(rut="3-3")  # queda pendiente
        t1 = _convertir_directo(db_session, s1["id_solicitud"])
        t2 = _convertir_directo(db_session, s2["id_solicitud"])

        por_id = {s["id_solicitud"]: s for s in client.get(URL, headers=auth_headers).json()}
        assert por_id[s1["id_solicitud"]]["codigo_seguimiento"] == t1.codigo_seguimiento
        assert por_id[s2["id_solicitud"]]["codigo_seguimiento"] == t2.codigo_seguimiento
        assert por_id[s3["id_solicitud"]]["codigo_seguimiento"] is None
        assert t1.codigo_seguimiento != t2.codigo_seguimiento


# ===========================================================================
# 3. Filtro por estado
# ===========================================================================

class TestFiltroEstado:

    @pytest.fixture()
    def una_pendiente_y_una_convertida(self, crear_solicitud, db_session):
        pendiente = crear_solicitud(rut="1-1")
        convertida = crear_solicitud(rut="2-2")
        _convertir_directo(db_session, convertida["id_solicitud"])
        return pendiente, convertida

    def test_filtra_pendientes(self, client, auth_headers, una_pendiente_y_una_convertida):
        pendiente, _ = una_pendiente_y_una_convertida
        data = client.get(URL, params={"estado": "pendiente"}, headers=auth_headers).json()
        assert [s["id_solicitud"] for s in data] == [pendiente["id_solicitud"]]

    def test_filtra_convertidas(self, client, auth_headers, una_pendiente_y_una_convertida):
        _, convertida = una_pendiente_y_una_convertida
        data = client.get(URL, params={"estado": "convertido"}, headers=auth_headers).json()
        assert [s["id_solicitud"] for s in data] == [convertida["id_solicitud"]]

    def test_sin_filtro_devuelve_todas(self, client, auth_headers, una_pendiente_y_una_convertida):
        assert len(client.get(URL, headers=auth_headers).json()) == 2

    def test_estado_sin_resultados_devuelve_lista_vacia(
            self, client, auth_headers, una_pendiente_y_una_convertida):
        resp = client.get(URL, params={"estado": "inexistente"}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_estado_demasiado_largo_422(self, client, auth_headers):
        resp = client.get(URL, params={"estado": "x" * 31}, headers=auth_headers)
        assert resp.status_code == 422


# ===========================================================================
# 4. Paginación
# ===========================================================================

class TestPaginacion:

    @pytest.fixture()
    def cinco(self, crear_solicitud):
        return [crear_solicitud(rut=f"{i}-{i}")["id_solicitud"] for i in range(1, 6)]

    def test_limit_limita_resultados(self, client, auth_headers, cinco):
        data = client.get(URL, params={"limit": 2}, headers=auth_headers).json()
        assert len(data) == 2

    def test_offset_salta_resultados(self, client, auth_headers, cinco):
        # Orden: más recientes primero -> ids [5, 4, 3, 2, 1]
        data = client.get(URL, params={"limit": 2, "offset": 2}, headers=auth_headers).json()
        assert [s["id_solicitud"] for s in data] == [cinco[2], cinco[1]]

    def test_offset_mas_alla_del_final_devuelve_vacio(self, client, auth_headers, cinco):
        assert client.get(URL, params={"offset": 100}, headers=auth_headers).json() == []

    def test_paginas_no_se_solapan_ni_pierden_filas(self, client, auth_headers, cinco):
        p1 = client.get(URL, params={"limit": 2, "offset": 0}, headers=auth_headers).json()
        p2 = client.get(URL, params={"limit": 2, "offset": 2}, headers=auth_headers).json()
        p3 = client.get(URL, params={"limit": 2, "offset": 4}, headers=auth_headers).json()
        ids = [s["id_solicitud"] for s in p1 + p2 + p3]
        assert sorted(ids) == sorted(cinco)

    @pytest.mark.parametrize("params", [
        {"limit": 0}, {"limit": -1}, {"limit": 201}, {"limit": "abc"},
        {"offset": -1}, {"offset": "abc"},
    ])
    def test_parametros_invalidos_422(self, client, auth_headers, params):
        assert client.get(URL, params=params, headers=auth_headers).status_code == 422

    def test_limit_maximo_permitido_200(self, client, auth_headers):
        assert client.get(URL, params={"limit": 200}, headers=auth_headers).status_code == 200