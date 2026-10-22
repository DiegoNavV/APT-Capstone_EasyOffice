"""
Conversión de Word a PDF con LibreOffice, y de PDF a imágenes con pdftoppm. Si alguno no está instalado en el equipo donde
corren las pruebas, las pruebas que lo necesitan se omiten (en Docker sí están).
"""
import shutil
import threading
import zipfile
from io import BytesIO

import pytest

from app import convertir_pdf
from app.convertir_pdf import ErrorConversion, ServidorOcupado, docx_a_pdf, pdf_a_imagenes
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


# ---------- cola ----------

def test_si_no_hay_cupo_responde_ocupado_sin_esperar_de_mas(monkeypatch):
    cupo = threading.BoundedSemaphore(1)
    cupo.acquire()                                    # el único lugar ya está ocupado
    monkeypatch.setattr(convertir_pdf, "_CUPO", cupo)
    with pytest.raises(ServidorOcupado) as exc:
        docx_a_pdf(docx_valido(["x"]), espera_maxima=0.05)
    assert "Intenta de nuevo" in str(exc.value)


def test_el_cupo_se_libera_aunque_la_conversion_falle(monkeypatch):
    cupo = threading.BoundedSemaphore(1)
    monkeypatch.setattr(convertir_pdf, "_CUPO", cupo)
    monkeypatch.setenv("SOFFICE_BIN", "programa-que-no-existe")
    with pytest.raises(ErrorConversion):
        docx_a_pdf(docx_valido(["x"]))
    assert cupo.acquire(blocking=False)               # si no se hubiera liberado, aquí fallaría


def test_el_archivo_invalido_no_ocupa_la_cola(monkeypatch):
    cupo = threading.BoundedSemaphore(1)
    cupo.acquire()
    monkeypatch.setattr(convertir_pdf, "_CUPO", cupo)
    with pytest.raises(ErrorConversion) as exc:       # se rechaza antes de esperar turno
        docx_a_pdf(b"no soy un word", espera_maxima=0.05)
    assert not isinstance(exc.value, ServidorOcupado)


# ---------- PDF a imágenes (pdftoppm) ----------

requiere_pdftoppm = pytest.mark.skipif(shutil.which("pdftoppm") is None, reason="pdftoppm no instalado (poppler-utils)")


def pdf_de_paginas(cantidad: int) -> bytes:
    """PDF real de `cantidad` páginas carta (612x792 pt), hecho con Pillow."""
    from PIL import Image

    hojas = [Image.new("RGB", (612, 792), (255, 255, 255 - n)) for n in range(cantidad)]
    buf = BytesIO()
    hojas[0].save(buf, format="PDF", save_all=True, append_images=hojas[1:], resolution=72)
    return buf.getvalue()


@requiere_pdftoppm
def test_cada_pagina_sale_como_jpeg_a_110_dpi():
    from PIL import Image

    paginas = pdf_a_imagenes(pdf_de_paginas(3))
    assert len(paginas) == 3
    for jpeg in paginas:
        assert jpeg[:3] == b"\xff\xd8\xff"
        with Image.open(BytesIO(jpeg)) as img:
            assert img.format == "JPEG"
            assert abs(img.width - 935) <= 2 and abs(img.height - 1210) <= 2


@requiere_pdftoppm
def test_las_paginas_salen_en_orden_aunque_sean_mas_de_nueve():
    from PIL import Image

    paginas = pdf_a_imagenes(pdf_de_paginas(convertir_pdf.MAX_PAGINAS_BORRADOR))
    assert len(paginas) == convertir_pdf.MAX_PAGINAS_BORRADOR
    azules = [Image.open(BytesIO(p)).convert("RGB").getpixel((5, 5))[2] for p in paginas]
    assert azules == sorted(azules, reverse=True)       # cada hoja tiene un poco menos de azul que la anterior


@requiere_pdftoppm
def test_mas_paginas_que_el_maximo_es_error_no_un_borrador_parcial():
    with pytest.raises(ErrorConversion) as exc:
        pdf_a_imagenes(pdf_de_paginas(convertir_pdf.MAX_PAGINAS_BORRADOR + 1))
    assert "demasiadas páginas" in str(exc.value) and "más de 10" in exc.value.detalle


@requiere_pdftoppm
def test_pdf_corrupto_da_error_simple():
    with pytest.raises(ErrorConversion) as exc:
        pdf_a_imagenes(b"%PDF-1.4 esto no es un pdf de verdad")
    assert "No se pudo convertir el PDF" in str(exc.value)


def test_sin_pdftoppm_instalado(monkeypatch):
    monkeypatch.setenv("PDFTOPPM_BIN", "programa-que-no-existe")
    with pytest.raises(ErrorConversion) as exc:
        pdf_a_imagenes(b"%PDF-1.4 x")
    assert "no está instalado" in str(exc.value)


def test_lo_que_no_es_pdf_no_ocupa_la_cola(monkeypatch):
    cupo = threading.BoundedSemaphore(1)
    cupo.acquire()
    monkeypatch.setattr(convertir_pdf, "_CUPO", cupo)
    with pytest.raises(ErrorConversion) as exc:
        pdf_a_imagenes(b"no soy un pdf", espera_maxima=0.05)
    assert not isinstance(exc.value, ServidorOcupado)


def test_pasar_a_imagenes_comparte_la_cola(monkeypatch):
    cupo = threading.BoundedSemaphore(1)
    cupo.acquire()                                    # LibreOffice ocupa el único lugar
    monkeypatch.setattr(convertir_pdf, "_CUPO", cupo)
    with pytest.raises(ServidorOcupado):
        pdf_a_imagenes(b"%PDF-1.4 x", espera_maxima=0.05)


def test_el_cupo_se_libera_aunque_falle_pasar_a_imagenes(monkeypatch):
    cupo = threading.BoundedSemaphore(1)
    monkeypatch.setattr(convertir_pdf, "_CUPO", cupo)
    monkeypatch.setenv("PDFTOPPM_BIN", "programa-que-no-existe")
    with pytest.raises(ErrorConversion):
        pdf_a_imagenes(b"%PDF-1.4 x")
    assert cupo.acquire(blocking=False)