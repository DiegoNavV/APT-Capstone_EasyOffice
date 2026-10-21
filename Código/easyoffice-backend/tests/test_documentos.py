"""Generar y descargar el PDF de un trámite."""
import shutil

import pytest

from app import models
from tests.test_plantillas import carpeta_plantillas, docx_con, headers_admin, subir  # noqa: F401  (fixtures)
from tests.test_valores_documento import BANCO_EO, tramite  # noqa: F401  (fixture)

PDF_FALSO = b"%PDF-1.4 documento de prueba"


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    """Carpeta de PDFs temporal, sin variables de banco y sin LibreOffice real
    (se reemplaza por un PDF falso para que las pruebas sean rápidas)."""
    monkeypatch.setenv("DOCUMENTOS_DIR", str(tmp_path / "documentos"))
    for nombre in ("MARCA_POR_DEFECTO", "BANCO_TEXTO_EASY_OFFICE", "BANCO_TEXTO_INOFFICE"):
        monkeypatch.delenv(nombre, raising=False)
    monkeypatch.setattr("app.documentos.docx_a_pdf", lambda docx: PDF_FALSO)
    return tmp_path / "documentos"


@pytest.fixture()
def con_plantilla(subir, tramite):  # noqa: F811
    r = subir(docx_con("Contrato {{FOLIO}} de {{RAZON_SOCIAL}}. Pago: {{BANCOLINK}}"), id_servicio=tramite.id_servicio)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def con_banco(monkeypatch):
    monkeypatch.setenv("BANCO_TEXTO_EASY_OFFICE", BANCO_EO)


def generar(client, headers, id_tramite):
    return client.post(f"/api/tramites/{id_tramite}/documento", headers=headers)


def test_exige_sesion(client, tramite):
    assert client.post(f"/api/tramites/{tramite.id_tramite}/documento").status_code == 401
    assert client.get(f"/api/tramites/{tramite.id_tramite}/documento").status_code == 401


def test_tramite_inexistente(client, headers_agente):
    assert generar(client, headers_agente, 9999).status_code == 404
    assert client.get("/api/tramites/9999/documento", headers=headers_agente).status_code == 404


def test_sin_plantilla_activa(client, headers_agente, tramite):
    r = generar(client, headers_agente, tramite.id_tramite)
    assert r.status_code == 409
    assert "no tiene una plantilla activa" in r.json()["detail"]


def test_genera_guarda_y_permite_descargar(client, headers_agente, tramite, con_plantilla, con_banco, entorno, db_session):
    r = generar(client, headers_agente, tramite.id_tramite)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["folio"] == "LF-01-2026" and cuerpo["nombre_archivo"] == "LF-01-2026.pdf"
    assert cuerpo["tamano_bytes"] == len(PDF_FALSO) and cuerpo["version_plantilla"] == "1"
    assert len(cuerpo["hash_sha256"]) == 64
    assert (entorno / f"tramite_{tramite.id_tramite}.pdf").read_bytes() == PDF_FALSO

    db_session.expire_all()
    guardado = db_session.get(models.Tramite, tramite.id_tramite)
    assert guardado.ruta_documento_generado == f"tramite_{tramite.id_tramite}.pdf"
    assert guardado.estado_actual == "generado"          # generar no cambia el estado

    d = client.get(f"/api/tramites/{tramite.id_tramite}/documento", headers=headers_agente)
    assert d.status_code == 200 and d.content == PDF_FALSO
    assert d.headers["content-type"] == "application/pdf"
    assert "LF-01-2026.pdf" in d.headers["content-disposition"]


def test_faltan_datos_informa_cuales(client, headers_agente, tramite, con_plantilla, entorno):
    r = generar(client, headers_agente, tramite.id_tramite)       # banco sin configurar
    assert r.status_code == 422
    detalle = r.json()["detail"]
    assert detalle["faltantes"] == ["BANCOLINK"]
    assert "Datos bancarios" in detalle["mensaje"]
    assert not entorno.exists() or not list(entorno.glob("*.pdf"))


def test_regenerar_reemplaza_el_pdf(client, headers_agente, tramite, con_plantilla, con_banco, entorno, monkeypatch):
    generar(client, headers_agente, tramite.id_tramite)
    monkeypatch.setattr("app.documentos.docx_a_pdf", lambda docx: b"%PDF-nuevo")
    r = generar(client, headers_agente, tramite.id_tramite)
    assert r.status_code == 200
    assert list(entorno.glob("*.pdf")) == [entorno / f"tramite_{tramite.id_tramite}.pdf"]
    assert client.get(f"/api/tramites/{tramite.id_tramite}/documento", headers=headers_agente).content == b"%PDF-nuevo"


def test_usa_la_plantilla_activa(client, headers_agente, tramite, con_plantilla, con_banco, subir):
    subir(docx_con("Version 2 {{FOLIO}} {{BANCOLINK}}"), id_servicio=tramite.id_servicio)
    assert generar(client, headers_agente, tramite.id_tramite).json()["version_plantilla"] == "2"


@pytest.mark.parametrize("estado", ["firmado", "entregado"])
def test_tramite_firmado_no_se_regenera(client, headers_agente, tramite, con_plantilla, con_banco, db_session, estado):
    tramite.estado_actual = estado
    db_session.commit()
    r = generar(client, headers_agente, tramite.id_tramite)
    assert r.status_code == 409 and "ya está firmado" in r.json()["detail"]


def test_descargar_sin_documento_generado(client, headers_agente, tramite):
    r = client.get(f"/api/tramites/{tramite.id_tramite}/documento", headers=headers_agente)
    assert r.status_code == 404


def test_archivo_de_plantilla_borrado_del_volumen(client, headers_agente, tramite, con_plantilla, con_banco, carpeta_plantillas):
    for f in carpeta_plantillas.rglob("*.docx"):
        f.unlink()
    r = generar(client, headers_agente, tramite.id_tramite)
    assert r.status_code == 409 and "no está disponible" in r.json()["detail"]


def test_falla_la_conversion(client, headers_agente, tramite, con_plantilla, con_banco, monkeypatch):
    from app.convertir_pdf import ErrorConversion

    def fallar(docx):
        raise ErrorConversion("No se pudo convertir el documento a PDF.", detalle="secreto interno")

    monkeypatch.setattr("app.documentos.docx_a_pdf", fallar)
    r = generar(client, headers_agente, tramite.id_tramite)
    assert r.status_code == 502
    assert "secreto interno" not in r.text           # el detalle técnico no sale al cliente


def test_ruta_manipulada_no_se_descarga(client, headers_agente, tramite, db_session, entorno):
    tramite.ruta_documento_generado = "../../etc/passwd"
    db_session.commit()
    assert client.get(f"/api/tramites/{tramite.id_tramite}/documento", headers=headers_agente).status_code == 404


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice no instalado")
def test_con_libreoffice_real(client, headers_agente, tramite, subir, con_banco, monkeypatch):
    from app.convertir_pdf import docx_a_pdf
    from tests.test_convertir_pdf import docx_valido
    monkeypatch.setattr("app.documentos.docx_a_pdf", docx_a_pdf)
    plantilla = docx_valido(["Contrato {{FOLIO}} de {{RAZON_SOCIAL}}. Pago: {{BANCOLINK}}"])
    assert subir(plantilla, id_servicio=tramite.id_servicio).status_code == 201
    r = generar(client, headers_agente, tramite.id_tramite)
    assert r.status_code == 200, r.text
    d = client.get(f"/api/tramites/{tramite.id_tramite}/documento", headers=headers_agente)
    assert d.content.startswith(b"%PDF") and len(d.content) > 1000