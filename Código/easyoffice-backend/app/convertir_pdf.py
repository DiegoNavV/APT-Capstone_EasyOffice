"""
Convierte un documento Word (.docx) a PDF usando LibreOffice, que viene
instalado en la imagen de Docker del backend (ver Dockerfile).

Cada conversión usa su propia carpeta temporal y su propio perfil de LibreOffice:
así dos conversiones al mismo tiempo no se pisan y no queda nada en disco al
terminar. LibreOffice se ejecuta SIN shell, con argumentos fijos y un tiempo
máximo; el nombre del archivo lo fijamos nosotros, nunca viene del usuario.

Cola: solo se convierten CONVERSIONES_SIMULTANEAS documentos a la vez (LibreOffice
consume bastante memoria). Los demás esperan su turno; si la espera se pasa del
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