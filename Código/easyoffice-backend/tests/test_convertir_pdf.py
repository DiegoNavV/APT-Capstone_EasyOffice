"""
Conversión de Word a PDF con LibreOffice. Si LibreOffice no está instalado en el equipo donde corren las pruebas, estas pruebas 
se omiten (en Docker sí está).
"""
import shutil
import threading
import zipfile
from io import BytesIO

import pytest

from app.convertir_pdf import ErrorConversion, docx_a_pdf
from app.rellenar_docx import rellenar_docx

requiere_libreoffice = pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice no instalado")

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def docx_valido(parrafos: list[str]) -> bytes:
    """Word mínimo pero completo (LibreOffice exige las relaciones y los tipos)."""
    cuerpo = "".join(f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>" for t in parrafos)
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>",
        )
        zf.writestr("word/document.xml", f'<w:document xmlns:w="{W}"><w:body>{cuerpo}</w:body></w:document>')
    return buf.getvalue()


@requiere_libreoffice
def test_convierte_un_docx_a_pdf():
    pdf = docx_a_pdf(docx_valido(["Hola mundo"]))
    assert pdf.startswith(b"%PDF") and len(pdf) > 500


@requiere_libreoffice
def test_el_texto_rellenado_llega_al_pdf():
    plantilla = docx_valido(["Contrato {{FOLIO}} de {{RAZON_SOCIAL}}"])
    docx = rellenar_docx(plantilla, {"FOLIO": "LF-01-2026", "RAZON_SOCIAL": "ACME"})
    pdf = docx_a_pdf(docx)
    # El texto del PDF va comprimido; se comprueba con pdftotext si existe, si no solo que sea PDF.
    if shutil.which("pdftotext"):
        import subprocess
        texto = subprocess.run(["pdftotext", "-", "-"], input=pdf, capture_output=True).stdout.decode()
        assert "LF-01-2026" in texto and "ACME" in texto and "{{" not in texto


@requiere_libreoffice
def test_archivo_corrupto_da_error_simple():
    with pytest.raises(ErrorConversion) as exc:
        docx_a_pdf(b"PK esto no es un word")
    assert "no es un documento Word" in str(exc.value)


@requiere_libreoffice
def test_dos_conversiones_a_la_vez():
    resultados = []

    def convertir(n):
        resultados.append(docx_a_pdf(docx_valido([f"Documento {n}"])))

    hilos = [threading.Thread(target=convertir, args=(n,)) for n in range(3)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert len(resultados) == 3 and all(r.startswith(b"%PDF") for r in resultados)


def test_sin_libreoffice_instalado(monkeypatch):
    monkeypatch.setenv("SOFFICE_BIN", "programa-que-no-existe")
    with pytest.raises(ErrorConversion) as exc:
        docx_a_pdf(docx_valido(["x"]))
    assert "no está instalado" in str(exc.value)