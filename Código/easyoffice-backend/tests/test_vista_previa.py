"""
Vista previa del borrador para el cliente (pública, con su código). Se prueba lo importante: no guarda nada, enmascara lo ya 
registrado, comparte las reglas del envío, no filtra detalles técnicos y se frena con los límites.
"""
import itertools

import pytest

from app import models, vista_previa
from app.convertir_pdf import ErrorConversion, ServidorOcupado
from app.seguridad import limiter
from tests.test_cliente_envio import CAMPOS_CONTRATO, CONTRATO, empresa_completa, tramite_de  # noqa: F401
from tests.test_plantillas import carpeta_plantillas, docx_con, headers_admin, subir  # noqa: F401
from tests.test_rellenar_docx import textos_de

PDF_FALSO = b"%PDF-1.4 borrador de prueba"
PLANTILLA = "{{FOLIO}} | {{RAZON_SOCIAL}} | {{RUT}} | {{MAIL}} | {{CELULAR_8_DIGITOS}} | {{GIRO_PRINCIPAL}}"


@pytest.fixture(autouse=True)
def entorno(monkeypatch):
    """Sin LibreOffice real: se guarda el .docx recibido y se devuelve un PDF falso."""
    for nombre in ("MARCA_POR_DEFECTO", "BANCO_TEXTO_EASY_OFFICE", "BANCO_TEXTO_INOFFICE"):
        monkeypatch.delenv(nombre, raising=False)      # las pruebas no dependen del .env de cada uno
    vista_previa.vaciar_cache()
    recibidos = []

    def falso(docx, espera_maxima=None):
        recibidos.append(docx)
        return PDF_FALSO

    monkeypatch.setattr("app.vista_previa.docx_a_pdf", falso)
    yield recibidos
    vista_previa.vaciar_cache()


@pytest.fixture()
def tramite(tramite_de, subir, db_session):  # noqa: F811
    t = tramite_de()
    t.folio = "LF-01-2026"
    db_session.commit()
    r = subir(docx_con(PLANTILLA), id_servicio=t.id_servicio)
    assert r.status_code == 201, r.text
    return t


def pedir(client, tramite, campos):
    return client.post(f"/api/tramites/codigo/{tramite.codigo_seguimiento}/vista-previa", json={"campos": campos})


def texto(docx: bytes) -> str:
    return " ".join(textos_de(docx))


# ---------- empresa nueva ----------

def test_borrador_con_los_datos_escritos(client, tramite, entorno):
    r = pedir(client, tramite, CAMPOS_CONTRATO)
    assert r.status_code == 200, r.text
    assert r.content == PDF_FALSO
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["cache-control"] == "no-store"
    t = texto(entorno[0])
    assert "LF-01-2026" in t and "COMERCIAL PRUEBA SPA" in t and "76.123.456-0" in t
    assert "ana@prueba.cl" in t and "912345678" in t and "VENTA DE ARTÍCULOS DE OFICINA" in t


def test_no_guarda_nada(client, tramite, db_session):
    antes = db_session.query(models.HistorialEstado).count()
    assert pedir(client, tramite, CAMPOS_CONTRATO).status_code == 200
    db_session.expire_all()
    t = db_session.get(models.Tramite, tramite.id_tramite)
    assert t.estado_actual == "generado" and t.datos_empresa is None and t.id_empresa is None
    assert t.ruta_documento_generado is None
    assert db_session.query(models.Empresa).count() == 0
    assert db_session.query(models.HistorialEstado).count() == antes


# ---------- empresa ya registrada ----------

def test_lo_ya_registrado_sale_enmascarado(client, tramite, empresa_completa, db_session, entorno):  # noqa: F811
    tramite.id_empresa = empresa_completa.id_empresa
    db_session.commit()
    r = pedir(client, tramite, {})
    assert r.status_code == 200, r.text
    t = texto(entorno[0])
    for completo in ("ana@prueba.cl", "76.123.456-0", "76123456", "912345678", "COMERCIAL PRUEBA", "VENTA DE ARTÍCULOS"):
        assert completo not in t
    assert "DATO YA REGISTRADO" in t and "•" in t


