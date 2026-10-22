"""Flujo completo: subir PDF -> aceptación del cliente -> firma automática -> descarga -> verificación."""
import hashlib
import io
import json
from datetime import datetime, timedelta, timezone

import pytest
from pypdf import PdfReader

from app import models
from app.db.session import SessionLocal
from app.services import audit
from helpers import OTRA_API_KEY, hacer_pdf

DATOS = {
    "title": "Contrato de servicio",
    "external_ref": "LF-0152-2026",
    "signers": [
        {
            "name": "Juan Pérez",
            "email": "juan@cliente.cl",
            "rut": "12.345.678-5",
            "represents_name": "Empresa Cliente SpA",
            "represents_rut": "76.543.210-3",
        }
    ],
    "callback_url": "http://backend:8000/api/webhooks/firma",
}

EVIDENCIA = {"ip": "200.1.2.3", "user_agent": "Mozilla/5.0 (Windows NT 10.0)", "consent": True}


def subir(client, auth, pdf, datos=None, headers=None):
    return client.post(
        "/api/v1/documents",
        files={"file": ("contrato.pdf", pdf, "application/pdf")},
        data={"data": json.dumps(datos or DATOS)},
        headers={**auth, **(headers or {})},
    )


def firmar_cliente(client, auth, doc_id, evidencia=None, headers=None):
    return client.post(
        f"/api/v1/documents/{doc_id}/client-signature",
        json=evidencia or EVIDENCIA,
        headers={**auth, **(headers or {})},
    )


# ---------- Crear ----------

class TestCrear:
    def test_crea_documento_pendiente(self, client, auth, storage, pdf_bytes):
        resp = subir(client, auth, pdf_bytes)
        assert resp.status_code == 201, resp.text
        doc = resp.json()
        assert doc["status"] == "pending"
        assert doc["original_sha256"] == hashlib.sha256(pdf_bytes).hexdigest()
        assert doc["signed_sha256"] is None
        assert doc["external_ref"] == "LF-0152-2026"
        assert doc["expires_at"] is not None
        # Persona + firma automática de la organización al final.
        assert [s["kind"] for s in doc["signers"]] == ["person", "organization_auto"]
        assert doc["signers"][0]["rut"] == "12345678-5"  # RUT normalizado
        assert doc["signers"][1]["name"] == "Easy Office SpA"
        assert storage.objects[f"documents/{doc['id']}/original.pdf"] == pdf_bytes

    def test_sin_firma_de_organizacion(self, client, auth, storage, pdf_bytes):
        resp = subir(client, auth, pdf_bytes, {**DATOS, "auto_organization_signature": False})
        assert [s["kind"] for s in resp.json()["signers"]] == ["person"]

    def test_sin_api_key_401(self, client, storage, pdf_bytes):
        resp = subir(client, {}, pdf_bytes)
        assert resp.status_code == 401

    def test_api_key_incorrecta_401(self, client, storage, pdf_bytes):
        resp = subir(client, {"X-API-Key": "fk_test_inventada"}, pdf_bytes)
        assert resp.status_code == 401

    def test_archivo_no_pdf_422(self, client, auth, storage):
        resp = subir(client, auth, b"esto no es un pdf")
        assert resp.status_code == 422
        assert "PDF" in resp.text

    def test_data_no_json_422(self, client, auth, storage, pdf_bytes):
        resp = client.post(
            "/api/v1/documents",
            files={"file": ("c.pdf", pdf_bytes, "application/pdf")},
            data={"data": "{no es json"},
            headers=auth,
        )
        assert resp.status_code == 422

    @pytest.mark.parametrize("cambio", [
        {"signers": []},
        {"title": ""},
        {"signers": [{"name": "X", "rut": "12.345.678-9"}]},  # dígito verificador incorrecto
        {"signers": [{"name": "X", "email": "no-es-correo"}]},
        {"campo_desconocido": 1},
        {"client_verification": "otp"},  # aún no disponible
        {"expires_in_days": 0},
        {"expires_in_days": 91},
    ])
    def test_datos_invalidos_422(self, client, auth, storage, pdf_bytes, cambio):
        resp = subir(client, auth, pdf_bytes, {**DATOS, **cambio})
        assert resp.status_code == 422, resp.text

    def test_callback_a_host_no_permitido_422(self, client, auth, storage, pdf_bytes):
        resp = subir(client, auth, pdf_bytes, {**DATOS, "callback_url": "http://169.254.169.254/latest"})
        assert resp.status_code == 422
        assert "no está permitido" in resp.text


# ---------- Idempotencia ----------

