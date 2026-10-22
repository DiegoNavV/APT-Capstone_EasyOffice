"""
Marca de agua del borrador que ve el cliente: "BORRADOR - SIN VALIDEZ" en rojo semitransparente, en diagonal y repetida por
toda la página. Se dibuja en el servidor y queda QUEMADA en la imagen (no es una capa del navegador que se pueda quitar).

El rojo es tenue a propósito: el texto negro del documento se sigue leyendo por debajo.
"""
import math
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from app.convertir_pdf import CALIDAD_JPEG, ErrorConversion

TEXTO = "BORRADOR - SIN VALIDEZ"
COLOR = (220, 0, 0, 80)            # rojo con alfa 80/255
ANGULO = 35                        # grados, de abajo-izquierda hacia arriba-derecha
# Viene en la imagen de Docker (fonts-dejavu-core); si no está se usa la fuente de Pillow.
FUENTE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _fuente(tamano: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(FUENTE, tamano)
    except OSError:
        return ImageFont.load_default(size=tamano)


def _capa_de_marca(ancho: int, alto: int) -> Image.Image:
    """Capa transparente del tamaño de la página con el texto repetido en diagonal."""
    tamano = max(14, ancho // 22)
    fuente = _fuente(tamano)
    izq, arriba, der, abajo = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), TEXTO, font=fuente)
    ancho_texto, alto_texto = der - izq, abajo - arriba
    paso_x = ancho_texto + tamano * 3
    paso_y = alto_texto * 5

    # Se dibuja en un cuadrado del tamaño de la diagonal para que, al girarlo, cubra toda la página.
    lado = int(math.hypot(ancho, alto)) + 1
    capa = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    dibujo = ImageDraw.Draw(capa)
    for fila, y in enumerate(range(0, lado, paso_y)):
        desfase = (paso_x // 2) * (fila % 2)          # filas intercaladas, como ladrillos
        for x in range(-paso_x + desfase, lado, paso_x):
            dibujo.text((x, y), TEXTO, font=fuente, fill=COLOR)
    capa = capa.rotate(ANGULO, resample=Image.BICUBIC)
    x0, y0 = (lado - ancho) // 2, (lado - alto) // 2
    return capa.crop((x0, y0, x0 + ancho, y0 + alto))


def marcar(jpeg: bytes) -> bytes:
    """Devuelve la página (JPEG) con la marca de agua. Lanza ErrorConversion si la imagen no se puede leer."""
    try:
        with Image.open(BytesIO(jpeg)) as original:
            pagina = original.convert("RGBA")
        pagina.alpha_composite(_capa_de_marca(*pagina.size))
        salida = BytesIO()
        pagina.convert("RGB").save(salida, format="JPEG", quality=CALIDAD_JPEG, optimize=True)
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ErrorConversion("No se pudo preparar la imagen del borrador.", detalle=repr(exc)) from None
    return salida.getvalue()
