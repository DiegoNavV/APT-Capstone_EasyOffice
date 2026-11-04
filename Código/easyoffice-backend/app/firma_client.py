"""
Cliente de la API de firma (Ley 19.799). Contrato: easyoffice-firma-api/CONTRATO_INTEGRACION.md

Aqui solo se habla con la API: crear el documento, registrar la aceptacion o el rechazo delcliente y descargar el PDF firmado. Decidir cuando 
hacerlo y que estado queda en el tramite es responsabilidad de quien llama.

Reglas del contrato que se respetan:
  - El documento se identifica con el FOLIO (external_ref). El codigo de seguimiento del cliente nunca viaja a la API de firma.
  - Los POST llevan Idempotency-Key armada con el folio, asi un reintento no duplica nada.
  - Ningun dato personal ni clave va en la URL.
"""
import json
import logging
import os

import httpx

log = logging.getLogger("easyoffice.firma")

# Se leen en cada uso (no al importar) para que las pruebas puedan cambiarlas.
def _url_base() -> str:
    return os.getenv("FIRMA_API_URL", "http://firma-api:8000/api/v1").rstrip("/")


def _api_key() -> str:
    return os.getenv("FIRMA_API_KEY", "fk_test_dev-inseguro-cambiar")


def _callback_url() -> str:
    return os.getenv("FIRMA_CALLBACK_URL", "http://backend:8000/api/webhooks/firma")


# Segundos de espera por llamada. Enviar un PDF puede tardar mas que un simple aviso.
TIMEOUT_S = 60


class ErrorFirma(Exception):
    """Fallo al hablar con la API de firma.

    `reintentable` es True cuando conviene volver a intentar mas tarde (la API no responde,
    se demoro o fallo por dentro). Es False cuando la API rechazo lo enviado (datos invalidos,
    clave incorrecta, documento ya cerrado): repetir lo mismo dara el mismo error."""

    def __init__(self, mensaje: str, *, estado_http: int | None = None, reintentable: bool = False):
        super().__init__(mensaje)
        self.estado_http = estado_http
        self.reintentable = reintentable


def _headers(idempotency_key: str | None = None) -> dict:
    cabeceras = {"X-API-Key": _api_key()}
    if idempotency_key:
        cabeceras["Idempotency-Key"] = idempotency_key
    return cabeceras


def _llamar(metodo: str, ruta: str, **kw) -> httpx.Response:
    try:
        respuesta = httpx.request(metodo, f"{_url_base()}{ruta}", timeout=TIMEOUT_S, **kw)
        respuesta.raise_for_status()
        return respuesta
    except httpx.HTTPStatusError as exc:
        estado = exc.response.status_code
        # Solo se registra el codigo: el cuerpo de la respuesta puede traer datos personales.
        log.warning("API de firma respondio %s en %s %s", estado, metodo, ruta.split("?")[0])
        raise ErrorFirma(
            f"La API de firma respondio {estado}.",
            estado_http=estado,
            reintentable=estado >= 500 or estado == 429,
        ) from None
    except httpx.HTTPError as exc:
        log.warning("No se pudo conectar con la API de firma (%s)", type(exc).__name__)
        raise ErrorFirma(
            f"No se pudo conectar con la API de firma ({type(exc).__name__}).", reintentable=True
        ) from None


def crear_documento(*, pdf: bytes, titulo: str, folio: str, firmante: dict) -> dict:
    """Envia el PDF a firmar. `firmante` = {"name", "rut", "email"} y, si firma en nombre de
    una empresa, tambien "represents_name" y "represents_rut". Devuelve la respuesta de la API
    (trae `id`, `status` y `expires_at`)."""
    datos = {
        "title": titulo,
        "external_ref": folio,
        "signers": [firmante],
        "callback_url": _callback_url(),
    }
    return _llamar(
        "POST", "/documents",
        files={"file": (f"{folio}.pdf", pdf, "application/pdf")},
        data={"data": json.dumps(datos)},
        headers=_headers(f"doc-{folio}"),
    ).json()


def registrar_aceptacion(document_id: str, folio: str, ip: str, user_agent: str) -> dict:
    """El cliente acepto. `ip` y `user_agent` deben ser los de SU navegador: son la evidencia."""
    return _llamar(
        "POST", f"/documents/{document_id}/client-signature",
        json={"ip": ip, "user_agent": user_agent, "consent": True},
        headers=_headers(f"firma-{folio}"),
    ).json()


def registrar_rechazo(document_id: str, folio: str, ip: str, user_agent: str, motivo: str | None = None) -> dict:
    return _llamar(
        "POST", f"/documents/{document_id}/client-rejection",
        json={"ip": ip, "user_agent": user_agent, "reason": motivo},
        headers=_headers(f"rechazo-{folio}"),
    ).json()


def descargar_firmado(document_id: str) -> bytes:
    """PDF firmado. Solo existe cuando el documento esta `completed`."""
    return _llamar("GET", f"/documents/{document_id}/download?version=signed", headers=_headers()).content