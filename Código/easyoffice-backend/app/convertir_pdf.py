"""
Convierte un documento Word (.docx) a PDF usando LibreOffice, y un PDF a imágenes
JPEG (una por página) usando pdftoppm (paquete poppler-utils). Ambos vienen
instalados en la imagen de Docker del backend (ver Dockerfile).

Cada conversión usa su propia carpeta temporal y su propio perfil de LibreOffice:
así dos conversiones al mismo tiempo no se pisan y no queda nada en disco al
terminar. LibreOffice y pdftoppm se ejecutan SIN shell, con argumentos fijos y un
tiempo máximo; el nombre del archivo lo fijamos nosotros, nunca viene del usuario.

Cola: solo se convierten CONVERSIONES_SIMULTANEAS documentos a la vez (LibreOffice
consume bastante memoria); pdftoppm comparte la misma cola. Los demás esperan su turno; si la espera se pasa del
máximo, se responde "ocupado" en vez de dejar la petición colgada.
"""
import os
import subprocess
import tempfile
import threading
import zipfile
from io import BytesIO
from pathlib import Path

TIEMPO_MAXIMO_SEGUNDOS = 120
# Cuánto espera su turno una conversión antes de rendirse (el panel usa este valor;
# la vista previa pública pide uno más corto).
ESPERA_MAXIMA_SEGUNDOS = 60
MAX_PDF_BYTES = 50 * 1024 * 1024
# Cuántas conversiones a la vez como máximo (LibreOffice consume bastante memoria).
_CUPO = threading.BoundedSemaphore(int(os.getenv("CONVERSIONES_SIMULTANEAS", "2")))

# PDF a imágenes (vista previa del borrador para el cliente).
TIEMPO_MAXIMO_IMAGENES_SEGUNDOS = 60
DPI_BORRADOR = 110
CALIDAD_JPEG = 80
# Un borrador con más páginas es un error: nunca se muestra a medias.
MAX_PAGINAS_BORRADOR = 10


class ErrorConversion(Exception):
    """No se pudo convertir el documento. El mensaje es simple y seguro de mostrar;
    el detalle técnico queda en `detalle` para los registros del servidor."""

    def __init__(self, mensaje: str, detalle: str = ""):
        super().__init__(mensaje)
        self.detalle = detalle


class ServidorOcupado(ErrorConversion):
    """Hay demasiadas conversiones en cola. Conviene reintentar en unos segundos."""


def _es_docx(contenido: bytes) -> bool:
    """LibreOffice convierte casi cualquier cosa (hasta texto suelto), así que
    antes se comprueba que de verdad sea un Word."""
    try:
        with zipfile.ZipFile(BytesIO(contenido)) as zf:
            return "word/document.xml" in zf.namelist()
    except zipfile.BadZipFile:
        return False


def docx_a_pdf(contenido: bytes, espera_maxima: float | None = None) -> bytes:
    """Convierte un .docx a PDF. `espera_maxima`: segundos que puede esperar su
    turno en la cola (por defecto ESPERA_MAXIMA_SEGUNDOS); si se pasa, lanza
    ServidorOcupado."""
    if not _es_docx(contenido):
        raise ErrorConversion("El archivo no es un documento Word (.docx) válido.")
    espera = ESPERA_MAXIMA_SEGUNDOS if espera_maxima is None else espera_maxima
    if not _CUPO.acquire(timeout=espera):
        raise ServidorOcupado("Hay muchas solicitudes en este momento. Intenta de nuevo en unos segundos.")
    try:
        return _convertir(contenido)
    finally:
        _CUPO.release()


