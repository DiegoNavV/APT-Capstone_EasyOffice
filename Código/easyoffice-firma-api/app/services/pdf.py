"""Operaciones sobre PDF: validar, agregar la hoja de evidencias y sellar (PAdES).

El sello usa un certificado propio de la plataforma, creado la primera vez que
se necesita. NO es un certificado emitido por un Prestador de Servicios de
Certificación acreditado (Ley 19.799): sirve para garantizar la integridad del
documento en las pruebas, no para una firma electrónica avanzada.
"""
import hashlib
import io
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

logger = logging.getLogger("firma.pdf")

KEY_FILE = "platform-key.pem"
CERT_FILE = "platform-cert.pem"


class InvalidPdf(ValueError):
    """El archivo recibido no es un PDF utilizable."""


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_pdf(data: bytes, max_bytes: int) -> int:
    """Comprueba que sea un PDF legible, sin cifrar y con páginas. Devuelve el número de páginas."""
    if len(data) > max_bytes:
        raise InvalidPdf(f"El PDF supera el máximo de {max_bytes // (1024 * 1024)} MB.")
    if not data.lstrip()[:5] == b"%PDF-":
        raise InvalidPdf("El archivo no es un PDF.")
    try:
        lector = PdfReader(io.BytesIO(data))
        if lector.is_encrypted:
            raise InvalidPdf("El PDF está protegido con contraseña.")
        paginas = len(lector.pages)
    except InvalidPdf:
        raise
    except (PdfReadError, Exception) as exc:  # noqa: BLE001 - cualquier error de lectura es un PDF inválido
        raise InvalidPdf("No se pudo leer el PDF.") from exc
    if paginas == 0:
        raise InvalidPdf("El PDF no tiene páginas.")
    return paginas


# ---------- Hoja de evidencias ----------

@dataclass
class EvidenceSigner:
    name: str
    rut: str | None
    represents_name: str | None
    represents_rut: str | None
    method: str
    signed_at: str
    ip: str | None = None
    user_agent: str | None = None


def build_evidence_page(
    *,
    document_id: str,
    title: str,
    external_ref: str | None,
    original_sha256: str,
    signers: list[EvidenceSigner],
    verify_url: str,
    generated_at: datetime,
) -> bytes:
    """Genera una página PDF con los datos de la firma, para anexar al documento."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    ancho, alto = A4
    x = 2 * cm
    y = alto - 2.2 * cm

    def linea(texto: str, tam: int = 9, negrita: bool = False, salto: float = 0.5) -> None:
        nonlocal y
        if y < 2.5 * cm:
            c.showPage()
            y = alto - 2.2 * cm
        c.setFont("Helvetica-Bold" if negrita else "Helvetica", tam)
        # Cortes simples para que el texto no se salga de la hoja.
        maximo = int((ancho - 4 * cm) / (tam * 0.5))
        while texto:
            c.drawString(x, y, texto[:maximo])
            texto = texto[maximo:]
            y -= salto * cm

    linea("HOJA DE EVIDENCIAS DE FIRMA ELECTRÓNICA SIMPLE", 13, True, 0.8)
    linea(f"Documento: {title}", 10, True)
    linea(f"Identificador: {document_id}")
    if external_ref:
        linea(f"Referencia: {external_ref}")
    linea(f"SHA-256 del documento original: {original_sha256}")
    linea(f"Hoja generada: {generated_at.astimezone(timezone.utc):%Y-%m-%d %H:%M:%S} UTC", salto=0.8)

    linea("Firmantes", 11, True, 0.6)
    for i, s in enumerate(signers, start=1):
        linea(f"{i}. {s.name}" + (f"  (RUT {s.rut})" if s.rut else ""), 10, True)
        if s.represents_name:
            linea(f"   En representación de: {s.represents_name}" + (f" (RUT {s.represents_rut})" if s.represents_rut else ""))
        linea(f"   Método: {s.method}")
        linea(f"   Fecha y hora: {s.signed_at}")
        if s.ip:
            linea(f"   IP: {s.ip}")
        if s.user_agent:
            linea(f"   Navegador: {s.user_agent[:160]}")
        y -= 0.2 * cm

    y -= 0.3 * cm
    linea("Verificación", 11, True, 0.6)
    linea(f"Este documento puede verificarse por su hash en: {verify_url}")
    linea("El sello digital de este PDF permite detectar cualquier modificación posterior a la firma.")
    y -= 0.3 * cm
    linea("Aviso: entorno de pruebas. El sello usa un certificado de la plataforma, no emitido por un", 8)
    linea("Prestador de Servicios de Certificación acreditado (Ley 19.799). Corresponde a firma electrónica simple.", 8)
    c.showPage()
    c.save()
    return buffer.getvalue()


def append_pdf(original: bytes, extra: bytes) -> bytes:
    """Devuelve el PDF original con las páginas de `extra` agregadas al final."""
    escritor = PdfWriter()
    escritor.append(PdfReader(io.BytesIO(original)))
    escritor.append(PdfReader(io.BytesIO(extra)))
    salida = io.BytesIO()
    escritor.write(salida)
    return salida.getvalue()


# ---------- Certificado de la plataforma y sello PAdES ----------

def ensure_platform_certificate(certs_dir: str, organization: str) -> tuple[Path, Path]:
    """Crea (una sola vez) una clave RSA y un certificado autofirmado para el sello."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    carpeta = Path(certs_dir)
    clave_path, cert_path = carpeta / KEY_FILE, carpeta / CERT_FILE
    if clave_path.exists() and cert_path.exists():
        return clave_path, cert_path

    carpeta.mkdir(parents=True, exist_ok=True)
    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nombre = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "CL"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
        x509.NameAttribute(NameOID.COMMON_NAME, f"{organization} - Plataforma FES (pruebas)"),
    ])
    ahora = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(nombre)
        .issuer_name(nombre)
        .public_key(clave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - timedelta(minutes=5))
        .not_valid_after(ahora + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=True, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]), critical=False)
        .sign(clave, hashes.SHA256())
    )
    clave_path.write_bytes(
        clave.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    clave_path.chmod(0o600)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    logger.info("Certificado de plataforma creado en %s", carpeta)
    return clave_path, cert_path


def certificate_fingerprint(cert_path: Path) -> str:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes

    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    return cert.fingerprint(hashes.SHA256()).hex()


def sign_pades(pdf: bytes, key_path: Path, cert_path: Path, reason: str, location: str = "Chile") -> bytes:
    """Aplica una firma digital PAdES (PDF Advanced Electronic Signature) con pyHanko."""
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import signers
    from pyhanko.sign.fields import SigSeedSubFilter

    firmante = signers.SimpleSigner.load(key_file=str(key_path), cert_file=str(cert_path))
    if firmante is None:
        raise RuntimeError("No se pudo cargar el certificado de la plataforma.")
    escritor = IncrementalPdfFileWriter(io.BytesIO(pdf), strict=False)
    metadatos = signers.PdfSignatureMetadata(
        field_name="FirmaPlataforma",
        reason=reason,
        location=location,
        md_algorithm="sha256",
        subfilter=SigSeedSubFilter.PADES,
    )
    salida = signers.sign_pdf(escritor, metadatos, signer=firmante)
    return salida.getvalue()
