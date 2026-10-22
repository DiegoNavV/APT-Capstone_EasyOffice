# Contrato de integración: CRM ↔ API de firma

Cómo se conectan el CRM (`Código/easyoffice-backend`) y la API de firma
(`Código/easyoffice-firma-api`). Versión de la API: **0.2.0**.

## 0. Acuerdos (revisión del PR #31)

| # | Tema | Acuerdo |
|---|---|---|
| 1 | Qué envía el CRM | El **PDF** y, por cada firmante, **nombre, RUT y correo** (y la empresa que representa con su RUT, si aplica). Además un título y el folio. |
| 2 | Identificador del trámite | El **folio** (ej. `LF-0152-2026`) en `external_ref`. **El código de seguimiento del cliente nunca viaja** a la API de firma: ni en el cuerpo, ni en la URL, ni en `Idempotency-Key`. |
| 3 | Entrega del firmado | El aviso `document.completed` trae el `document_id`. El CRM **descarga** el PDF firmado desde la API y lo guarda como **copia oficial**. La copia de la API queda como respaldo y evidencia durante el plazo de retención. **El cliente nunca descarga desde la API de firma.** |
| 4 | Avisos de cambios | Webhook `POST` al CRM con los eventos `document.completed`, `document.rejected`, `document.expired` y `document.cancelled`, firmado con **HMAC-SHA256 + marca de tiempo** (sección 6). |
| 5 | Rechazo o plazo vencido | El cliente puede **rechazar** (`client-rejection`, con motivo opcional) → `rejected`. Si nadie firma antes de `expires_at` (30 días por defecto, configurable por documento) → `expired`. Ambos casos avisan por webhook. |

Reglas generales: ningún token, API key ni dato personal viaja en la URL
(siempre en header o body); la API no escribe la query string en sus logs.

## 1. Flujo

```
Cliente (sitio web)        CRM backend                              API de firma
───────────────────        ───────────                              ────────────
completa datos      ──▶    registrar_envio_datos()
                           trámite -> procesando_firma
                           genera el PDF desde la plantilla
                           POST /documents (PDF, firmantes, folio,  ──▶ guarda PDF + SHA-256
                                callback_url)                       ◀── 201 {id, status: pending, expires_at}
acepta / rechaza    ──▶    POST /documents/{id}/client-signature    ──▶ firma del cliente (FES)
                             (o /client-rejection)                      + firma automática de Easy Office
                                                                        + hoja de evidencias + sello PAdES
                                                                    ◀── 200 {status: completed | rejected}
                           ◀── webhook document.completed {document_id}
                           GET /documents/{id}/download             ──▶
                                                                    ◀── PDF firmado
                           guarda la copia oficial
                           trámite -> firmado
cliente descarga    ◀──    (desde el CRM, nunca desde la API de firma)
```

La respuesta de `client-signature` ya indica `completed`; el webhook confirma el
mismo hecho y es el aviso oficial (también cubre `expired`, que no ocurre
durante una petición del CRM). El CRM puede actuar con cualquiera de los dos,
pero debe tolerar recibir el aviso aunque ya haya procesado la respuesta.

## 2. Conexión

| Desde | URL base |
|---|---|
| Backend del CRM (contenedor) | `http://firma-api:8000/api/v1` |
| Navegador o curl en tu PC | `http://localhost:8100/api/v1` |
| Codespaces | pestaña **Puertos** → 8100 |

La red Docker compartida se crea **una sola vez** y es **externa** en ambos
compose (no importa cuál se levante primero):

```bash
docker network create easyoffice-net
```

En el `docker-compose.yml` del CRM:

```yaml
services:
  backend:
    networks: [default, easyoffice-net]

networks:
  easyoffice-net:
    external: true
```

Variables de entorno para el backend del CRM:

```env
FIRMA_API_URL=http://firma-api:8000/api/v1
FIRMA_API_KEY=fk_test_dev-inseguro-cambiar     # debe estar en API_KEYS de la API de firma
FIRMA_WEBHOOK_SECRET=dev-inseguro-cambiar      # igual a WEBHOOK_SECRET de la API de firma
```

