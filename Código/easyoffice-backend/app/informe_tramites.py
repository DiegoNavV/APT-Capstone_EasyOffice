"""
Informe corporativo en PDF de los trámites: los mismos conteos agregados de la vista
"Reportes" del panel (ver app/crud.py::reporte_tramites), pero con gráficos de barra y
membrete de Easy Office en vez de la tabla cruda del CSV (ver app/routers/tramites.py:
GET /api/tramites/reporte/informe).

Se arma como .docx con python-docx (los gráficos son imágenes PNG dibujadas con Pillow,
ya una dependencia del proyecto) y se convierte a PDF con el mismo conversor que usan los
contratos (app/convertir_pdf.docx_a_pdf), para no mantener dos caminos de generación de PDF
distintos. Nunca incluye datos personales: son solo los conteos agregados, igual que la
pantalla.
"""
from datetime import datetime
from io import BytesIO

from docx import Document
from docx.shared import Cm, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont

from app import schemas
from app.convertir_pdf import ErrorConversion, ServidorOcupado, docx_a_pdf

# Mismos colores que el panel (easyoffice-frontend/tailwind.config.js): brand.primary,
# subtle (riel de las barras), ink.primary y ink.muted aproximados.
_RGB_MARCA = (0x0E, 0xAD, 0x84)
_RGB_RIEL = (0xEE, 0xF1, 0xF4)
_RGB_TEXTO = (31, 41, 55)
_RGB_FECHA = (107, 114, 128)

_RUTAS_FUENTE_NORMAL = ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",)
_RUTAS_FUENTE_NEGRITA = ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",)


class InformeNoGenerable(Exception):
    """No se pudo generar el informe. `codigo_http` indica cómo responder."""

    def __init__(self, mensaje: str, codigo_http: int = 502):
        super().__init__(mensaje)
        self.codigo_http = codigo_http


def _fuente(tamano: int, negrita: bool = False) -> ImageFont.FreeTypeFont:
    for ruta in (_RUTAS_FUENTE_NEGRITA if negrita else _RUTAS_FUENTE_NORMAL):
        try:
            return ImageFont.truetype(ruta, tamano)
        except OSError:
            continue
    return ImageFont.load_default()


def _grafico_barras(filas: list[schemas.ReporteConteoOut], total: int) -> bytes:
    """Gráfico de barras horizontales, mismo estilo que <Barra>/<FilaConteo> del panel
    (easyoffice-frontend/src/pages/Reportes.jsx). Devuelve un PNG."""
    ancho, alto_fila, margen = 1200, 70, 40
    alto = margen * 2 + alto_fila * len(filas)
    imagen = Image.new("RGB", (ancho, alto), "white")
    dibujo = ImageDraw.Draw(imagen)
    fuente_etiqueta = _fuente(26)
    fuente_cantidad = _fuente(26, negrita=True)

    ancho_etiqueta, ancho_cantidad, alto_barra = 340, 80, 14
    x_ini = margen + ancho_etiqueta
    x_fin = ancho - margen - ancho_cantidad
    ancho_disponible = x_fin - x_ini

    for i, fila in enumerate(filas):
        y = margen + i * alto_fila + alto_fila // 2
        etiqueta = fila.etiqueta if len(fila.etiqueta) <= 40 else fila.etiqueta[:39] + "…"
        dibujo.text((margen, y), etiqueta, font=fuente_etiqueta, fill=_RGB_TEXTO, anchor="lm")

        dibujo.rounded_rectangle(
            [x_ini, y - alto_barra // 2, x_fin, y + alto_barra // 2], radius=alto_barra // 2, fill=_RGB_RIEL
        )
        porcentaje = (fila.cantidad / total) if total else 0
        ancho_lleno = int(ancho_disponible * porcentaje)
        if ancho_lleno > 0:
            dibujo.rounded_rectangle(
                [x_ini, y - alto_barra // 2, x_ini + max(ancho_lleno, alto_barra), y + alto_barra // 2],
                radius=alto_barra // 2, fill=_RGB_MARCA,
            )
        dibujo.text((x_fin + 12, y), str(fila.cantidad), font=fuente_cantidad, fill=_RGB_TEXTO, anchor="lm")

    buffer = BytesIO()
    imagen.save(buffer, format="PNG")
    return buffer.getvalue()


def _agregar_seccion(documento: Document, titulo: str, filas: list[schemas.ReporteConteoOut], total: int, sin_datos: str):
    documento.add_heading(titulo, level=2)
    if not filas:
        documento.add_paragraph(sin_datos)
        return
    documento.add_picture(BytesIO(_grafico_barras(filas, total)), width=Cm(16))


def construir_informe_docx(reporte: schemas.ReporteTramitesOut) -> bytes:
    documento = Document()

    titulo = documento.add_heading("Easy Office", level=0)
    titulo.runs[0].font.color.rgb = RGBColor(*_RGB_MARCA)

    subtitulo = documento.add_paragraph()
    run_subtitulo = subtitulo.add_run("Informe de trámites")
    run_subtitulo.font.size = Pt(18)
    run_subtitulo.font.bold = True

    fecha = documento.add_paragraph()
    run_fecha = fecha.add_run(f"Generado el {datetime.now():%d-%m-%Y %H:%M}")
    run_fecha.font.size = Pt(10)
    run_fecha.font.color.rgb = RGBColor(*_RGB_FECHA)

    total_parrafo = documento.add_paragraph()
    total_parrafo.add_run("Total de trámites: ")
    run_total = total_parrafo.add_run(str(reporte.total))
    run_total.font.bold = True
    run_total.font.size = Pt(16)

    _agregar_seccion(documento, "Por estado", reporte.por_estado, reporte.total, "Sin datos.")
    _agregar_seccion(documento, "Por servicio", reporte.por_servicio, reporte.total, "Sin datos.")
    _agregar_seccion(
        documento, "Por agente", reporte.por_agente, reporte.total,
        "Ningún trámite tiene un agente responsable asignado.",
    )

    buffer = BytesIO()
    documento.save(buffer)
    return buffer.getvalue()


def construir_informe_pdf(reporte: schemas.ReporteTramitesOut) -> bytes:
    """Arma el informe y lo convierte a PDF. Lanza InformeNoGenerable si la conversión falla
    o el servidor está ocupado (mismo conversor y misma cola que los contratos)."""
    try:
        return docx_a_pdf(construir_informe_docx(reporte))
    except ServidorOcupado as exc:
        raise InformeNoGenerable(str(exc), codigo_http=503) from None
    except ErrorConversion as exc:
        raise InformeNoGenerable(str(exc), codigo_http=502) from None
