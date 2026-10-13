"""
Formulario del cliente (lectura): con su código el cliente ve qué debe completar.
Es público, así que se prueba sobre todo lo que NO debe salir: datos completos de una empresa, datos después del envío, o información 
con un código inválido.
"""
import pytest

from app import models
from app.seguridad import limiter

CONTRATO = "Contrato de servicio"
AUTORIZACION = "Autorización de domicilio tributario"

DATOS_EMPRESA = {
    "representante_legal": "Ana Soto Pérez",
    "rut_representante": "11222333-4",
    "domicilio_representante": "Av. Siempre Viva 742",
    "comuna_representante": "Providencia",
    "region_representante": "Metropolitana",
    "giro_principal": "Venta de artículos de oficina",
    "email": "peruanolindo@hotmail.com",
    "celular": "912345678",
    "fecha_escritura": "2020-05-15",
}
# Valores que jamás deben aparecer completos en la respuesta.
SENSIBLES = [
    "Comercial Prueba SpA", "76123456-0", "Ana Soto", "11222333-4", "Av. Siempre Viva",
    "peruanolindo", "hotmail", "912345678",
]


@pytest.fixture()
def tramite_de(client, crear_solicitud, convertir, seed, db_session):
    """Crea un trámite para el servicio indicado y lo devuelve (modelo)."""
    def _crear(nombre_servicio=CONTRATO, empresa=None):
        seed["servicio"].nombre = nombre_servicio
        db_session.commit()
        resp = convertir(crear_solicitud()["id_solicitud"])
        assert resp.status_code == 200
        tramite = db_session.get(models.Tramite, resp.json()["id_tramite"])
        if empresa is not None:
            tramite.id_empresa = empresa.id_empresa
            db_session.commit()
        return tramite

    return _crear


@pytest.fixture()
def empresa_completa(db_session):
    empresa = models.Empresa(
        rut_empresa="76123456-0", razon_social="Comercial Prueba SpA", datos=dict(DATOS_EMPRESA)
    )
    db_session.add(empresa)
    db_session.commit()
    db_session.refresh(empresa)
    return empresa


def _formulario(client, codigo):
    return client.get(f"/api/tramites/codigo/{codigo}/formulario")


def _por_clave(cuerpo):
    return {c["clave"]: c for c in cuerpo["campos"]}


class TestAccesoYCodigo:
    def test_es_publico_no_pide_login(self, client, tramite_de):
        tramite = tramite_de()
        assert _formulario(client, tramite.codigo_seguimiento).status_code == 200

    def test_acepta_el_codigo_en_minusculas(self, client, tramite_de):
        tramite = tramite_de()
        assert _formulario(client, tramite.codigo_seguimiento.lower()).status_code == 200

    def test_codigo_inexistente_404(self, client, tramite_de):
        tramite_de()
        assert _formulario(client, "ZZZZZZZZ").status_code == 404

    @pytest.mark.parametrize("codigo", ["abc", "123456789", "1234567"])
    def test_codigo_de_largo_incorrecto_400(self, client, codigo):
        assert _formulario(client, codigo).status_code == 400

    def test_no_choca_con_la_consulta_de_seguimiento(self, client, tramite_de):
        tramite = tramite_de()
        resp = client.get(f"/api/tramites/codigo/{tramite.codigo_seguimiento}")
        assert resp.status_code == 200
        assert "campos" not in resp.json()


class TestCamposSegunServicio:
    def test_contrato_pide_12_campos(self, client, tramite_de):
        cuerpo = _formulario(client, tramite_de(CONTRATO).codigo_seguimiento).json()
        assert cuerpo["formulario_disponible"] is True
        assert len(cuerpo["campos"]) == 12
        assert cuerpo["nombre_servicio"] == CONTRATO

    def test_autorizacion_pide_solo_4_campos(self, client, tramite_de):
        cuerpo = _formulario(client, tramite_de(AUTORIZACION).codigo_seguimiento).json()
        assert len(cuerpo["campos"]) == 4

    def test_servicio_sin_formulario_definido_no_lo_ofrece(self, client, tramite_de):
        cuerpo = _formulario(client, tramite_de("Constitución de Sociedad").codigo_seguimiento).json()
        assert cuerpo["formulario_disponible"] is False
        assert cuerpo["campos"] == []

    def test_cada_campo_trae_lo_que_el_formulario_necesita(self, client, tramite_de):
        campo = _formulario(client, tramite_de().codigo_seguimiento).json()["campos"][0]
        assert set(campo) == {
            "clave", "etiqueta", "tipo", "ayuda", "max_largo", "registrado", "valor_enmascarado"
        }