class TestIdempotencia:
    def test_misma_clave_mismo_contenido_no_duplica(self, client, auth, storage, pdf_bytes):
        r1 = subir(client, auth, pdf_bytes, headers={"Idempotency-Key": "tramite-ABCD1234"})
        r2 = subir(client, auth, pdf_bytes, headers={"Idempotency-Key": "tramite-ABCD1234"})
        assert r1.status_code == r2.status_code == 201
        assert r1.json()["id"] == r2.json()["id"]
        assert r2.headers.get("Idempotent-Replayed") == "true"
        with SessionLocal() as db:
            assert db.query(models.Document).count() == 1

    def test_misma_clave_contenido_distinto_409(self, client, auth, storage, pdf_bytes):
        subir(client, auth, pdf_bytes, headers={"Idempotency-Key": "k1"})
        resp = subir(client, auth, hacer_pdf("otro"), headers={"Idempotency-Key": "k1"})
        assert resp.status_code == 409

    def test_firma_cliente_repetida_no_falla(self, client, auth, storage, pdf_bytes):
        doc_id = subir(client, auth, pdf_bytes).json()["id"]
        r1 = firmar_cliente(client, auth, doc_id, headers={"Idempotency-Key": "firma-1"})
        r2 = firmar_cliente(client, auth, doc_id, headers={"Idempotency-Key": "firma-1"})
        assert r1.status_code == r2.status_code == 200
        assert r1.json()["signed_sha256"] == r2.json()["signed_sha256"]


# ---------- Firma ----------

class TestFirma:
    def test_flujo_completo(self, client, auth, storage, pdf_bytes, encolados):
        doc_id = subir(client, auth, pdf_bytes).json()["id"]
        resp = firmar_cliente(client, auth, doc_id)
        assert resp.status_code == 200, resp.text
        doc = resp.json()
        assert doc["status"] == "completed"
        assert doc["signature_type"] == "pades"
        assert all(s["status"] == "signed" for s in doc["signers"])
        assert doc["links"]["download_signed"]

        firmado = storage.objects[f"documents/{doc_id}/signed.pdf"]
        assert hashlib.sha256(firmado).hexdigest() == doc["signed_sha256"]
        # El original + la hoja de evidencias.
        lector = PdfReader(io.BytesIO(firmado))
        assert len(lector.pages) == 2
        hoja = lector.pages[-1].extract_text()
        assert "HOJA DE EVIDENCIAS" in hoja
        assert "200.1.2.3" in hoja
        assert "Juan Pérez" in hoja
        # Se encoló el webhook de documento completado.
        assert len(encolados) == 1

    def test_evidencia_guardada(self, client, auth, storage, pdf_bytes):
        doc_id = subir(client, auth, pdf_bytes).json()["id"]
        firmar_cliente(client, auth, doc_id)
        with SessionLocal() as db:
            cliente = db.query(models.Signer).filter_by(document_id=doc_id, kind="person").one()
            assert cliente.evidence["ip"] == "200.1.2.3"
            assert cliente.evidence["consent"] is True
            assert cliente.evidence["document_sha256"] == hashlib.sha256(pdf_bytes).hexdigest()

    def test_sin_consentimiento_422(self, client, auth, storage, pdf_bytes):
        doc_id = subir(client, auth, pdf_bytes).json()["id"]
        resp = firmar_cliente(client, auth, doc_id, {**EVIDENCIA, "consent": False})
        assert resp.status_code == 422

    def test_consentimiento_no_booleano_422(self, client, auth, storage, pdf_bytes):
        doc_id = subir(client, auth, pdf_bytes).json()["id"]
        resp = firmar_cliente(client, auth, doc_id, {**EVIDENCIA, "consent": "true"})
        assert resp.status_code == 422

    def test_ip_invalida_422(self, client, auth, storage, pdf_bytes):
        doc_id = subir(client, auth, pdf_bytes).json()["id"]
        resp = firmar_cliente(client, auth, doc_id, {**EVIDENCIA, "ip": "999.1.1.1"})
        assert resp.status_code == 422

    def test_firmar_documento_completado_409(self, client, auth, storage, pdf_bytes):
        doc_id = subir(client, auth, pdf_bytes).json()["id"]
        firmar_cliente(client, auth, doc_id)
        assert firmar_cliente(client, auth, doc_id).status_code == 409

    def test_dos_firmantes_en_orden(self, client, auth, storage, pdf_bytes):
        datos = {**DATOS, "signers": [{"name": "Primero"}, {"name": "Segundo"}]}
        doc = subir(client, auth, pdf_bytes, datos).json()
        segundo = doc["signers"][1]["id"]
        # El segundo no puede firmar antes que el primero.
        resp = firmar_cliente(client, auth, doc["id"], {**EVIDENCIA, "signer_id": segundo})
        assert resp.status_code == 409
        r1 = firmar_cliente(client, auth, doc["id"])
        assert r1.json()["status"] == "pending"
        r2 = firmar_cliente(client, auth, doc["id"])
        assert r2.json()["status"] == "completed"

    def test_sello_falla_entrega_sin_sello(self, client, auth, storage, pdf_bytes, monkeypatch):
        from app.services import pdf as pdf_service

        def romper(*a, **k):
            raise RuntimeError("sin pyhanko")

        monkeypatch.setattr(pdf_service, "sign_pades", romper)
        doc_id = subir(client, auth, pdf_bytes).json()["id"]
        doc = firmar_cliente(client, auth, doc_id).json()
        assert doc["status"] == "completed"
        assert doc["signature_type"] == "none"


