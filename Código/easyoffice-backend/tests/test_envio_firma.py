"""
Envio de un tramite a la API de firma: que guarde el id del documento, registre la aceptacion con la IP y el navegador del cliente, 
no duplique nada al reintentar y nunca lance un error.
La API de firma y la generacion del PDF se reemplazan por funciones falsas.
"""
from datetime import timedelta

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

# ---------- Envio en segundo plano ----------

def test_en_segundo_plano_abre_su_propia_sesion_y_envia(db_session, TestingSessionLocal, en_firma, falsa, monkeypatch):
    monkeypatch.setattr(envio_firma, "SessionLocal", TestingSessionLocal)

    envio_firma.enviar_en_segundo_plano(en_firma.id_tramite, IP, NAVEGADOR)

    assert len(falsa["crear"]) == 1
    assert falsa["aceptar"] == [("11111111-2222-3333-4444-555555555555", "LF-01-2026", IP, NAVEGADOR)]
    db_session.expire_all()
    assert db_session.get(models.Tramite, en_firma.id_tramite).documento_firma_id == "11111111-2222-3333-4444-555555555555"


def test_en_segundo_plano_cierra_su_sesion(TestingSessionLocal, en_firma, falsa, monkeypatch):
    sesiones = []

    def fabrica():
        sesion = TestingSessionLocal()
        cerrar = sesion.close
        sesion.close = lambda: (sesiones.append("cerrada"), cerrar())
        return sesion

    monkeypatch.setattr(envio_firma, "SessionLocal", fabrica)
    envio_firma.enviar_en_segundo_plano(en_firma.id_tramite, IP, NAVEGADOR)

    assert sesiones == ["cerrada"]


def test_en_segundo_plano_con_tramite_inexistente_no_lanza(TestingSessionLocal, falsa, monkeypatch):
    monkeypatch.setattr(envio_firma, "SessionLocal", TestingSessionLocal)

    envio_firma.enviar_en_segundo_plano(9999, IP, NAVEGADOR)

    assert falsa["crear"] == [] and falsa["aceptar"] == []


