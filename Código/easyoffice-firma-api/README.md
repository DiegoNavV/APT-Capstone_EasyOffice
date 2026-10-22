# easyoffice-firma-api

API REST de **firma electrónica simple (FES)** para las pruebas funcionales del CRM
Easy Office (`Código/easyoffice-backend`). Reemplaza al "módulo simulado de firma
electrónica" definido en `Definiciones_Desarrollo_CRM_EasyOffice.docx`, mientras
Easy Office no entregue acceso a la API de su proveedor.

> **Versión 0.2.0 (pruebas).** Firma de verdad: guarda el PDF, registra la
> aceptación del cliente con evidencia, aplica la firma automática de Easy Office
> con sello digital **PAdES**, anexa una hoja de evidencias, avisa por webhook y
> permite verificar el documento por su hash.
>
> 👉 **Para integrar el CRM: ver [`CONTRATO_INTEGRACION.md`](CONTRATO_INTEGRACION.md).**

## Flujo

1. El cliente ingresa su código de seguimiento, completa sus datos y acepta.
2. El CRM genera el PDF y lo envía: `POST /api/v1/documents`.
3. El CRM registra la aceptación del cliente (IP, navegador, consentimiento):
   `POST /api/v1/documents/{id}/client-signature`.
4. La API aplica la **firma automática de Easy Office**, agrega la **hoja de
   evidencias** y **sella** el PDF (PAdES). El documento queda `completed`.
5. El CRM descarga el PDF firmado y marca el trámite como `firmado`.
6. Cualquiera puede verificar el PDF por su SHA-256: `GET /api/v1/verify/{sha256}`.

Si el cliente **rechaza** (`POST /api/v1/documents/{id}/client-rejection`) el documento
queda `rejected`; si nadie firma antes de `expires_at` (30 días por defecto) queda
`expired`. Cada estado final se avisa al CRM por webhook firmado (HMAC + marca de tiempo).
El trámite se identifica con el **folio**; el código de seguimiento del cliente nunca
llega a esta API.

## Alcance

- **FES**: la aceptación del cliente es su firma; la evidencia queda en la hoja de
  evidencias y en una bitácora de auditoría con hash encadenado.
- El sello usa un **certificado de la plataforma**, no de un Prestador de Servicios
  de Certificación acreditado (Ley 19.799): garantiza integridad, no es FEA.
- Fuera de esta versión: OTP por correo, gestión de organizaciones y API keys en
  base de datos (Fase 1), sello de tiempo de una TSA.
- **VALIDAR CON ABOGADO**: validez de la firma automática y plazos de retención.

## Arquitectura

| Servicio | Para qué | Puerto local |
|---|---|---|
| `api` | FastAPI: documentos, firma, verificación | 8100 |
| `worker` | Celery: envío de webhooks con reintentos | — |
| `db` | PostgreSQL 16 | interno |
| `redis` | Cola de tareas | interno |
| `minio` | Almacenamiento de PDFs (S3) | consola 9101 |
| `mailpit` | Captura de correos (para el futuro OTP) | 8025 |

```
app/
  main.py                 crea la app, middlewares y rutas
  worker.py               Celery (webhooks)
  models.py               documentos, firmantes, auditoría, idempotencia, webhooks
  schemas.py              validación de entrada y salida
  api/v1/documents.py     endpoints de documentos y firma
  api/v1/verify.py        verificación pública por hash
  api/v1/health.py        health checks
  core/                   configuración, API key, logs, middlewares, MinIO
  services/signing.py     flujo de firma
  services/pdf.py         validación, hoja de evidencias, sello PAdES (pyHanko)
  services/audit.py       bitácora append-only con hash encadenado
  services/webhooks.py    webhooks firmados con HMAC-SHA256
  services/idempotency.py Idempotency-Key
alembic/                  migraciones
scripts/demo_firma.py     demostración del flujo completo
tests/                    pytest (SQLite y almacenamiento en memoria)
```

## Manual de uso

### Opción A: en el navegador (GitHub Codespaces, sin instalar nada)

1. En el repositorio, elegir la rama → **Code → Codespaces → Create codespace**.
2. Si pregunta, **"Confiar en la carpeta y continuar"**.
3. En la **Terminal**, pegar (una sola vez):

