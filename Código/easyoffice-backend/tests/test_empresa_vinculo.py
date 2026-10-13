"""
Vincular una empresa existente al convertir una solicitud (acción del agente): buscador de empresas, empresas sugeridas para un 
solicitante y conversión con `id_empresa` opcional. El cliente final nunca interviene en este vínculo.
"""
import pytest

from app import models


@pytest.fixture()
def crear_empresa(db_session):
    def _crear(rut="76123456-0", razon_social="Comercial Prueba SpA", **datos):
        empresa = models.Empresa(rut_empresa=rut, razon_social=razon_social, datos=datos)
        db_session.add(empresa)
        db_session.commit()
        db_session.refresh(empresa)
        return empresa

    return _crear


def _convertir_con(client, headers, id_solicitud, **cuerpo):
    return client.post(
        f"/api/solicitudes-contacto/{id_solicitud}/convertir", json=cuerpo, headers=headers
    )


class TestBuscadorEmpresas:
    URL = "/api/empresas"

    def test_exige_login(self, client):
        assert client.get(self.URL, params={"q": "prueba"}).status_code == 401

    @pytest.mark.parametrize("q", ["", "a"])
    def test_texto_muy_corto_422(self, client, headers_agente, q):
        assert client.get(self.URL, params={"q": q}, headers=headers_agente).status_code == 422

    def test_sin_parametro_q_422(self, client, headers_agente):
        assert client.get(self.URL, headers=headers_agente).status_code == 422

    def test_busca_por_razon_social_parcial_sin_importar_mayusculas(
        self, client, headers_agente, crear_empresa
    ):
        crear_empresa(razon_social="Comercial Prueba SpA")
        crear_empresa(rut="77111222-3", razon_social="Otra Cosa Ltda")

        resp = client.get(self.URL, params={"q": "prueba"}, headers=headers_agente)

        assert resp.status_code == 200
        assert [e["razon_social"] for e in resp.json()] == ["Comercial Prueba SpA"]

    def test_busca_por_rut_aunque_venga_con_puntos(self, client, headers_agente, crear_empresa):
        crear_empresa(rut="76123456-0")

        resp = client.get(self.URL, params={"q": "76.123.456-0"}, headers=headers_agente)

        assert [e["rut_empresa"] for e in resp.json()] == ["76123456-0"]

    def test_solo_devuelve_id_rut_y_razon_social(self, client, headers_agente, crear_empresa):
        crear_empresa(representante_nombre="Ana Soto", domicilio="Calle 1")

        fila = client.get(self.URL, params={"q": "prueba"}, headers=headers_agente).json()[0]

        assert set(fila) == {"id_empresa", "rut_empresa", "razon_social"}

    def test_sin_coincidencias_devuelve_lista_vacia(self, client, headers_agente, crear_empresa):
        crear_empresa()
        resp = client.get(self.URL, params={"q": "inexistente"}, headers=headers_agente)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_maximo_10_resultados(self, client, headers_agente, crear_empresa):
        for i in range(12):
            crear_empresa(rut=f"7600000{i:02d}-0", razon_social=f"Empresa Serie {i:02d}")

        resp = client.get(self.URL, params={"q": "serie"}, headers=headers_agente)

        assert len(resp.json()) == 10

    def test_los_comodines_de_like_se_toman_literalmente(
        self, client, headers_agente, crear_empresa
    ):
        crear_empresa()
        resp = client.get(self.URL, params={"q": "%%"}, headers=headers_agente)
        assert resp.json() == []


class TestEmpresasSugeridas:
    def _url(self, id_solicitud):
        return f"/api/solicitudes-contacto/{id_solicitud}/empresas-sugeridas"

    def test_exige_login(self, client, crear_solicitud):
        sol = crear_solicitud()
        assert client.get(self._url(sol["id_solicitud"])).status_code == 401

    def test_solicitud_inexistente_404(self, client, headers_agente):
        assert client.get(self._url(9999), headers=headers_agente).status_code == 404

    def test_solicitante_nuevo_sin_sugerencias(self, client, headers_agente, crear_solicitud):
        sol = crear_solicitud()
        resp = client.get(self._url(sol["id_solicitud"]), headers=headers_agente)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_solicitud_sin_rut_sin_sugerencias(self, client, headers_agente, crear_solicitud):
        sol = crear_solicitud(rut=None)
        assert client.get(self._url(sol["id_solicitud"]), headers=headers_agente).json() == []

    def test_sugiere_la_empresa_de_un_tramite_anterior_del_mismo_solicitante(
        self, client, headers_agente, crear_solicitud, crear_empresa
    ):
        empresa = crear_empresa()
        primera = crear_solicitud()
        assert _convertir_con(
            client, headers_agente, primera["id_solicitud"], id_empresa=empresa.id_empresa
        ).status_code == 200

        segunda = crear_solicitud()  # mismo RUT de solicitante
        resp = client.get(self._url(segunda["id_solicitud"]), headers=headers_agente)

        assert resp.json() == [{
            "id_empresa": empresa.id_empresa,
            "rut_empresa": "76123456-0",
            "razon_social": "Comercial Prueba SpA",
        }]

    def test_empresa_repetida_en_varios_tramites_aparece_una_vez(
        self, client, headers_agente, crear_solicitud, crear_empresa
    ):
        empresa = crear_empresa()
        for _ in range(2):
            sol = crear_solicitud()
            _convertir_con(client, headers_agente, sol["id_solicitud"], id_empresa=empresa.id_empresa)

        nueva = crear_solicitud()
        resp = client.get(self._url(nueva["id_solicitud"]), headers=headers_agente)

        assert len(resp.json()) == 1

    def test_no_sugiere_empresas_de_otro_solicitante(
        self, client, headers_agente, crear_solicitud, crear_empresa
    ):
        empresa = crear_empresa()
        ajena = crear_solicitud(rut="11111111-1", nombre="Otra Persona")
        _convertir_con(client, headers_agente, ajena["id_solicitud"], id_empresa=empresa.id_empresa)

        mia = crear_solicitud()  # RUT 12345678-9
        assert client.get(self._url(mia["id_solicitud"]), headers=headers_agente).json() == []

    def test_tramites_sin_empresa_no_generan_sugerencias(
        self, client, headers_agente, crear_solicitud, convertir
    ):
        primera = crear_solicitud()
        assert convertir(primera["id_solicitud"]).status_code == 200

        segunda = crear_solicitud()
        assert client.get(self._url(segunda["id_solicitud"]), headers=headers_agente).json() == []


