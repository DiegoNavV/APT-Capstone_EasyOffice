"""Lectura y validación de las marcas de una plantilla Word (.docx)."""
import zipfile
from io import BytesIO

import pytest

from app.marcas_documento import (
    CATALOGO_MARCAS, MAX_TAMANO_BYTES, PlantillaInvalida, normalizar_marca, revisar_docx,
)

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="xml" ContentType="application/xml"/></Types>'
)
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def hacer_docx(cuerpo_xml: str, extras: dict | None = None, content_types: str = CONTENT_TYPES) -> bytes:
    """Arma un .docx mínimo con el cuerpo dado (XML de párrafos)."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("word/document.xml", f"<w:document {W}><w:body>{cuerpo_xml}</w:body></w:document>")
        for nombre, datos in (extras or {}).items():
            zf.writestr(nombre, datos)
    return buf.getvalue()


def parrafo_texto(texto: str) -> str:
    return f"<w:p><w:r><w:t>{texto}</w:t></w:r></w:p>"


def parrafo_mergefield(nombre: str) -> str:
    # Así guarda Word un campo de combinar correspondencia (campo complejo).
    return (
        '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        f'<w:r><w:instrText xml:space="preserve"> MERGEFIELD {nombre} \\* MERGEFORMAT </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        f"<w:r><w:t>«{nombre}»</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
    )


def test_normalizar_marca():
    assert normalizar_marca("Razón Social ") == "RAZON_SOCIAL"
    assert normalizar_marca("PRECIO_Ss_1") == "PRECIO_SS_1"
    assert normalizar_marca("región-rep legal") == "REGION_REP_LEGAL"


def test_lee_mergefield_y_llaves():
    docx = hacer_docx(parrafo_mergefield("RAZON_SOCIAL") + parrafo_texto("Folio {{ folio }} y {{Razón Social}}"))
    assert revisar_docx(docx) == ["FOLIO", "RAZON_SOCIAL"]


def test_llaves_partidas_en_varios_pedazos():
    # Word suele partir el texto escrito en varios "runs".
    parrafo = "<w:p><w:r><w:t>{{RU</w:t></w:r><w:r><w:t>T}}</w:t></w:r></w:p>"
    assert revisar_docx(hacer_docx(parrafo)) == ["RUT"]


def test_mergefield_partido_en_varios_pedazos():
    parrafo = (
        '<w:p><w:r><w:instrText> MERGE</w:instrText></w:r>'
        '<w:r><w:instrText>FIELD  RUT </w:instrText></w:r></w:p>'
    )
    assert revisar_docx(hacer_docx(parrafo)) == ["RUT"]


def test_fldsimple():
    parrafo = '<w:p><w:fldSimple w:instr=" MERGEFIELD MAIL "><w:r><w:t>x</w:t></w:r></w:fldSimple></w:p>'
    assert revisar_docx(hacer_docx(parrafo)) == ["MAIL"]


def test_mergefield_con_comillas():
    docx = hacer_docx(parrafo_mergefield('"Razón Social"'))
    assert revisar_docx(docx) == ["RAZON_SOCIAL"]


def test_lee_encabezados_y_pies():
    docx = hacer_docx(
        parrafo_texto("{{FOLIO}}"),
        extras={"word/footer1.xml": f"<w:ftr {W}>{parrafo_texto('{{RUT}}')}</w:ftr>"},
    )
    assert revisar_docx(docx) == ["FOLIO", "RUT"]


def test_marca_desconocida_se_rechaza_y_se_nombra():
    docx = hacer_docx(parrafo_texto("{{FOLIO}} {{NO_EXISTE}} {{OTRA_COSA}}"))
    with pytest.raises(PlantillaInvalida) as e:
        revisar_docx(docx)
    assert "NO_EXISTE" in str(e.value) and "OTRA_COSA" in str(e.value)


def test_sin_marcas_se_rechaza():
    with pytest.raises(PlantillaInvalida, match="ninguna marca"):
        revisar_docx(hacer_docx(parrafo_texto("Texto sin marcas")))


def test_no_es_zip():
    with pytest.raises(PlantillaInvalida, match="Word"):
        revisar_docx(b"esto no es un docx")


def test_zip_falso_que_empieza_con_pk():
    with pytest.raises(PlantillaInvalida, match="Word"):
        revisar_docx(b"PK\x03\x04basura")


def test_zip_sin_document_xml():
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        zf.writestr("otro.txt", "hola")
    with pytest.raises(PlantillaInvalida, match="Word"):
        revisar_docx(buf.getvalue())


def test_macros_se_rechazan():
    docx = hacer_docx(parrafo_texto("{{FOLIO}}"), extras={"word/vbaProject.bin": b"x"})
    with pytest.raises(PlantillaInvalida, match="macros"):
        revisar_docx(docx)


def test_tipo_con_macros_se_rechaza():
    ct = CONTENT_TYPES.replace("application/xml", "application/vnd.ms-word.document.macroEnabled.main+xml")
    with pytest.raises(PlantillaInvalida, match="macros"):
        revisar_docx(hacer_docx(parrafo_texto("{{FOLIO}}"), content_types=ct))


def test_archivo_demasiado_grande():
    with pytest.raises(PlantillaInvalida, match="pesa demasiado"):
        revisar_docx(b"PK" + b"0" * MAX_TAMANO_BYTES)


def test_demasiado_contenido_descomprimido():
    # Un zip pequeño que al abrirse ocupa muchísimo ("zip bomb").
    docx = hacer_docx(parrafo_texto("{{FOLIO}}"), extras={"word/relleno.bin": b"0" * (101 * 1024 * 1024)})
    assert len(docx) < MAX_TAMANO_BYTES
    with pytest.raises(PlantillaInvalida, match="inusual"):
        revisar_docx(docx)


def test_catalogo_incluye_las_marcas_del_contrato_real():
    for n in (1, 2, 3):
        for base in ("SERVICIO", "DESCRIPCION_SS", "PRECIO_SS", "CICLO_PAGO_SS"):
            assert f"{base}_{n}" in CATALOGO_MARCAS
    for m in ("FOLIO", "RAZON_SOCIAL", "BANCOLINK", "VENCIMIENTO", "ROL_PROPIEDAD"):
        assert m in CATALOGO_MARCAS