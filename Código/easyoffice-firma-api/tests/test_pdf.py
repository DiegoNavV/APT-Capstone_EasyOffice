"""Servicio PDF: validación, hoja de evidencias y sello PAdES verificable."""
import io
from datetime import datetime, timezone

import pytest
from pypdf import PdfReader

from app.services import pdf
from helpers import hacer_pdf


class TestValidacion:
    def test_pdf_valido(self):
        assert pdf.validate_pdf(hacer_pdf(paginas=3), 10_000_000) == 3

    @pytest.mark.parametrize("datos", [b"", b"hola", b"%PDF-1.4 basura sin estructura"])
    def test_invalidos(self, datos):
        with pytest.raises(pdf.InvalidPdf):
            pdf.validate_pdf(datos, 10_000_000)

    def test_demasiado_grande(self):
        with pytest.raises(pdf.InvalidPdf):
            pdf.validate_pdf(hacer_pdf(), 100)


def test_hoja_de_evidencias_se_anexa():
    hoja = pdf.build_evidence_page(
        document_id="doc-1", title="Contrato", external_ref="REF1", original_sha256="a" * 64,
        signers=[pdf.EvidenceSigner("Ana Ñúñez", "11111111-1", None, None, "Aceptación", "2026-10-15 10:00:00 UTC", "1.1.1.1", "UA")],
        verify_url="http://x/verify/aaa", generated_at=datetime.now(timezone.utc),
    )
    combinado = pdf.append_pdf(hacer_pdf(paginas=2), hoja)
    lector = PdfReader(io.BytesIO(combinado))
    assert len(lector.pages) == 3
    assert "Ana Ñúñez" in lector.pages[2].extract_text()


def test_certificado_se_crea_una_vez(tmp_path):
    k1, c1 = pdf.ensure_platform_certificate(str(tmp_path), "Easy Office SpA")
    huella = pdf.certificate_fingerprint(c1)
    k2, c2 = pdf.ensure_platform_certificate(str(tmp_path), "Easy Office SpA")
    assert (k1, c1) == (k2, c2)
    assert pdf.certificate_fingerprint(c2) == huella


def test_sello_pades_valido_e_integro(tmp_path):
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature

    clave, cert = pdf.ensure_platform_certificate(str(tmp_path), "Easy Office SpA")
    firmado = pdf.sign_pades(hacer_pdf(), clave, cert, reason="Prueba")

    lector = PdfFileReader(io.BytesIO(firmado))
    assert len(lector.embedded_signatures) == 1
    estado = validate_pdf_signature(lector.embedded_signatures[0])
    assert estado.intact is True   # el contenido no cambió después de firmar
    assert estado.valid is True    # la firma criptográfica es correcta


def test_sello_detecta_modificacion(tmp_path):
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature

    clave, cert = pdf.ensure_platform_certificate(str(tmp_path), "Easy Office SpA")
    firmado = bytearray(pdf.sign_pades(hacer_pdf("texto original"), clave, cert, reason="Prueba"))
    # Altera un byte del contenido firmado (el texto de la página).
    i = firmado.find(b"texto original")
    if i == -1:
        pytest.skip("El texto quedó comprimido; no se puede alterar directamente.")
    firmado[i] = ord("T")
    estado = validate_pdf_signature(PdfFileReader(io.BytesIO(bytes(firmado))).embedded_signatures[0])
    assert estado.intact is False