class TestSinEmpresaVinculada:
    def test_ningun_campo_viene_registrado(self, client, tramite_de):
        cuerpo = _formulario(client, tramite_de().codigo_seguimiento).json()
        assert cuerpo["datos_enviados"] is False
        assert all(c["registrado"] is False for c in cuerpo["campos"])
        assert all(c["valor_enmascarado"] is None for c in cuerpo["campos"])

    def test_empresa_que_existe_pero_no_esta_vinculada_no_se_usa(
        self, client, tramite_de, empresa_completa
    ):
        # El vínculo lo hace solo el agente; que exista una empresa no basta.
        cuerpo = _formulario(client, tramite_de().codigo_seguimiento).json()
        assert all(c["registrado"] is False for c in cuerpo["campos"])


class TestConEmpresaVinculada:
    def test_los_datos_existentes_salen_enmascarados(self, client, tramite_de, empresa_completa):
        tramite = tramite_de(empresa=empresa_completa)
        campos = _por_clave(_formulario(client, tramite.codigo_seguimiento).json())

        assert campos["email"]["registrado"] is True
        assert campos["email"]["valor_enmascarado"] == "pe•••••@•••.com"
        assert campos["celular"]["valor_enmascarado"] == "9 •••• ••78"
        assert campos["rut_empresa"]["valor_enmascarado"] == "76•••••-0"
        assert campos["domicilio_representante"]["valor_enmascarado"] == "Dato ya registrado"
        assert campos["razon_social"]["valor_enmascarado"] == "Dato ya registrado"

    def test_la_fecha_sale_completa(self, client, tramite_de, empresa_completa):
        tramite = tramite_de(empresa=empresa_completa)
        campos = _por_clave(_formulario(client, tramite.codigo_seguimiento).json())
        assert campos["fecha_escritura"]["valor_enmascarado"] == "2020-05-15"

    def test_ningun_dato_sensible_sale_completo(self, client, tramite_de, empresa_completa):
        tramite = tramite_de(empresa=empresa_completa)
        texto = _formulario(client, tramite.codigo_seguimiento).text
        for sensible in SENSIBLES:
            assert sensible not in texto

    def test_solo_se_marcan_registrados_los_campos_que_existen(self, client, tramite_de, db_session):
        parcial = models.Empresa(
            rut_empresa="76123456-0", razon_social="Parcial SpA", datos={"email": "a@b.cl"}
        )
        db_session.add(parcial)
        db_session.commit()
        tramite = tramite_de(empresa=parcial)

        campos = _por_clave(_formulario(client, tramite.codigo_seguimiento).json())

        registrados = {k for k, c in campos.items() if c["registrado"]}
        assert registrados == {"razon_social", "rut_empresa", "email"}

    def test_autorizacion_reutiliza_datos_del_contrato(self, client, tramite_de, empresa_completa):
        tramite = tramite_de(AUTORIZACION, empresa=empresa_completa)
        cuerpo = _formulario(client, tramite.codigo_seguimiento).json()
        assert len(cuerpo["campos"]) == 4
        assert any(c["registrado"] for c in cuerpo["campos"])


class TestDespuesDelEnvio:
    def test_si_ya_envio_solo_informa_el_estado(self, client, tramite_de, empresa_completa, db_session):
        tramite = tramite_de(empresa=empresa_completa)
        db_session.add(models.DatosEmpresaTramite(
            id_tramite=tramite.id_tramite,
            solicitante_es_representante=True,
            consentimiento_aceptado=True,
        ))
        db_session.commit()

        resp = _formulario(client, tramite.codigo_seguimiento)
        cuerpo = resp.json()

        assert cuerpo["datos_enviados"] is True
        assert cuerpo["formulario_disponible"] is False
        assert cuerpo["campos"] == []
        for sensible in SENSIBLES:
            assert sensible not in resp.text

    @pytest.mark.parametrize("estado", ["procesando_firma", "en_revision", "firmado", "entregado"])
    def test_si_el_tramite_ya_avanzo_no_ofrece_el_formulario(
        self, client, tramite_de, db_session, estado
    ):
        tramite = tramite_de()
        tramite.estado_actual = estado
        db_session.commit()

        cuerpo = _formulario(client, tramite.codigo_seguimiento).json()

        assert cuerpo["formulario_disponible"] is False
        assert cuerpo["campos"] == []
        assert cuerpo["estado_actual"] == estado


class TestLimiteDePeticiones:
    @pytest.fixture()
    def limite_activo(self):
        # La suite lo desactiva globalmente (ver conftest); aquí se activa y se restaura.
        limiter.reset()
        limiter.enabled = True
        yield
        limiter.enabled = False
        limiter.reset()

    def test_pasadas_30_consultas_por_minuto_responde_429(self, client, tramite_de, limite_activo):
        codigo = tramite_de().codigo_seguimiento
        respuestas = [_formulario(client, codigo).status_code for _ in range(31)]
        assert respuestas[:30] == [200] * 30
        assert respuestas[30] == 429

    def test_los_intentos_con_codigo_invalido_tambien_cuentan(self, client, limite_activo):
        respuestas = [_formulario(client, "ZZZZZZZZ").status_code for _ in range(31)]
        assert respuestas[:30] == [404] * 30
        assert respuestas[30] == 429