def test_en_segundo_plano_error_inesperado_no_lanza(TestingSessionLocal, en_firma, falsa, monkeypatch):
    def revienta(db, tramite, ip, user_agent):
        raise RuntimeError("algo raro")

    monkeypatch.setattr(envio_firma, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(envio_firma, "enviar_a_firma", revienta)

    envio_firma.enviar_en_segundo_plano(en_firma.id_tramite, IP, NAVEGADOR)

# ---------- Correo del firmante ----------

def _sin_correo_de_empresa(db_session, tramite, solicitante_es_representante=None):
    """Quita el correo de la empresa y, si se indica, registra lo que respondio el cliente al enviar
    sus datos ('¿eres el representante legal?')."""
    tramite.empresa.email = None
    if solicitante_es_representante is not None:
        db_session.add(models.DatosEmpresaTramite(
            id_tramite=tramite.id_tramite,
            solicitante_es_representante=solicitante_es_representante,
            version_consentimiento="v1",
        ))
    db_session.commit()


def test_el_correo_de_la_empresa_tiene_prioridad(db_session, en_firma):
    db_session.add(models.DatosEmpresaTramite(
        id_tramite=en_firma.id_tramite, solicitante_es_representante=True, version_consentimiento="v1",
    ))
    db_session.commit()

    assert envio_firma.correo_del_firmante(en_firma) == "contacto@altus.cl"


def test_sin_correo_de_empresa_usa_el_del_cliente_si_es_el_representante(db_session, en_firma, falsa):
    _sin_correo_de_empresa(db_session, en_firma, solicitante_es_representante=True)

    assert envio_firma.correo_del_firmante(en_firma) == "cliente@prueba.cl"
    assert enviar(db_session, en_firma) is True
    assert falsa["crear"][0]["firmante"]["email"] == "cliente@prueba.cl"


def test_sin_correo_de_empresa_y_cliente_no_representante_no_hay_correo(db_session, en_firma, falsa):
    _sin_correo_de_empresa(db_session, en_firma, solicitante_es_representante=False)

    assert envio_firma.correo_del_firmante(en_firma) is None
    assert enviar(db_session, en_firma) is False
    assert falsa["crear"] == [] and falsa["generar"] == 0


def test_sin_correo_de_empresa_ni_registro_del_envio_no_hay_correo(db_session, en_firma):
    _sin_correo_de_empresa(db_session, en_firma)

    assert envio_firma.correo_del_firmante(en_firma) is None


def test_representante_sin_correo_de_cliente_no_hay_correo(db_session, en_firma):
    _sin_correo_de_empresa(db_session, en_firma, solicitante_es_representante=True)
    # El esquema exige algun contacto (ck_cliente_algun_contacto): se deja solo el telefono.
    en_firma.cliente.telefono = "912345678"
    en_firma.cliente.email = None
    db_session.commit()

    assert envio_firma.correo_del_firmante(en_firma) is None


# ---------- Aviso al agente ----------

def _ahora(tramite, segundos):
    """La hora actual simulada: `segundos` despues de la ultima actualizacion del tramite."""
    return tramite.fecha_actualizacion + timedelta(seconds=segundos)


def test_sin_correo_se_avisa_de_inmediato(db_session, en_firma):
    _sin_correo_de_empresa(db_session, en_firma, solicitante_es_representante=False)
    db_session.refresh(en_firma)

    assert envio_firma.motivo_envio_pendiente(en_firma, _ahora(en_firma, 0)) == envio_firma.MOTIVO_SIN_CORREO


def test_con_correo_y_reciente_no_se_avisa(db_session, en_firma):
    db_session.refresh(en_firma)
    assert envio_firma.motivo_envio_pendiente(en_firma, _ahora(en_firma, 10)) is None


def test_con_correo_pasado_el_tiempo_se_avisa_que_no_se_completo(db_session, en_firma):
    db_session.refresh(en_firma)
    ahora = _ahora(en_firma, envio_firma.ESPERA_ENVIO_SEGUNDOS + 1)

    assert envio_firma.motivo_envio_pendiente(en_firma, ahora) == envio_firma.MOTIVO_NO_COMPLETADO


def test_justo_en_el_limite_todavia_no_se_avisa(db_session, en_firma):
    db_session.refresh(en_firma)
    ahora = _ahora(en_firma, envio_firma.ESPERA_ENVIO_SEGUNDOS)

    assert envio_firma.motivo_envio_pendiente(en_firma, ahora) is None


def test_ya_enviado_a_firma_y_reciente_no_se_avisa_aunque_falte_el_correo(db_session, en_firma):
    # El documento ya salio: que ahora no se encuentre el correo ya no es el problema.
    _sin_correo_de_empresa(db_session, en_firma, solicitante_es_representante=False)
    en_firma.documento_firma_id = "11111111-2222-3333-4444-555555555555"
    db_session.commit()
    db_session.refresh(en_firma)

    assert envio_firma.motivo_envio_pendiente(en_firma, _ahora(en_firma, 10)) is None


def test_ya_enviado_a_firma_pero_sin_avanzar_se_avisa(db_session, en_firma):
    en_firma.documento_firma_id = "11111111-2222-3333-4444-555555555555"
    db_session.commit()
    db_session.refresh(en_firma)
    ahora = _ahora(en_firma, envio_firma.ESPERA_ENVIO_SEGUNDOS + 60)

    assert envio_firma.motivo_envio_pendiente(en_firma, ahora) == envio_firma.MOTIVO_NO_COMPLETADO


def test_un_tramite_que_no_esta_en_firma_nunca_avisa(db_session, tramite):  # noqa: F811
    assert tramite.estado_actual == "esperando_datos"
    assert envio_firma.motivo_envio_pendiente(tramite, _ahora(tramite, 99999)) is None


def test_un_tramite_firmado_no_avisa(db_session, en_firma):
    db_session.add(models.HistorialEstado(
        id_tramite=en_firma.id_tramite, estado="firmado", origen="sistema", comentario="Firmado.",
    ))
    db_session.commit()
    db_session.refresh(en_firma)

    assert envio_firma.motivo_envio_pendiente(en_firma, _ahora(en_firma, 99999)) is None