def test_mezcla_de_registrado_y_escrito(client, tramite, db_session, entorno):
    empresa = models.Empresa(rut_empresa="76123456-0", razon_social="Comercial Prueba SpA", datos={})
    db_session.add(empresa)
    db_session.commit()
    tramite.id_empresa = empresa.id_empresa
    db_session.commit()
    escritos = {k: v for k, v in CAMPOS_CONTRATO.items() if k not in ("razon_social", "rut_empresa")}
    r = pedir(client, tramite, escritos)
    assert r.status_code == 200, r.text
    t = texto(entorno[0])
    assert "COMERCIAL PRUEBA" not in t and "76.123.456-0" not in t      # lo registrado, oculto
    assert "ana@prueba.cl" in t and "VENTA DE ARTÍCULOS DE OFICINA" in t  # lo escrito, completo


# ---------- mismas reglas que el envío ----------

def test_campo_ya_registrado_se_rechaza(client, tramite, empresa_completa, db_session):  # noqa: F811
    tramite.id_empresa = empresa_completa.id_empresa
    db_session.commit()
    r = pedir(client, tramite, {"email": "otro@correo.cl"})
    assert r.status_code == 422 and "email" in r.json()["detail"]["errores"]


def test_campos_con_errores_se_informan_todos_juntos(client, tramite):
    r = pedir(client, tramite, {**CAMPOS_CONTRATO, "rut_empresa": "1-9", "celular": "123"})
    assert r.status_code == 422
    assert set(r.json()["detail"]["errores"]) == {"rut_empresa", "celular"}


def test_faltan_campos_obligatorios(client, tramite):
    r = pedir(client, tramite, {})
    assert r.status_code == 422 and "razon_social" in r.json()["detail"]["errores"]


def test_no_acepta_campos_de_mas_en_el_cuerpo(client, tramite):
    r = client.post(
        f"/api/tramites/codigo/{tramite.codigo_seguimiento}/vista-previa",
        json={"campos": CAMPOS_CONTRATO, "consentimiento_aceptado": True},
    )
    assert r.status_code == 422


# ---------- cuándo no hay borrador ----------

def test_codigo_corto_y_codigo_inexistente(client, tramite):
    assert client.post("/api/tramites/codigo/ABC/vista-previa", json={"campos": {}}).status_code == 400
    assert client.post("/api/tramites/codigo/ZZZZZZZZ/vista-previa", json={"campos": {}}).status_code == 404


def test_tramite_que_ya_envio_sus_datos(client, tramite, db_session):
    tramite.estado_actual = "procesando_firma"
    db_session.commit()
    assert pedir(client, tramite, CAMPOS_CONTRATO).status_code == 409


def test_sin_plantilla_el_mensaje_es_simple(client, tramite, db_session):
    db_session.query(models.PlantillaDocumento).delete()
    db_session.commit()
    r = pedir(client, tramite, CAMPOS_CONTRATO)
    assert r.status_code == 409
    assert "plantilla" not in r.json()["detail"].lower()
    assert "puedes continuar" in r.json()["detail"].lower()


def test_si_falta_algo_del_agente_no_se_nombra_la_marca(client, tramite, db_session, subir):
    subir(docx_con("{{FOLIO}} {{BANCOLINK}}"), id_servicio=tramite.id_servicio)   # banco sin configurar
    r = pedir(client, tramite, CAMPOS_CONTRATO)
    assert r.status_code == 409 and "BANCOLINK" not in r.text and "banco" not in r.text.lower()


# ---------- conversión, caché y cola ----------

def test_mismos_datos_no_se_convierten_dos_veces(client, tramite, entorno):
    assert pedir(client, tramite, CAMPOS_CONTRATO).status_code == 200
    assert pedir(client, tramite, CAMPOS_CONTRATO).status_code == 200
    assert len(entorno) == 1                                  # la segunda salió de la caché
    assert pedir(client, tramite, {**CAMPOS_CONTRATO, "giro_principal": "Otro giro"}).status_code == 200
    assert len(entorno) == 2                                  # datos distintos: se arma de nuevo


