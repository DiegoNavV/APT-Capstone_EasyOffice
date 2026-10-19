"""Constantes y utilidades para los tests (importables desde cualquier test)."""
import io

API_KEY = "fk_test_clave-de-pruebas"
OTRA_API_KEY = "fk_test_otro-cliente"


def hacer_pdf(texto: str = "Contrato de servicio de prueba", paginas: int = 1) -> bytes:
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    for i in range(paginas):
        c.drawString(72, 750, f"{texto} - página {i + 1}")
        c.showPage()
    c.save()
    return buffer.getvalue()