def _convertir(contenido: bytes) -> bytes:
    programa = os.getenv("SOFFICE_BIN", "soffice")
    with tempfile.TemporaryDirectory(prefix="conv_") as carpeta:
        base = Path(carpeta)
        origen = base / "documento.docx"
        origen.write_bytes(contenido)
        perfil = (base / "perfil").as_uri()
        comando = [
            programa, "--headless", "--norestore", "--nolockcheck", "--nodefault",
            f"-env:UserInstallation={perfil}",
            "--convert-to", "pdf", "--outdir", str(base), str(origen),
        ]
        try:
            resultado = subprocess.run(
                comando, capture_output=True, timeout=TIEMPO_MAXIMO_SEGUNDOS, cwd=carpeta,
                env={**os.environ, "HOME": carpeta},
            )
        except FileNotFoundError:
            raise ErrorConversion("El conversor a PDF no está instalado en el servidor.", detalle=programa) from None
        except subprocess.TimeoutExpired:
            raise ErrorConversion("La conversión a PDF tardó demasiado. Intenta nuevamente.") from None

        destino = base / "documento.pdf"
        if resultado.returncode != 0 or not destino.exists():
            salida = (resultado.stderr or resultado.stdout or b"").decode("utf-8", "ignore")[-500:]
            raise ErrorConversion("No se pudo convertir el documento a PDF.", detalle=salida)
        if destino.stat().st_size > MAX_PDF_BYTES:
            raise ErrorConversion("El PDF resultante es demasiado grande.")
        pdf = destino.read_bytes()
    if not pdf.startswith(b"%PDF"):
        raise ErrorConversion("La conversión no produjo un PDF válido.")
    return pdf


def pdf_a_imagenes(pdf: bytes, espera_maxima: float | None = None) -> list[bytes]:
    """Convierte cada página de un PDF a JPEG (DPI_BORRADOR, calidad CALIDAD_JPEG) y
    las devuelve en orden. Si el PDF tiene más de MAX_PAGINAS_BORRADOR páginas lanza
    ErrorConversion. Usa la misma cola que docx_a_pdf (puede lanzar ServidorOcupado)."""
    if not pdf.startswith(b"%PDF"):
        raise ErrorConversion("El archivo no es un PDF válido.")
    espera = ESPERA_MAXIMA_SEGUNDOS if espera_maxima is None else espera_maxima
    if not _CUPO.acquire(timeout=espera):
        raise ServidorOcupado("Hay muchas solicitudes en este momento. Intenta de nuevo en unos segundos.")
    try:
        return _rasterizar(pdf)
    finally:
        _CUPO.release()


def _numero_de_pagina(ruta: Path) -> int:
    # pdftoppm nombra "pagina-1.jpg" o "pagina-01.jpg" según cuántas páginas haya.
    return int(ruta.stem.rsplit("-", 1)[1])


def _rasterizar(pdf: bytes) -> list[bytes]:
    programa = os.getenv("PDFTOPPM_BIN", "pdftoppm")
    with tempfile.TemporaryDirectory(prefix="img_") as carpeta:
        base = Path(carpeta)
        origen = base / "documento.pdf"
        origen.write_bytes(pdf)
        # Se pide una página más que el máximo: si aparece, el documento es demasiado
        # largo (así no hace falta otro programa para contar las páginas).
        comando = [
            programa, "-r", str(DPI_BORRADOR), "-jpeg", "-jpegopt", f"quality={CALIDAD_JPEG}",
            "-l", str(MAX_PAGINAS_BORRADOR + 1), str(origen), str(base / "pagina"),
        ]
        try:
            resultado = subprocess.run(
                comando, capture_output=True, timeout=TIEMPO_MAXIMO_IMAGENES_SEGUNDOS, cwd=carpeta,
                env={**os.environ, "HOME": carpeta},
            )
        except FileNotFoundError:
            raise ErrorConversion("El conversor a imágenes no está instalado en el servidor.", detalle=programa) from None
        except subprocess.TimeoutExpired:
            raise ErrorConversion("La conversión a imágenes tardó demasiado. Intenta nuevamente.") from None

        paginas = sorted(base.glob("pagina-*.jpg"), key=_numero_de_pagina)
        if resultado.returncode != 0 or not paginas:
            salida = (resultado.stderr or resultado.stdout or b"").decode("utf-8", "ignore")[-500:]
            raise ErrorConversion("No se pudo convertir el PDF a imágenes.", detalle=salida)
        if len(paginas) > MAX_PAGINAS_BORRADOR:
            raise ErrorConversion(
                "El documento tiene demasiadas páginas para mostrarlo.",
                detalle=f"más de {MAX_PAGINAS_BORRADOR} páginas",
            )
        return [p.read_bytes() for p in paginas]