# ---------- Consultas, descarga, aislamiento ----------

class TestConsultas:
    def test_get(self, client, auth, storage, pdf_bytes):
        doc_id = subir(client, auth, pdf_bytes).json()["id"]
        resp = client.get(f"/api/v1/documents/{doc_id}", headers=auth)
        assert resp.status_code == 200
        assert resp.json()["id"] == doc_id

    def test_otro_cliente_no_ve_el_documento_404(self, client, auth, storage, pdf_bytes):
        doc_id = subir(client, auth, pdf_bytes).json()["id"]
        otro = {"X-API-Key": OTRA_API_KEY}
        assert client.get(f"/api/v1/documents/{doc_id}", headers=otro).status_code == 404
        assert firmar_cliente(client, otro, doc_id).status_code == 404

    def test_inexistente_404(self, client, auth, storage):
        assert client.get("/api/v1/documents/no-existe", headers=auth).status_code == 404

    def test_descargar_original_y_firmado(self, client, auth, storage, pdf_bytes):
        doc_id = subir(client, auth, pdf_bytes).json()["id"]
        # Antes de firmar no hay versión firmada.
        assert client.get(f"/api/v1/documents/{doc_id}/download", headers=auth).status_code == 409
        orig = client.get(f"/api/v1/documents/{doc_id}/download?version=original", headers=auth)
        assert orig.status_code == 200
        assert orig.content == pdf_bytes
        assert orig.headers["content-type"] == "application/pdf"
        firmar_cliente(client, auth, doc_id)
        firmado = client.get(f"/api/v1/documents/{doc_id}/download", headers=auth)
        assert firmado.status_code == 200
        assert firmado.content.startswith(b"%PDF")
        assert "LF-0152-2026-signed.pdf" in firmado.headers["content-disposition"]

    def test_cancelar(self, client, auth, storage, pdf_bytes):
        doc_id = subir(client, auth, pdf_bytes).json()["id"]
        resp = client.post(f"/api/v1/documents/{doc_id}/cancel", headers=auth)
        assert resp.json()["status"] == "cancelled"
        assert firmar_cliente(client, auth, doc_id).status_code == 409
        assert client.post(f"/api/v1/documents/{doc_id}/cancel", headers=auth).status_code == 409


# ---------- Verificación y auditoría ----------

class TestVerificacion:
    def test_verificar_firmado_y_original(self, client, auth, storage, pdf_bytes):
        doc_id = subir(client, auth, pdf_bytes).json()["id"]
        doc = firmar_cliente(client, auth, doc_id).json()
        # Pública: sin API key.
        r = client.get(f"/api/v1/verify/{doc['signed_sha256']}")
        assert r.json() == {
            "found": True, "match": "signed", "status": "completed", "signature_type": "pades",
            "completed_at": r.json()["completed_at"], "signers_signed": 2,
        }
        r = client.get(f"/api/v1/verify/{doc['original_sha256']}")
        assert r.json()["match"] == "original"

    def test_verificar_desconocido(self, client):
        r = client.get("/api/v1/verify/" + "a" * 64)
        assert r.json()["found"] is False

    def test_verificar_hash_mal_formado_422(self, client):
        assert client.get("/api/v1/verify/abc").status_code == 422

    def test_verificar_no_expone_datos_personales(self, client, auth, storage, pdf_bytes):
        doc = subir(client, auth, pdf_bytes).json()
        texto = client.get(f"/api/v1/verify/{doc['original_sha256']}").text
        for prohibido in ("Juan", "12345678", "LF-0152", "juan@"):
            assert prohibido not in texto

    def test_evidencia_y_cadena_integra(self, client, auth, storage, pdf_bytes):
        doc_id = subir(client, auth, pdf_bytes).json()["id"]
        firmar_cliente(client, auth, doc_id)
        r = client.get(f"/api/v1/documents/{doc_id}/evidence", headers=auth)
        datos = r.json()
        assert datos["chain_valid"] is True
        tipos = [e["event_type"] for e in datos["events"]]
        assert tipos == ["document.created", "signer.signed", "signer.signed", "document.completed"]

    def test_cadena_detecta_alteracion(self, client, auth, storage, pdf_bytes):
        doc_id = subir(client, auth, pdf_bytes).json()["id"]
        firmar_cliente(client, auth, doc_id)
        with SessionLocal() as db:
            evento = db.query(models.AuditEvent).order_by(models.AuditEvent.id).first()
            evento.payload = {**evento.payload, "client_id": "manipulado"}
            db.commit()
            ok, alterado = audit.verify_chain(db)
            assert ok is False
            assert alterado == evento.id