## 3. Autenticación e idempotencia

- Header obligatorio (salvo `/health` y `/verify`): `X-API-Key: <clave>`. Sin ella o incorrecta → `401`.
- Cada clave solo ve sus propios documentos (los de otra clave responden `404`).
- `Idempotency-Key` en los `POST` (recomendado), construida con el **folio**:
  `doc-LF-0152-2026`, `firma-LF-0152-2026`, `rechazo-LF-0152-2026`. Si se repite
  con el mismo contenido, la API devuelve la misma respuesta sin duplicar nada;
  con contenido distinto responde `409`.

## 4. Endpoints

### 4.1 `POST /documents`: enviar un PDF a firmar

`multipart/form-data`:

- `file`: el PDF (máx. 10 MB, sin contraseña).
- `data`: JSON (texto):

| Campo | Tipo | Oblig. | Descripción |
|---|---|---|---|
| `title` | texto ≤200 | sí | Ej. "Contrato de servicio" |
| `external_ref` | texto ≤100 | sí (acordado) | **Folio** del trámite |
| `signers` | lista 1–10 | sí | Personas que firman, en orden |
| `signers[].name` | texto | sí | |
| `signers[].rut` | texto | sí (acordado) | Se valida el dígito verificador |
| `signers[].email` | texto | sí (acordado) | |
| `signers[].represents_name` | texto | no | Empresa que representa |
| `signers[].represents_rut` | texto | no | RUT de la empresa |
| `expires_in_days` | 1–90 | no | Plazo para firmar (por defecto 30) |
| `callback_url` | URL | sí (acordado) | `http://backend:8000/api/webhooks/firma` |
| `auto_organization_signature` | bool | no (true) | Firma automática de Easy Office al final |
| `metadata` | objeto | no | Datos libres sin datos personales (≤4000 caracteres) |

```bash
curl -X POST http://localhost:8100/api/v1/documents \
  -H "X-API-Key: fk_test_dev-inseguro-cambiar" \
  -H "Idempotency-Key: doc-LF-0152-2026" \
  -F "file=@contrato.pdf;type=application/pdf" \
  -F 'data={"title":"Contrato de servicio","external_ref":"LF-0152-2026",
            "signers":[{"name":"Juan Pérez","rut":"12.345.678-5","email":"juan@cliente.cl",
                        "represents_name":"Empresa Cliente SpA","represents_rut":"76.543.210-3"}],
            "callback_url":"http://backend:8000/api/webhooks/firma"}'
```

Respuesta `201` (resumida):

```json
{
  "id": "6f1c…",
  "external_ref": "LF-0152-2026",
  "status": "pending",
  "expires_at": "2026-11-18T20:00:00Z",
  "original_sha256": "3aa6ee1a…",
  "signers": [
    {"id": "a1…", "order": 1, "kind": "person", "name": "Juan Pérez", "status": "pending"},
    {"id": "b2…", "order": 2, "kind": "organization_auto", "name": "Easy Office SpA", "status": "pending"}
  ],
  "links": {"download_signed": null, "evidence": "/api/v1/documents/6f1c…/evidence", "verify": "/api/v1/verify/3aa6…"}
}
```

### 4.2 `POST /documents/{id}/client-signature`: el cliente acepta

El CRM lo llama **en nombre del cliente** cuando acepta en el sitio. `ip` y
`user_agent` deben ser los **del navegador del cliente** (son la evidencia).

```json
{ "ip": "200.1.2.3", "user_agent": "Mozilla/5.0 …", "consent": true }
```

Opcionales: `signer_id` (si hay varios firmantes; el orden es secuencial) y
`accepted_at` (fecha ISO). Cuando firman todas las personas, la API aplica la
firma automática de Easy Office, anexa la **hoja de evidencias**, sella el PDF
(**PAdES**) y responde `200` con `status: completed`.

### 4.3 `POST /documents/{id}/client-rejection`: el cliente rechaza

```json
{ "ip": "200.1.2.3", "user_agent": "Mozilla/5.0 …", "reason": "Los datos de la empresa están mal" }
```

`reason` es opcional (≤500). El documento queda `rejected`, no admite más firmas
y se avisa con `document.rejected` (incluye `rejection_reason`).