class TestConvertirConEmpresa:
    def test_vincula_la_empresa_al_tramite(
        self, client, headers_agente, crear_solicitud, crear_empresa, db_session
    ):
        empresa = crear_empresa()
        sol = crear_solicitud()

        resp = _convertir_con(client, headers_agente, sol["id_solicitud"], id_empresa=empresa.id_empresa)

        assert resp.status_code == 200
        tramite = db_session.get(models.Tramite, resp.json()["id_tramite"])
        assert tramite.id_empresa == empresa.id_empresa

    def test_el_historial_deja_constancia_de_la_empresa(
        self, client, headers_agente, crear_solicitud, crear_empresa, db_session
    ):
        empresa = crear_empresa()
        sol = crear_solicitud()

        resp = _convertir_con(client, headers_agente, sol["id_solicitud"], id_empresa=empresa.id_empresa)

        historial = db_session.query(models.HistorialEstado).filter_by(
            id_tramite=resp.json()["id_tramite"]
        ).one()
        assert "Comercial Prueba SpA" in historial.comentario
        assert "76123456-0" in historial.comentario

    def test_sin_cuerpo_el_tramite_queda_sin_empresa(
        self, crear_solicitud, convertir, db_session
    ):
        sol = crear_solicitud()
        resp = convertir(sol["id_solicitud"])
        assert resp.status_code == 200
        assert db_session.get(models.Tramite, resp.json()["id_tramite"]).id_empresa is None

    def test_cuerpo_vacio_o_id_nulo_equivale_a_sin_empresa(
        self, client, headers_agente, crear_solicitud, db_session
    ):
        for cuerpo in ({}, {"id_empresa": None}):
            sol = crear_solicitud(rut=None)
            resp = _convertir_con(client, headers_agente, sol["id_solicitud"], **cuerpo)
            assert resp.status_code == 200
            assert db_session.get(models.Tramite, resp.json()["id_tramite"]).id_empresa is None

    def test_empresa_inexistente_404_y_no_se_crea_nada(
        self, client, headers_agente, crear_solicitud, db_session
    ):
        sol = crear_solicitud()

        resp = _convertir_con(client, headers_agente, sol["id_solicitud"], id_empresa=9999)

        assert resp.status_code == 404
        assert "empresa" in resp.json()["detail"].lower()
        db_session.expire_all()
        assert db_session.get(models.SolicitudContacto, sol["id_solicitud"]).estado == "pendiente"
        assert db_session.query(models.Tramite).count() == 0
        assert db_session.query(models.Cliente).count() == 0

    @pytest.mark.parametrize("valor", [0, -1, "abc"])
    def test_id_empresa_invalido_422(self, client, headers_agente, crear_solicitud, valor):
        sol = crear_solicitud()
        resp = _convertir_con(client, headers_agente, sol["id_solicitud"], id_empresa=valor)
        assert resp.status_code == 422

    def test_el_responsable_sigue_siendo_la_sesion(
        self, client, headers_agente, crear_solicitud, crear_empresa, seed, db_session
    ):
        empresa = crear_empresa()
        sol = crear_solicitud()

        resp = _convertir_con(
            client, headers_agente, sol["id_solicitud"],
            id_empresa=empresa.id_empresa, id_usuario_responsable=9999,
        )

        assert resp.status_code == 200
        tramite = db_session.get(models.Tramite, resp.json()["id_tramite"])
        assert tramite.id_usuario_responsable == seed["usuario"].id_usuario

    def test_el_solicitante_no_se_altera_al_vincular_empresa(
        self, client, headers_agente, crear_solicitud, crear_empresa, db_session
    ):
        empresa = crear_empresa()
        sol = crear_solicitud()

        _convertir_con(client, headers_agente, sol["id_solicitud"], id_empresa=empresa.id_empresa)

        cliente = db_session.query(models.Cliente).one()
        assert (cliente.nombre, cliente.rut) == ("Juan Pérez", "12345678-9")

    def test_exige_login_aunque_se_envie_empresa(self, client, crear_solicitud, crear_empresa):
        empresa = crear_empresa()
        sol = crear_solicitud()
        resp = client.post(
            f"/api/solicitudes-contacto/{sol['id_solicitud']}/convertir",
            json={"id_empresa": empresa.id_empresa},
        )
        assert resp.status_code == 401