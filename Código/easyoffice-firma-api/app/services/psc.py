"""
Interfaz de los proveedores de firma avanzada (FEA) y una implementación simulada.

La FEA real se delega a un Prestador de Servicios de Certificación acreditado (Ley 19.799, D.S. 181).
Este módulo define la interfaz y un MockPSC para pruebas.

El MockPSC NO produce una firma válida: su resultado siempre lleva tipo "FEA_SIMULADA",
para que nunca se presente como FEA.
"""
import hashlib
import hmac
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

TIPO_SIMULADA = "FEA_SIMULADA"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ErrorPSC(Exception):
    """Error al pedir una firma a un proveedor."""


@dataclass(frozen=True)
class ResultadoFirma:
    proveedor: str
    tipo: str
    firmante: str
    sha256_documento: str
    firmado_en: str
    firma: str


def _validar_entrada(sha256_documento: str, firmante: str) -> None:
    if not _SHA256.match(sha256_documento):
        raise ValueError("El hash del documento debe ser SHA-256 en minúsculas (64 caracteres hex).")
    if not firmante or not firmante.strip():
        raise ValueError("El firmante no puede estar vacío.")


class PSCProvider(ABC):
    """Contrato que debe cumplir cualquier proveedor de FEA (real o simulado)."""

    nombre: str = "base"

    @abstractmethod
    def firmar(self, sha256_documento: str, firmante: str) -> ResultadoFirma:
        """Firma avanzada del hash del documento en nombre de `firmante`."""


class MockPSC(PSCProvider):
    """Proveedor simulado para pruebas. Firma con HMAC, no con un certificado acreditado."""

    nombre = "mock"

    def __init__(self, secreto: str):
        if not secreto:
            raise ValueError("El MockPSC necesita un secreto.")
        self._secreto = secreto.encode("utf-8")

    def firmar(self, sha256_documento: str, firmante: str, ahora: datetime | None = None) -> ResultadoFirma:
        _validar_entrada(sha256_documento, firmante)
        instante = (ahora or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        mensaje = f"{sha256_documento}|{firmante.strip()}|{instante}".encode("utf-8")
        firma = hmac.new(self._secreto, mensaje, hashlib.sha256).hexdigest()
        return ResultadoFirma(
            proveedor=self.nombre,
            tipo=TIPO_SIMULADA,
            firmante=firmante.strip(),
            sha256_documento=sha256_documento,
            firmado_en=instante,
            firma=firma,
        )
