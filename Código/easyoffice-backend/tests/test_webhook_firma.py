"""
Ruta publica del webhook de la API de firma: solo pasan avisos autenticos y recientes, y los que no se pueden aplicar ahora piden 
reintento. La descarga del PDF firmado se reemplaza por una funcion falsa.
"""
import hashlib
import hmac
import json
import time

import pytest

from app import firma_client, models
from tests.test_aviso_firma import (  # noqa: F401  (fixtures y datos compartidos)
    ID_DOCUMENTO, PDF_FIRMADO, carpeta_documentos, descarga, en_firma, estado,
)
from tests.test_valores_documento import tramite  # noqa: F401  (fixture que usa en_firma)

SECRETO = "secreto-de-prueba"
RUTA = "/api/webhooks/firma"


@pytest.fixture(autouse=True)
def secreto(monkeypatch):
    monkeypatch.setenv("FIRMA_WEBHOOK_SECRET", SECRETO)


def aviso(tipo="document.completed", **extra):
    return {"event": tipo, "document_id": ID_DOCUMENTO, "external_ref": "LF-01-2026", **extra}


def enviar(client, cuerpo=None, *, marca=None, secreto=SECRETO, firma=None, cabeceras=True):
    """Envia un aviso firmado como lo hace la API de firma. `cuerpo` puede ser un dict o bytes."""
    if cuerpo is None:
        cuerpo = aviso()
    if isinstance(cuerpo, dict):
        cuerpo = json.dumps(cuerpo).encode()
    marca = str(int(time.time())) if marca is None else marca
    if firma is None:
        firma = "sha256=" + hmac.new(secreto.encode(), marca.encode() + b"." + cuerpo, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json"}
    if cabeceras:
        headers.update({"X-Firma-Timestamp": marca, "X-Firma-Signature": firma})
    return client.post(RUTA, content=cuerpo, headers=headers)


class TestAutenticidad:
    def test_sin_cabeceras_se_rechaza(self, client, en_firma, descarga):
        assert enviar(client, cabeceras=False).status_code == 401
        assert descarga == []

    def test_firma_con_otro_secreto_se_rechaza(self, client, en_firma, descarga):
        assert enviar(client, secreto="otro-secreto").status_code == 401
        assert descarga == []

    def test_firma_invalida_no_cambia_el_tramite(self, client, en_firma, db_session, descarga):
        assert enviar(client, firma="sha256=" + "0" * 64).status_code == 401
        assert estado(db_session, en_firma) == "procesando_firma"

    def test_aviso_viejo_se_rechaza(self, client, en_firma, db_session, descarga):
        vieja = str(int(time.time()) - 3600)
        assert enviar(client, marca=vieja).status_code == 401
        assert estado(db_session, en_firma) == "procesando_firma"

    def test_cuerpo_alterado_despues_de_firmar_se_rechaza(self, client, en_firma, db_session, descarga):
        marca = str(int(time.time()))
        original = json.dumps(aviso("document.rejected")).encode()
        firma = "sha256=" + hmac.new(SECRETO.encode(), marca.encode() + b"." + original, hashlib.sha256).hexdigest()
        alterado = json.dumps(aviso("document.completed")).encode()

        assert enviar(client, alterado, marca=marca, firma=firma).status_code == 401
        assert estado(db_session, en_firma) == "procesando_firma"

    def test_no_pide_sesion_de_agente(self, client, en_firma, descarga):
        # Es publica: la llama la API de firma. La unica puerta es la firma del aviso.
        assert enviar(client).status_code == 200


class TestAvisosValidos:
    def test_completado_deja_el_tramite_firmado(self, client, en_firma, db_session, descarga, carpeta_documentos):
        r = enviar(client)

        assert r.status_code == 200
        assert r.json() == {"ok": True, "resultado": "firmado"}
        assert estado(db_session, en_firma) == "firmado"
        assert (carpeta_documentos / f"tramite_{en_firma.id_tramite}.pdf").read_bytes() == PDF_FIRMADO

    def test_rechazo_deja_el_tramite_rechazado(self, client, en_firma, db_session):
        r = enviar(client, aviso("document.rejected", rejection_reason="Datos mal"))

        assert r.status_code == 200
        assert r.json()["resultado"] == "rechazado"
        assert estado(db_session, en_firma) == "rechazado"

    def test_aviso_repetido_responde_ok_sin_cambios(self, client, en_firma, descarga):
        enviar(client)
        r = enviar(client)

        assert r.status_code == 200
        assert r.json()["resultado"] == "sin_cambios"
        assert descarga == [ID_DOCUMENTO]

    def test_documento_desconocido_responde_ok_y_se_ignora(self, client, en_firma, db_session):
        r = enviar(client, {**aviso(), "document_id": "00000000-0000-0000-0000-000000000000"})

        assert r.status_code == 200
        assert r.json()["resultado"] == "ignorado"
        assert estado(db_session, en_firma) == "procesando_firma"


class TestReintentos:
    def test_si_no_se_puede_descargar_pide_reintento_y_despues_funciona(
        self, client, en_firma, db_session, monkeypatch
    ):
        def cae(document_id):
            raise firma_client.ErrorFirma("sin conexion", reintentable=True)

        monkeypatch.setattr(firma_client, "descargar_firmado", cae)
        assert enviar(client).status_code == 503
        assert estado(db_session, en_firma) == "procesando_firma"

        # La API de firma reintenta el mismo aviso y esta vez la descarga funciona.
        monkeypatch.setattr(firma_client, "descargar_firmado", lambda document_id: PDF_FIRMADO)
        assert enviar(client).status_code == 200
        assert estado(db_session, en_firma) == "firmado"

    def test_pdf_invalido_pide_reintento(self, client, en_firma, db_session, monkeypatch):
        monkeypatch.setattr(firma_client, "descargar_firmado", lambda document_id: b"no soy un pdf")

        assert enviar(client).status_code == 503
        assert estado(db_session, en_firma) == "procesando_firma"


class TestCuerposRaros:
    def test_json_invalido(self, client):
        assert enviar(client, b"esto no es json").status_code == 400

    def test_json_que_no_es_un_objeto(self, client):
        assert enviar(client, b"[1, 2, 3]").status_code == 400

    def test_cuerpo_demasiado_grande(self, client):
        assert enviar(client, b"x" * (70 * 1024)).status_code == 413