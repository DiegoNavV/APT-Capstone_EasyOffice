"""
Envio de un tramite a la API de firma: que guarde el id del documento, registre la aceptacion con la IP y el navegador del cliente, 
no duplique nada al reintentar y nunca lance un error.
La API de firma y la generacion del PDF se reemplazan por funciones falsas.
"""
import pytest

from app import envio_firma, firma_client, models
from app.documentos import DocumentoNoGenerable
from app.firma_client import ErrorFirma
from tests.test_valores_documento import tramite  # noqa: F401  (fixture)

IP = "200.1.2.3"
NAVEGADOR = "Mozilla/5.0 (prueba)"
PDF = b"%PDF-1.4 prueba"


@pytest.fixture()
def falsa(tmp_path, monkeypatch):
    """Reemplaza el PDF y la API de firma. Devuelve las llamadas hechas."""
    pdf = tmp_path / "tramite.pdf"
    pdf.write_bytes(PDF)
    llamadas = {"generar": 0, "crear": [], "aceptar": []}

    def generar(db, tramite):
        llamadas["generar"] += 1

    def crear_documento(**kw):
        llamadas["crear"].append(kw)
        return {"id": "11111111-2222-3333-4444-555555555555", "status": "pending"}

    def registrar_aceptacion(document_id, folio, ip, user_agent):
        llamadas["aceptar"].append((document_id, folio, ip, user_agent))
        return {"status": "completed"}

    monkeypatch.setattr(envio_firma.documentos, "generar", generar)
    monkeypatch.setattr(envio_firma.documentos, "ruta_del_documento", lambda tramite: pdf)
    monkeypatch.setattr(firma_client, "crear_documento", crear_documento)
    monkeypatch.setattr(firma_client, "registrar_aceptacion", registrar_aceptacion)
    return llamadas


@pytest.fixture()
def en_firma(db_session, tramite):  # noqa: F811
    """El tramite tal como queda cuando el cliente envio sus datos."""
    tramite.estado_actual = "procesando_firma"
    db_session.add(models.HistorialEstado(
        id_tramite=tramite.id_tramite, estado="procesando_firma", origen="cliente", comentario="Datos enviados.",
    ))
    db_session.commit()
    return tramite


def enviar(db_session, tramite):
    return envio_firma.enviar_a_firma(db_session, tramite, IP, NAVEGADOR)


def test_envia_el_documento_con_el_firmante_y_el_folio(db_session, en_firma, falsa):
    assert enviar(db_session, en_firma) is True

    crear = falsa["crear"][0]
    assert crear["pdf"] == PDF
    assert crear["folio"] == "LF-01-2026"
    assert crear["titulo"] == "Constitución de Sociedad"
    assert crear["firmante"] == {
        "name": "Oscar Contreras Benavides",
        "rut": "14144266-K",
        "email": "contacto@altus.cl",
        "represents_name": "Altus and Company Co. SpA",
        "represents_rut": "78526673-0",
    }


def test_nunca_envia_el_codigo_de_seguimiento(db_session, en_firma, falsa):
    enviar(db_session, en_firma)
    assert "ABCD2345" not in repr(falsa["crear"]) + repr(falsa["aceptar"])


def test_guarda_el_id_del_documento_en_la_base(db_session, en_firma, falsa):
    enviar(db_session, en_firma)

    db_session.expire_all()
    guardado = db_session.get(models.Tramite, en_firma.id_tramite)
    assert guardado.documento_firma_id == "11111111-2222-3333-4444-555555555555"
    assert guardado.estado_actual == "procesando_firma"   # el estado final lo fija el aviso de la API (webhook)


def test_registra_la_aceptacion_con_ip_y_navegador_del_cliente(db_session, en_firma, falsa):
    enviar(db_session, en_firma)
    assert falsa["aceptar"] == [("11111111-2222-3333-4444-555555555555", "LF-01-2026", IP, NAVEGADOR)]


def test_reintentar_no_crea_otro_documento(db_session, en_firma, falsa):
    enviar(db_session, en_firma)
    enviar(db_session, en_firma)

    assert falsa["generar"] == 1
    assert len(falsa["crear"]) == 1
    assert len(falsa["aceptar"]) == 2   # la API es idempotente con la misma clave


def test_si_falla_la_aceptacion_conserva_el_documento_y_reintenta_solo_eso(db_session, en_firma, falsa, monkeypatch):
    def cae(*args, **kw):
        raise ErrorFirma("sin conexion", reintentable=True)

    monkeypatch.setattr(firma_client, "registrar_aceptacion", cae)
    assert enviar(db_session, en_firma) is False

    db_session.expire_all()
    assert db_session.get(models.Tramite, en_firma.id_tramite).documento_firma_id is not None

    monkeypatch.undo()   # vuelve la API; se reemplazan de nuevo las funciones falsas por las de la prueba
    assert len(falsa["crear"]) == 1


def test_api_caida_al_crear_no_lanza_ni_deja_id(db_session, en_firma, falsa, monkeypatch):
    def cae(**kw):
        raise ErrorFirma("sin conexion", reintentable=True)

    monkeypatch.setattr(firma_client, "crear_documento", cae)
    assert enviar(db_session, en_firma) is False

    db_session.expire_all()
    guardado = db_session.get(models.Tramite, en_firma.id_tramite)
    assert guardado.documento_firma_id is None
    assert guardado.estado_actual == "procesando_firma"
    assert falsa["aceptar"] == []


def test_si_no_se_puede_generar_el_pdf_no_lanza(db_session, en_firma, falsa, monkeypatch):
    def falla(db, tramite):
        raise DocumentoNoGenerable("sin plantilla")

    monkeypatch.setattr(envio_firma.documentos, "generar", falla)
    assert enviar(db_session, en_firma) is False
    assert falsa["crear"] == []


def test_error_inesperado_tampoco_lanza(db_session, en_firma, falsa, monkeypatch):
    def revienta(**kw):
        raise RuntimeError("algo raro")

    monkeypatch.setattr(firma_client, "crear_documento", revienta)
    assert enviar(db_session, en_firma) is False


def test_solo_envia_si_esta_procesando_firma(db_session, tramite, falsa):  # noqa: F811
    assert tramite.estado_actual == "esperando_datos"
    assert enviar(db_session, tramite) is False
    assert falsa["crear"] == [] and falsa["generar"] == 0


def test_sin_folio_no_envia(db_session, en_firma, falsa):
    # El esquema exige folio y condiciones junto con la sucursal (ck_tramite_folio_con_sucursal y
    # ck_tramite_condiciones_con_sucursal): se quitan los tres.
    en_firma.folio = None
    en_firma.condiciones = None
    en_firma.id_sucursal = None
    db_session.commit()

    assert enviar(db_session, en_firma) is False
    assert falsa["crear"] == []


def test_sin_correo_de_la_empresa_no_envia(db_session, en_firma, falsa):
    en_firma.empresa.email = None
    db_session.commit()

    assert enviar(db_session, en_firma) is False
    assert falsa["crear"] == [] and falsa["generar"] == 0