# ---------- Rechazo y expiración (acordado con el equipo del CRM) ----------

def _vencer(doc_id: str) -> None:
    with SessionLocal() as db:
        documento = db.get(models.Document, doc_id)
        documento.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()


class TestRechazo:
    def test_cliente_rechaza(self, client, auth, storage, pdf_bytes, encolados):
        doc_id = subir(client, auth, pdf_bytes).json()["id"]
        resp = client.post(
            f"/api/v1/documents/{doc_id}/client-rejection",
            json={"ip": "200.1.2.3", "user_agent": "Mozilla/5.0", "reason": "Los datos de la empresa están mal"},
            headers=auth,
        )
        assert resp.status_code == 200, resp.text
        doc = resp.json()
        assert doc["status"] == "rejected"
        assert doc["rejected_at"] is not None
        assert doc["rejection_reason"] == "Los datos de la empresa están mal"
        assert doc["signers"][0]["status"] == "rejected"
        assert doc["signed_sha256"] is None
        # Ya no se puede firmar.
        assert firmar_cliente(client, auth, doc_id).status_code == 409
        # Aviso document.rejected con el motivo.
        assert len(encolados) == 1
        with SessionLocal() as db:
            entrega = db.get(models.WebhookDelivery, encolados[0])
            assert entrega.event == "document.rejected"
            assert entrega.payload["rejection_reason"] == "Los datos de la empresa están mal"
            assert entrega.payload["external_ref"] == "LF-0152-2026"

    def test_rechazar_documento_firmado_409(self, client, auth, storage, pdf_bytes):
        doc_id = subir(client, auth, pdf_bytes).json()["id"]
        firmar_cliente(client, auth, doc_id)
        resp = client.post(
            f"/api/v1/documents/{doc_id}/client-rejection",
            json={"ip": "200.1.2.3", "user_agent": "UA"},
            headers=auth,
        )
        assert resp.status_code == 409


class TestExpiracion:
    def test_por_defecto_expira_en_30_dias(self, client, auth, storage, pdf_bytes):
        doc = subir(client, auth, pdf_bytes).json()
        creado = datetime.fromisoformat(doc["created_at"])
        expira = datetime.fromisoformat(doc["expires_at"])
        assert timedelta(days=29) < expira - creado <= timedelta(days=30, minutes=1)

    def test_plazo_propio(self, client, auth, storage, pdf_bytes):
        doc = subir(client, auth, pdf_bytes, {**DATOS, "expires_in_days": 2}).json()
        creado = datetime.fromisoformat(doc["created_at"])
        assert datetime.fromisoformat(doc["expires_at"]) - creado <= timedelta(days=2, minutes=1)

    def test_consultar_documento_vencido_lo_expira(self, client, auth, storage, pdf_bytes, encolados):
        doc_id = subir(client, auth, pdf_bytes).json()["id"]
        _vencer(doc_id)
        doc = client.get(f"/api/v1/documents/{doc_id}", headers=auth).json()
        assert doc["status"] == "expired"
        assert doc["expired_at"] is not None
        assert len(encolados) == 1

    def test_firmar_documento_vencido_409(self, client, auth, storage, pdf_bytes):
        doc_id = subir(client, auth, pdf_bytes).json()["id"]
        _vencer(doc_id)
        resp = firmar_cliente(client, auth, doc_id)
        assert resp.status_code == 409
        assert "venció" in resp.text
        assert client.get(f"/api/v1/documents/{doc_id}", headers=auth).json()["status"] == "expired"

    def test_tarea_periodica(self, client, auth, storage, pdf_bytes, encolados):
        from app.services.signing import expire_due_documents

        vencido1 = subir(client, auth, pdf_bytes).json()["id"]
        vencido2 = subir(client, auth, hacer_pdf("otro")).json()["id"]
        vigente = subir(client, auth, hacer_pdf("vigente")).json()["id"]
        _vencer(vencido1)
        _vencer(vencido2)
        with SessionLocal() as db:
            assert expire_due_documents(db) == 2
            assert expire_due_documents(db) == 0  # idempotente
            assert db.get(models.Document, vigente).status == "pending"
        assert len(encolados) == 2

    def test_completado_no_expira(self, client, auth, storage, pdf_bytes):
        doc_id = subir(client, auth, pdf_bytes).json()["id"]
        firmar_cliente(client, auth, doc_id)
        _vencer(doc_id)
        assert client.get(f"/api/v1/documents/{doc_id}", headers=auth).json()["status"] == "completed"
