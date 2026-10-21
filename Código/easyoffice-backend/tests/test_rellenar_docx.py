"""Reemplazo de las marcas de una plantilla Word por los datos del trámite."""
import zipfile
from io import BytesIO

import pytest
from lxml import etree

from app.marcas_documento import PlantillaInvalida, revisar_docx
from app.rellenar_docx import FaltanDatos, rellenar_docx
from tests.test_marcas_documento import hacer_docx, parrafo_mergefield, parrafo_texto

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def parte(docx: bytes, nombre: str = "word/document.xml") -> etree._Element:
    with zipfile.ZipFile(BytesIO(docx)) as zf:
        return etree.fromstring(zf.read(nombre))


def textos_de(docx: bytes, nombre: str = "word/document.xml") -> list[str]:
    """Texto de cada párrafo, en orden."""
    raiz = parte(docx, nombre)
    return ["".join(p.xpath(".//w:t/text()", namespaces=NS)) for p in raiz.iter("{%s}p" % NS["w"])]


def test_mergefield_complejo_se_reemplaza_y_conserva_formato():
    p = (
        '<w:p><w:r><w:t xml:space="preserve">Empresa: </w:t></w:r>'
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText xml:space="preserve"> MERGEFIELD RAZON_SOCIAL </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        '<w:r><w:rPr><w:b/></w:rPr><w:t>«RAZON_SOCIAL»</w:t></w:r>'
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        '<w:r><w:t>.</w:t></w:r></w:p>'
    )
    salida = rellenar_docx(hacer_docx(p), {"RAZON_SOCIAL": "ACME SpA"})
    assert textos_de(salida) == ["Empresa: ACME SpA."]
    raiz = parte(salida)
    assert not raiz.xpath("//w:fldChar | //w:instrText", namespaces=NS)
    # El texto reemplazado heredó la negrita del resultado del campo.
    assert raiz.xpath("//w:r[w:rPr/w:b]/w:t/text()", namespaces=NS) == ["ACME SpA"]


def test_mergefield_con_instruccion_partida():
    p = (
        '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText> MERGE</w:instrText></w:r><w:r><w:instrText>FIELD  RUT </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>«RUT»</w:t></w:r>'
        '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
    )
    assert textos_de(rellenar_docx(hacer_docx(p), {"RUT": "76123456-0"})) == ["76123456-0"]


def test_fldsimple():
    p = '<w:p><w:fldSimple w:instr=" MERGEFIELD MAIL "><w:r><w:t>«MAIL»</w:t></w:r></w:fldSimple></w:p>'
    salida = rellenar_docx(hacer_docx(p), {"MAIL": "a@b.cl"})
    assert textos_de(salida) == ["a@b.cl"]
    assert not parte(salida).xpath("//w:fldSimple", namespaces=NS)


def test_llaves_partidas_en_varios_pedazos_con_texto_alrededor():
    p = (
        "<w:p><w:r><w:t>Hola {{RA</w:t></w:r><w:r><w:t>ZON_SO</w:t></w:r>"
        "<w:r><w:t>CIAL}} bienvenido</w:t></w:r></w:p>"
    )
    assert textos_de(rellenar_docx(hacer_docx(p), {"RAZON_SOCIAL": "ACME"})) == ["Hola ACME bienvenido"]


def test_varias_marcas_en_el_mismo_parrafo_y_mismo_pedazo():
    p = parrafo_texto("{{FOLIO}} - {{RUT}} - {{FOLIO}}")
    salida = rellenar_docx(hacer_docx(p), {"FOLIO": "LF-01-2026", "RUT": "1-9"})
    assert textos_de(salida) == ["LF-01-2026 - 1-9 - LF-01-2026"]


def test_mezcla_de_formas_en_un_documento():
    cuerpo = parrafo_mergefield("FOLIO") + parrafo_texto("RUT {{rut}}")
    salida = rellenar_docx(hacer_docx(cuerpo), {"FOLIO": "LF-01-2026", "RUT": "1-9"})
    assert textos_de(salida) == ["LF-01-2026", "RUT 1-9"]


def test_salto_de_linea_pasa_a_w_br():
    salida = rellenar_docx(hacer_docx(parrafo_texto("{{DESCRIPCION_SS_1}}")), {"DESCRIPCION_SS_1": "uno\ndos\r\ntres"})
    raiz = parte(salida)
    assert len(raiz.xpath("//w:br", namespaces=NS)) == 2
    assert textos_de(salida) == ["unodostres"]


def test_valor_vacio_es_valido_pero_faltante_no():
    cuerpo = parrafo_texto("[{{SERVICIO_3}}]") + parrafo_texto("{{RUT}} {{MAIL}}")
    assert textos_de(rellenar_docx(hacer_docx(cuerpo), {"SERVICIO_3": "", "RUT": "1", "MAIL": "x"}))[0] == "[]"
    with pytest.raises(FaltanDatos) as exc:
        rellenar_docx(hacer_docx(cuerpo), {"SERVICIO_3": "", "RUT": None})
    assert exc.value.marcas == ["MAIL", "RUT"]


def test_valor_con_llaves_no_se_vuelve_a_interpretar():
    cuerpo = parrafo_texto("{{RAZON_SOCIAL}} / {{RUT}}")
    salida = rellenar_docx(hacer_docx(cuerpo), {"RAZON_SOCIAL": "{{RUT}} <b>&</b>", "RUT": "1-9"})
    assert textos_de(salida) == ["{{RUT}} <b>&</b> / 1-9"]