### 4.4 `GET /documents/{id}/download?version=signed`

PDF firmado (`application/pdf`). Antes de completarse → `409`.
`version=original` entrega el PDF tal como se envió.

### 4.5 Otros

| Método y ruta | Uso |
|---|---|
| `GET /documents/{id}` | Estado (si venció el plazo, lo marca `expired` en ese momento) |
| `POST /documents/{id}/cancel` | Cancelar un documento pendiente (ej. el agente anula el trámite) |
| `GET /documents/{id}/evidence` | Bitácora de auditoría con hash encadenado |
| `GET /verify/{sha256}` | **Pública**: verifica un PDF por su hash, sin datos personales |
| `GET /health/ready` | Estado de la API y sus dependencias |

## 5. Estados

| Documento (API de firma) | Cuándo | Trámite (CRM) | Evento |
|---|---|---|---|
| `pending` | Creado, esperando firma | `procesando_firma` | — |
| `completed` | Firmaron todos | `firmado` (y `entregado` cuando el cliente descarga desde el CRM) | `document.completed` |
| `rejected` | El cliente rechazó | `rechazado` | `document.rejected` |
| `expired` | Venció `expires_at` sin firmas | `rechazado` (o regenerar y reenviar) | `document.expired` |
| `cancelled` | El CRM lo canceló | según el CRM | `document.cancelled` |

Guardar en el trámite el `id` del documento de firma (sugerido: columna
`id_documento_firma`) y la ruta de la copia oficial en `ruta_documento_generado`.

## 6. Webhook

```
POST http://backend:8000/api/webhooks/firma
Content-Type: application/json
X-Firma-Event: document.completed
X-Firma-Delivery: <id único del aviso>
X-Firma-Timestamp: 1760900000
X-Firma-Signature: sha256=<HMAC-SHA256(WEBHOOK_SECRET, "<timestamp>." + cuerpo)>

{"event":"document.completed","document_id":"6f1c…","external_ref":"LF-0152-2026",
 "status":"completed","signed_sha256":"…","signature_type":"pades","completed_at":"…"}
```

El CRM debe:

1. Recalcular la firma sobre `"<timestamp>." + cuerpo` (bytes exactos) y compararla en tiempo constante.
2. Rechazar si el timestamp difiere en más de **5 minutos** de la hora actual (evita reenvíos de avisos viejos).
3. Responder `2xx` rápido. Si no, la API reintenta con espera creciente (hasta 6 intentos).
4. Ser idempotente: el mismo aviso puede llegar más de una vez (usar `X-Firma-Delivery` o `document_id`).

## 7. Código de ejemplo para el CRM (Python / FastAPI)

### 7.1 Cliente de la API de firma

```python
# app/firma_client.py
import json
import os

import httpx

FIRMA_API_URL = os.getenv("FIRMA_API_URL", "http://firma-api:8000/api/v1")
FIRMA_API_KEY = os.getenv("FIRMA_API_KEY", "fk_test_dev-inseguro-cambiar")
CALLBACK_URL = os.getenv("FIRMA_CALLBACK_URL", "http://backend:8000/api/webhooks/firma")


class ErrorFirma(Exception):
    pass


def _headers(idem: str | None = None) -> dict:
    h = {"X-API-Key": FIRMA_API_KEY}
    if idem:
        h["Idempotency-Key"] = idem
    return h


def _llamar(metodo: str, ruta: str, **kw) -> httpx.Response:
    try:
        r = httpx.request(metodo, f"{FIRMA_API_URL}{ruta}", timeout=60, **kw)
        r.raise_for_status()
        return r
    except httpx.HTTPStatusError as exc:
        raise ErrorFirma(f"API de firma respondió {exc.response.status_code}: {exc.response.text[:300]}") from exc
    except httpx.HTTPError as exc:
        raise ErrorFirma(f"No se pudo conectar con la API de firma: {type(exc).__name__}") from exc


def crear_documento(*, pdf: bytes, titulo: str, folio: str, firmante: dict) -> dict:
    """firmante = {"name", "rut", "email", "represents_name", "represents_rut"}"""
    datos = {"title": titulo, "external_ref": folio, "signers": [firmante], "callback_url": CALLBACK_URL}
    return _llamar(
        "POST", "/documents",
        files={"file": (f"{folio}.pdf", pdf, "application/pdf")},
        data={"data": json.dumps(datos)},
        headers=_headers(f"doc-{folio}"),
    ).json()


def registrar_aceptacion(document_id: str, folio: str, ip: str, user_agent: str) -> dict:
    return _llamar(
        "POST", f"/documents/{document_id}/client-signature",
        json={"ip": ip, "user_agent": user_agent, "consent": True},
        headers=_headers(f"firma-{folio}"),
    ).json()


def registrar_rechazo(document_id: str, folio: str, ip: str, user_agent: str, motivo: str | None) -> dict:
    return _llamar(
        "POST", f"/documents/{document_id}/client-rejection",
        json={"ip": ip, "user_agent": user_agent, "reason": motivo},
        headers=_headers(f"rechazo-{folio}"),
    ).json()


def descargar_firmado(document_id: str) -> bytes:
    return _llamar("GET", f"/documents/{document_id}/download", headers=_headers()).content
```

