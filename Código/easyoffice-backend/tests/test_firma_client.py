"""
Cliente de la API de firma: que arme bien las peticiones del contrato y que clasifique los errores.
La API real no se llama: se reemplaza httpx.request por una funcion falsa que guarda lo recibido.
"""
import json

import httpx
import pytest

from app import firma_client
from app.firma_client import ErrorFirma


class Falsa:
    """Reemplazo de httpx.request: guarda la peticion y devuelve la respuesta indicada."""

    def __init__(self, estado=200, cuerpo=None, contenido=b"", error=None):
        self.estado = estado
        self.cuerpo = cuerpo if cuerpo is not None else {}
        self.contenido = contenido
        self.error = error
        self.llamadas = []

    def __call__(self, metodo, url, **kw):
        self.llamadas.append({"metodo": metodo, "url": url, **kw})
        if self.error:
            raise self.error
        peticion = httpx.Request(metodo, url)
        if self.contenido:
            return httpx.Response(self.estado, content=self.contenido, request=peticion)
        return httpx.Response(self.estado, json=self.cuerpo, request=peticion)


@pytest.fixture()
def falsa(monkeypatch):
    monkeypatch.setenv("FIRMA_API_URL", "http://firma-api:8000/api/v1")
    monkeypatch.setenv("FIRMA_API_KEY", "fk_test_clave")
    monkeypatch.setenv("FIRMA_CALLBACK_URL", "http://backend:8000/api/webhooks/firma")
    f = Falsa(cuerpo={"id": "6f1c", "status": "pending"})
    monkeypatch.setattr(firma_client.httpx, "request", f)
    return f


FIRMANTE = {"name": "Juan Perez", "rut": "12.345.678-5", "email": "juan@cliente.cl"}


class TestCrearDocumento:
    def test_arma_la_peticion_del_contrato(self, falsa):
        r = firma_client.crear_documento(pdf=b"%PDF-1.4", titulo="Contrato", folio="LF-0152-2026", firmante=FIRMANTE)

        assert r == {"id": "6f1c", "status": "pending"}
        llamada = falsa.llamadas[0]
        assert llamada["metodo"] == "POST"
        assert llamada["url"] == "http://firma-api:8000/api/v1/documents"
        assert llamada["headers"]["X-API-Key"] == "fk_test_clave"
        assert llamada["headers"]["Idempotency-Key"] == "doc-LF-0152-2026"
        assert llamada["files"]["file"] == ("LF-0152-2026.pdf", b"%PDF-1.4", "application/pdf")

    def test_el_folio_viaja_como_referencia_externa(self, falsa):
        firma_client.crear_documento(pdf=b"x", titulo="Contrato", folio="LF-0152-2026", firmante=FIRMANTE)

        datos = json.loads(falsa.llamadas[0]["data"]["data"])
        assert datos["external_ref"] == "LF-0152-2026"
        assert datos["title"] == "Contrato"
        assert datos["signers"] == [FIRMANTE]
        assert datos["callback_url"] == "http://backend:8000/api/webhooks/firma"


class TestAceptacionYRechazo:
    def test_aceptacion_lleva_ip_navegador_y_consentimiento(self, falsa):
        firma_client.registrar_aceptacion("6f1c", "LF-0152-2026", "200.1.2.3", "Mozilla/5.0")

        llamada = falsa.llamadas[0]
        assert llamada["url"].endswith("/documents/6f1c/client-signature")
        assert llamada["json"] == {"ip": "200.1.2.3", "user_agent": "Mozilla/5.0", "consent": True}
        assert llamada["headers"]["Idempotency-Key"] == "firma-LF-0152-2026"

    def test_rechazo_lleva_motivo(self, falsa):
        firma_client.registrar_rechazo("6f1c", "LF-0152-2026", "200.1.2.3", "Mozilla/5.0", "Datos mal")

        llamada = falsa.llamadas[0]
        assert llamada["url"].endswith("/documents/6f1c/client-rejection")
        assert llamada["json"]["reason"] == "Datos mal"
        assert llamada["headers"]["Idempotency-Key"] == "rechazo-LF-0152-2026"


class TestDescarga:
    def test_pide_la_version_firmada_y_devuelve_los_bytes(self, monkeypatch):
        f = Falsa(contenido=b"%PDF-firmado")
        monkeypatch.setattr(firma_client.httpx, "request", f)

        assert firma_client.descargar_firmado("6f1c") == b"%PDF-firmado"
        assert f.llamadas[0]["url"].endswith("/documents/6f1c/download?version=signed")


class TestErrores:
    @pytest.mark.parametrize("estado", [500, 502, 503, 429])
    def test_error_del_servidor_es_reintentable(self, monkeypatch, estado):
        monkeypatch.setattr(firma_client.httpx, "request", Falsa(estado=estado))
        with pytest.raises(ErrorFirma) as exc:
            firma_client.descargar_firmado("6f1c")
        assert exc.value.reintentable is True
        assert exc.value.estado_http == estado

    @pytest.mark.parametrize("estado", [400, 401, 404, 409, 422])
    def test_rechazo_de_la_api_no_es_reintentable(self, monkeypatch, estado):
        monkeypatch.setattr(firma_client.httpx, "request", Falsa(estado=estado))
        with pytest.raises(ErrorFirma) as exc:
            firma_client.descargar_firmado("6f1c")
        assert exc.value.reintentable is False
        assert exc.value.estado_http == estado

    def test_api_caida_es_reintentable(self, monkeypatch):
        monkeypatch.setattr(firma_client.httpx, "request", Falsa(error=httpx.ConnectError("sin conexion")))
        with pytest.raises(ErrorFirma) as exc:
            firma_client.descargar_firmado("6f1c")
        assert exc.value.reintentable is True
        assert exc.value.estado_http is None

    def test_demora_excesiva_es_reintentable(self, monkeypatch):
        monkeypatch.setattr(firma_client.httpx, "request", Falsa(error=httpx.ReadTimeout("lento")))
        with pytest.raises(ErrorFirma) as exc:
            firma_client.descargar_firmado("6f1c")
        assert exc.value.reintentable is True

    def test_el_mensaje_de_error_no_incluye_el_cuerpo_de_la_respuesta(self, monkeypatch):
        monkeypatch.setattr(firma_client.httpx, "request", Falsa(estado=422, cuerpo={"detail": "RUT 12.345.678-5 invalido"}))
        with pytest.raises(ErrorFirma) as exc:
            firma_client.crear_documento(pdf=b"x", titulo="T", folio="LF-0152-2026", firmante=FIRMANTE)
        assert "12.345.678-5" not in str(exc.value)