def test_campo_que_no_es_mergefield_no_se_toca():
    p = (
        '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText> PAGE </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r>'
        '<w:r><w:fldChar w:fldCharType="end"/></w:r><w:r><w:t> {{RUT}}</w:t></w:r></w:p>'
    )
    salida = rellenar_docx(hacer_docx(p), {"RUT": "1-9"})
    assert parte(salida).xpath("//w:instrText/text()", namespaces=NS) == [" PAGE "]
    assert textos_de(salida) == ["1 1-9"]


def test_encabezado_y_pie():
    extras = {
        "word/header1.xml": f'<w:hdr xmlns:w="{NS["w"]}">{parrafo_texto("Folio {{FOLIO}}")}</w:hdr>',
        "word/footer1.xml": f'<w:ftr xmlns:w="{NS["w"]}">{parrafo_mergefield("RUT")}</w:ftr>',
    }
    docx = hacer_docx(parrafo_texto("{{MAIL}}"), extras)
    salida = rellenar_docx(docx, {"FOLIO": "LF-01-2026", "RUT": "1-9", "MAIL": "a@b.cl"})
    assert textos_de(salida, "word/header1.xml") == ["Folio LF-01-2026"]
    assert textos_de(salida, "word/footer1.xml") == ["1-9"]


def test_resultado_ya_no_tiene_marcas_y_otros_archivos_quedan_iguales():
    docx = hacer_docx(parrafo_mergefield("RUT"), {"word/media/logo.png": b"\x89PNGdatos"})
    salida = rellenar_docx(docx, {"RUT": "1-9"})
    with pytest.raises(PlantillaInvalida):      # revisar_docx exige >= 1 marca: ya no hay ninguna
        revisar_docx(salida)
    with zipfile.ZipFile(BytesIO(salida)) as zf:
        assert zf.read("word/media/logo.png") == b"\x89PNGdatos"
        assert zf.testzip() is None


def test_claves_del_diccionario_se_normalizan():
    assert textos_de(rellenar_docx(hacer_docx(parrafo_texto("{{Razón Social}}")), {"razon social": "ACME"})) == ["ACME"]


def test_archivo_que_no_es_docx():
    with pytest.raises(PlantillaInvalida):
        rellenar_docx(b"PK no es zip", {})


# ---------- filas de tabla vacías ----------

def celda(*parrafos: str) -> str:
    return "<w:tc>" + "".join(parrafos) + "</w:tc>"


def fila(*celdas: str) -> str:
    return "<w:tr>" + "".join(celdas) + "</w:tr>"


def tabla(*filas: str) -> str:
    return "<w:tbl>" + "".join(filas) + "</w:tbl><w:p/>"


def filas_de(docx: bytes) -> list[str]:
    raiz = parte(docx)
    return ["|".join("".join(c.xpath(".//w:t/text()", namespaces=NS)) for c in tr.findall("w:tc", NS))
            for tr in raiz.iter("{%s}tr" % NS["w"])]


def test_fila_con_todas_las_marcas_vacias_se_elimina():
    cuerpo = tabla(
        fila(celda(parrafo_texto("SERVICIO")), celda(parrafo_texto("PRECIO"))),            # encabezado, sin marcas
        fila(celda(parrafo_texto("{{SERVICIO_1}}")), celda(parrafo_texto("$ {{PRECIO_SS_1}}"))),
        fila(celda(parrafo_texto("{{SERVICIO_2}}")), celda(parrafo_texto("$ {{PRECIO_SS_2}}"))),
    )
    valores = {"SERVICIO_1": "BODEGA", "PRECIO_SS_1": "100", "SERVICIO_2": "", "PRECIO_SS_2": ""}
    assert filas_de(rellenar_docx(hacer_docx(cuerpo), valores)) == ["SERVICIO|PRECIO", "BODEGA|$ 100"]


def test_fila_con_algun_dato_se_conserva():
    cuerpo = tabla(
        fila(celda(parrafo_texto("{{SERVICIO_1}}")), celda(parrafo_texto("{{DESCRIPCION_SS_1}}"))),
        fila(celda(parrafo_texto("{{SERVICIO_2}}")), celda(parrafo_texto("{{DESCRIPCION_SS_2}}"))),
    )
    valores = {"SERVICIO_1": "A", "DESCRIPCION_SS_1": "", "SERVICIO_2": "B", "DESCRIPCION_SS_2": "detalle"}
    assert filas_de(rellenar_docx(hacer_docx(cuerpo), valores)) == ["A|", "B|detalle"]


def test_fila_vacia_con_mergefield_y_varios_parrafos_por_celda():
    cuerpo = tabla(
        fila(celda(parrafo_texto("{{SERVICIO_1}}")), celda(parrafo_mergefield("PRECIO_SS_1"), parrafo_texto("fin"))),
        fila(celda(parrafo_mergefield("SERVICIO_3")), celda(parrafo_mergefield("PRECIO_SS_3"), parrafo_texto("fin"))),
    )
    valores = {"SERVICIO_1": "A", "PRECIO_SS_1": "5", "SERVICIO_3": "", "PRECIO_SS_3": ""}
    assert filas_de(rellenar_docx(hacer_docx(cuerpo), valores)) == ["A|5fin"]


def test_nunca_se_borran_todas_las_filas_de_una_tabla():
    cuerpo = tabla(fila(celda(parrafo_texto("{{SERVICIO_2}}"))), fila(celda(parrafo_texto("{{SERVICIO_3}}"))))
    assert filas_de(rellenar_docx(hacer_docx(cuerpo), {"SERVICIO_2": "", "SERVICIO_3": ""})) == ["", ""]


def test_parrafo_vacio_fuera_de_tabla_no_se_elimina():
    cuerpo = parrafo_texto("[{{SERVICIO_3}}]")
    assert textos_de(rellenar_docx(hacer_docx(cuerpo), {"SERVICIO_3": ""})) == ["[]"]