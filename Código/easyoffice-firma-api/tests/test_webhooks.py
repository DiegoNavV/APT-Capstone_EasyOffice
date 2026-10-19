import hashlib
import hmac
import time

import httpx
import pytest

from app import models
from app.db.session import SessionLocal
from app.services import webhooks


class TestFirmaHmac:
    def test_firma_cubre_timestamp_y_cuerpo(self):
        cuerpo = b'{"event":"document.completed"}'
        esperado = "sha256=" + hmac.new(b"secreto-de-pruebas", b"1700000000." + cuerpo, hashlib.sha256).hexdigest()
        assert webhooks.sign_body(cuerpo, "1700000000") == esperado

    def test_verificacion_del_receptor(self):
        cuerpo = b'{"event":"document.completed"}'
        ahora = str(int(time.time()))
        firma = webhooks.sign_body(cuerpo, ahora)
        assert webhooks.verify_signature(cuerpo, ahora, firma, "secreto-de-pruebas") is True
        # Cuerpo alterado, secreto distinto o aviso viejo (> 5 minutos): se rechaza.
        assert webhooks.verify_signature(cuerpo + b" ", ahora, firma, "secreto-de-pruebas") is False
        assert webhooks.verify_signature(cuerpo, ahora, firma, "otro-secreto") is False
        viejo = str(int(time.time()) - 600)
        assert webhooks.verify_signature(cuerpo, viejo, webhooks.sign_body(cuerpo, viejo), "secreto-de-pruebas") is False
        assert webhooks.verify_signature(cuerpo, "no-es-numero", firma, "secreto-de-pruebas") is False

    def test_cuerpo_canonico_estable(self):
        assert webhooks.body_bytes({"b": 1, "a": 2}) == webhooks.body_bytes({"a": 2, "b": 1})


class TestCallbackUrl:
    @pytest.mark.parametrize("url", [
        "http://backend:8000/api/webhooks/firma",
        "https://localhost/hook",
    ])
    def test_permitidas(self, url):
        assert webhooks.validate_callback_url(url) == url

    @pytest.mark.parametrize("url", [
        "ftp://backend/x",
        "http://evil.example/hook",
        "http://169.254.169.254/latest/meta-data",
        "http://user:pass@backend/hook",
        "no-es-url",
    ])
    def test_rechazadas(self, url):
        with pytest.raises(webhooks.CallbackUrlNotAllowed):
            webhooks.validate_callback_url(url)


def _entrega(db) -> models.WebhookDelivery:
    entrega = models.WebhookDelivery(
        document_id="doc-1", event="document.completed", url="http://backend:8000/hook",
        payload={"event": "document.completed", "document_id": "doc-1"},
    )
    db.add(entrega)
    db.commit()
    return entrega


class TestEntrega:
    def test_entrega_exitosa_con_headers(self, monkeypatch):
        recibido = {}

        def falso_post(url, content, headers, **kw):
            recibido.update(url=url, content=content, headers=headers)
            return httpx.Response(200)

        monkeypatch.setattr(httpx, "post", falso_post)
        with SessionLocal() as db:
            entrega = _entrega(db)
            assert webhooks.deliver(db, entrega.id) is True
            db.refresh(entrega)
            assert entrega.status == "delivered"
            assert entrega.attempts == 1
        h = recibido["headers"]
        assert h["X-Firma-Event"] == "document.completed"
        assert webhooks.verify_signature(recibido["content"], h["X-Firma-Timestamp"], h["X-Firma-Signature"], "secreto-de-pruebas")

    def test_fallos_hasta_agotar_intentos(self, monkeypatch):
        monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(500))
        with SessionLocal() as db:
            entrega = _entrega(db)
            for _ in range(6):  # WEBHOOK_MAX_ATTEMPTS por defecto
                assert webhooks.deliver(db, entrega.id) is False
            db.refresh(entrega)
            assert entrega.status == "failed"
            assert entrega.last_status_code == 500

    def test_error_de_red_queda_pendiente(self, monkeypatch):
        def caido(*a, **k):
            raise httpx.ConnectError("sin conexión")

        monkeypatch.setattr(httpx, "post", caido)
        with SessionLocal() as db:
            entrega = _entrega(db)
            assert webhooks.deliver(db, entrega.id) is False
            db.refresh(entrega)
            assert entrega.status == "pending"
            assert entrega.last_error == "ConnectError"