La IP del cliente se obtiene en el router con `request.client.host` (detrás de
Nginx, el header `X-Forwarded-For` configurado como confiable) y el navegador con
`request.headers.get("user-agent")`.

### 7.2 Receptor del webhook

```python
# app/routers/webhook_firma.py
import hashlib
import hmac
import json
import os
import time

from fastapi import APIRouter, Header, HTTPException, Request

router = APIRouter()
SECRETO = os.getenv("FIRMA_WEBHOOK_SECRET", "dev-inseguro-cambiar").encode()
TOLERANCIA_S = 300


@router.post("/api/webhooks/firma")
async def webhook_firma(
    request: Request,
    x_firma_timestamp: str = Header(...),
    x_firma_signature: str = Header(...),
):
    cuerpo = await request.body()
    try:
        vigente = abs(time.time() - int(x_firma_timestamp)) <= TOLERANCIA_S
    except ValueError:
        vigente = False
    esperado = "sha256=" + hmac.new(SECRETO, x_firma_timestamp.encode() + b"." + cuerpo, hashlib.sha256).hexdigest()
    if not vigente or not hmac.compare_digest(esperado, x_firma_signature):
        raise HTTPException(401, "Aviso de firma inválido")

    evento = json.loads(cuerpo)
    folio = evento["external_ref"]
    if evento["event"] == "document.completed":
        ...  # descargar_firmado(evento["document_id"]), guardar copia oficial, trámite -> firmado
    elif evento["event"] in ("document.rejected", "document.expired"):
        ...  # trámite -> rechazado (guardar evento.get("rejection_reason"))
    return {"ok": True}
```

## 8. Errores

| Código | Cuándo |
|---|---|
| `401` | Falta `X-API-Key` o es incorrecta |
| `404` | El documento no existe o es de otra clave |
| `409` | No permitido en el estado actual (ya firmado, rechazado, expirado, cancelado, fuera de orden) o `Idempotency-Key` reutilizada con otro contenido |
| `413` | PDF de más de 10 MB |
| `422` | Datos inválidos: PDF ilegible, RUT incorrecto, `consent` distinto de `true`, `callback_url` no permitida, `expires_in_days` fuera de 1–90… |

## 9. Alcance y limitaciones

- **Firma electrónica simple (FES)**: la aceptación del cliente en el sitio más la
  evidencia (IP, navegador, hora, hash del documento).
- La **firma automática de Easy Office** usa un certificado **de la plataforma**,
  no de un Prestador de Servicios de Certificación acreditado (Ley 19.799):
  garantiza la integridad del PDF, pero no es FEA.
- Cuando Easy Office entregue la API de su proveedor real, se reemplaza el
  interior de la API de firma; **este contrato no cambia**.
- OTP por correo: previsto (`client_verification: "otp"`), aún no habilitado.
- **VALIDAR CON ABOGADO**: validez de la firma automática, plazo de retención (6 años por defecto) y plazo para firmar.