```bash
sudo iptables-legacy -I FORWARD -i br+ -o br+ -j ACCEPT
docker network create easyoffice-net 2>/dev/null || true
cd "Código/easyoffice-firma-api" && cp .env.example .env && docker compose up --build -d
```

4. Esperar 2 a 4 minutos y probar:

```bash
sleep 20; curl -s localhost:8100/api/v1/health/ready
docker compose exec api python scripts/demo_firma.py
```

5. Documentación interactiva: pestaña **Puertos** → 8100 → 🌐 → agregar **`/docs`**.
   Botón **Authorize** → pegar la API key (`fk_test_dev-inseguro-cambiar`).
6. Al terminar: **github.com/codespaces → `···` → Stop codespace**.

> ⚠️ La línea `iptables-legacy` es obligatoria en cada Codespace nuevo o
> reiniciado: es una falla conocida de Codespaces que bloquea la conexión entre
> contenedores. En Docker Desktop no hace falta.

### Opción B: en el computador (Docker Desktop)

```bash
cd "Código/easyoffice-firma-api"
cp .env.example .env          # en CMD de Windows: copy .env.example .env
docker network create easyoffice-net   # solo la primera vez (red compartida con el CRM)
docker compose up --build -d
docker compose exec api python scripts/demo_firma.py
```

Abrir http://localhost:8100/docs

### Comandos útiles

| Para | Comando |
|---|---|
| Ver estado de los servicios | `docker compose ps` |
| Ver logs de la API | `docker compose logs api --tail 40` |
| Demo del flujo completo | `docker compose exec api python scripts/demo_firma.py` |
| Copiar el PDF firmado de la demo | `docker compose cp api:/tmp/demo-contrato-firmado.pdf .` |
| Correr los tests | `docker compose run --rm api pytest -v` |
| Apagar (conserva datos) | `docker compose down` |
| Apagar y borrar datos | `docker compose down -v` |

### Problemas conocidos

- **`network easyoffice-net declared as external, but could not be found`** → falta crear la red: `docker network create easyoffice-net`.
- **API `exited` o `health: starting` en Codespaces** → falta la línea `iptables-legacy`; ejecutarla y luego `docker compose up -d`.
- **`pull access denied for minio/minio`** → MinIO dejó Docker Hub y quay.io; se usa `cgr.dev/chainguard/minio:latest` (ya configurado).
- **Un comando pegado aparece repetido** → `Ctrl+C` y pegar de nuevo con un solo `Ctrl+V`.
- **`{"detail":"Not Found"}`** en la raíz es normal → agregar `/docs`.

## Seguridad

- API key por header `X-API-Key` (comparación en tiempo constante); cada cliente solo ve sus documentos.
- `Idempotency-Key` en los POST: los reintentos no duplican documentos ni firmas.
- PDF validado (formato, tamaño máx. 10 MB, sin contraseña).
- Webhooks firmados con HMAC-SHA256 y solo hacia hosts permitidos (evita SSRF).
- Auditoría append-only con hash encadenado; en Postgres un trigger impide editarla o borrarla.
- Verificación pública sin datos personales.
- Secretos solo por variables de entorno; en producción la API no arranca con valores de desarrollo.
  `MASTER_KEY_HEX` se valida (64 caracteres hex) en todos los entornos.
- Log de acceso propio sin query string (el de uvicorn está desactivado). Regla:
  ningún token ni API key viaja en la URL; siempre en header o body.
- Headers de seguridad, logs JSON con datos sensibles enmascarados, contenedor sin root.

## Plan por fases

| Fase | Contenido | Estado |
|---|---|---|
| 0 | Esqueleto: docker-compose, configuración, Alembic, health checks | ✅ |
| Pruebas (0.2) | Documentos, FES del cliente, rechazo, expiración, firma automática PAdES, evidencias, webhooks, verificación | ✅ |
| 1 | Organizaciones y API keys en base de datos, rate limit | |
| 3 | OTP por correo | |
| 4 | Sello de tiempo (TSA) y adaptador al proveedor real de Easy Office | |