def test_la_cache_vence(client, tramite, entorno, monkeypatch):
    assert pedir(client, tramite, CAMPOS_CONTRATO).status_code == 200
    monkeypatch.setattr(vista_previa, "CACHE_SEGUNDOS", -1)
    vista_previa.vaciar_cache()
    assert pedir(client, tramite, CAMPOS_CONTRATO).status_code == 200      # se guarda ya vencida
    assert pedir(client, tramite, CAMPOS_CONTRATO).status_code == 200
    assert len(entorno) == 3


def test_la_cache_no_crece_sin_limite(client, tramite, monkeypatch):
    monkeypatch.setattr(vista_previa, "CACHE_MAXIMO", 3)
    for n in range(6):
        assert pedir(client, tramite, {**CAMPOS_CONTRATO, "giro_principal": f"Giro {n}"}).status_code == 200
    assert len(vista_previa._cache) == 3


def test_cola_llena_responde_503_con_reintento(client, tramite, monkeypatch):
    def ocupado(docx, espera_maxima=None):
        raise ServidorOcupado("Hay muchas solicitudes en este momento. Intenta de nuevo en unos segundos.")

    monkeypatch.setattr("app.vista_previa.docx_a_pdf", ocupado)
    r = pedir(client, tramite, CAMPOS_CONTRATO)
    assert r.status_code == 503 and r.headers["retry-after"] == "5"


def test_la_espera_en_cola_es_corta(client, tramite, monkeypatch):
    pedidos = []
    monkeypatch.setattr("app.vista_previa.docx_a_pdf", lambda docx, espera_maxima=None: pedidos.append(espera_maxima) or PDF_FALSO)
    pedir(client, tramite, CAMPOS_CONTRATO)
    assert pedidos == [vista_previa.ESPERA_MAXIMA_SEGUNDOS] and vista_previa.ESPERA_MAXIMA_SEGUNDOS <= 10


def test_falla_la_conversion_sin_filtrar_detalles(client, tramite, monkeypatch):
    def fallar(docx, espera_maxima=None):
        raise ErrorConversion("No se pudo convertir el documento a PDF.", detalle="secreto interno")

    monkeypatch.setattr("app.vista_previa.docx_a_pdf", fallar)
    r = pedir(client, tramite, CAMPOS_CONTRATO)
    assert r.status_code == 502 and "secreto interno" not in r.text


# ---------- límites de uso ----------

class TestLimites:
    @pytest.fixture()
    def limite_activo(self):
        limiter.reset()
        limiter.enabled = True
        yield
        limiter.enabled = False
        limiter.reset()

    def test_por_codigo_10_por_hora(self, client, tramite, limite_activo):
        respuestas = [pedir(client, tramite, CAMPOS_CONTRATO).status_code for _ in range(11)]
        assert respuestas[:10] == [200] * 10 and respuestas[10] == 429

    def test_otro_codigo_no_se_ve_afectado(self, client, tramite, limite_activo):
        for _ in range(11):
            pedir(client, tramite, CAMPOS_CONTRATO)
        r = client.post("/api/tramites/codigo/ZZZZZZZZ/vista-previa", json={"campos": {}})
        assert r.status_code == 404                                       # no 429

    def test_por_ip_15_por_minuto(self, client, limite_activo):
        codigos = [f"ABCDE{n:03d}" for n in range(16)]
        respuestas = [client.post(f"/api/tramites/codigo/{c}/vista-previa", json={"campos": {}}).status_code for c in codigos]
        assert respuestas[:15] == [404] * 15 and respuestas[15] == 429

    def test_total_30_por_minuto_aunque_cambie_la_ip(self, client, limite_activo, monkeypatch):
        ips = itertools.count(1)
        monkeypatch.setattr("app.routers.tramites.get_remote_address", lambda request: f"10.0.0.{next(ips)}")
        codigos = [f"ABCDEF{n:02d}" for n in range(31)]
        respuestas = [client.post(f"/api/tramites/codigo/{c}/vista-previa", json={"campos": {}}).status_code for c in codigos]
        assert respuestas[:30] == [404] * 30 and respuestas[30] == 429