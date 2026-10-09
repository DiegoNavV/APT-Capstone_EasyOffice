# easyoffice-firma-api

API REST de **firma electrónica simple (FES)** para pruebas del CRM Easy Office
(`Código/easyoffice-backend`). Es el "módulo simulado de firma electrónica"
definido en `Definiciones_Desarrollo_CRM_EasyOffice.docx`, mientras Easy Office
no entregue acceso a la API de su proveedor.

> **Estado: Fase 0 (esqueleto).** Hoy solo responde health checks. Las demás
> funciones se agregan por fases (ver abajo).

## Cómo encaja con el CRM

1. El cliente ingresa su código de seguimiento en la web, completa sus datos y
   presiona "generar documento con firma".
2. El CRM genera el PDF desde `plantilla_documento` y lo envía a esta API.
3. **Firma el cliente** (FES): se identifica con el código y un OTP enviado a su correo.
4. **Firma Easy Office automáticamente** ("firma desatendida"), sin intervención humana.
5. La API sella el PDF (PAdES), agrega una hoja de evidencias y avisa al CRM
   con un webhook `document.completed`.
6. El trámite pasa a `firmado` y el cliente descarga el documento.

| Evento en la API | Estado del trámite en el CRM |
|---|---|
| Documento creado | `procesando_firma` |
| `document.completed` | `firmado` |
| El cliente descarga | `entregado` |
| `signer.declined` | `rechazado` |

## Alcance

Solo **FES**. No somos Prestador de Servicios de Certificación acreditado
(Ley 19.799): la FEA queda fuera. La firma automática de Easy Office y los
plazos de retención están marcados **VALIDAR CON ABOGADO**.

## Arquitectura

| Servicio | Para qué | Puerto local |
|---|---|---|
| `api` | FastAPI | http://localhost:8100 |
| `worker` | Celery: webhooks con reintentos (Fase 5) | — |
| `db` | PostgreSQL 16 | interno |
| `redis` | Rate limit y colas | interno |
| `minio` | Almacenamiento de PDFs | consola http://localhost:9101 |
| `mailpit` | Captura los correos de OTP en desarrollo | http://localhost:8025 |

Los puertos no chocan con el compose del CRM (8000, 8080, 5432) y solo se
publican en `127.0.0.1`.

```
app/
  main.py              crea la app, middlewares y rutas
  worker.py            Celery
  core/config.py       configuración por variables de entorno
  core/logging_config.py  logs JSON con datos sensibles enmascarados
  core/middleware.py   X-Request-ID y headers de seguridad
  core/storage.py      cliente MinIO con tiempos de espera
  db/                  SQLAlchemy (base y sesión)
  api/v1/health.py     /api/v1/health y /api/v1/health/ready
  services/health.py   chequeos de base de datos, Redis y MinIO
alembic/               migraciones
scripts/               arranque del contenedor e inicialización de MinIO
tests/                 pytest (SQLite en memoria, sin servicios externos)
```

## Instalación

Requisito: Docker Desktop.

```bash
cd Código/easyoffice-firma-api
cp .env.example .env          # en CMD de Windows: copy .env.example .env
docker compose up --build
```

Al arrancar, la API aplica las migraciones y crea el bucket de MinIO.

### Conexión con el CRM (Docker)

El CRM corre en otro `docker-compose`. Dentro de su contenedor, `localhost`
es el propio contenedor del CRM, no tu computador, así que **no** sirve
`http://localhost:8100`. Por eso esta API crea la red Docker compartida
`easyoffice-net` y se publica en ella con el nombre `firma-api`.

1. Levantar **primero** esta API (crea la red).
2. En el `docker-compose.yml` del CRM, agregar la red al servicio `backend`:

   ```yaml
   services:
     backend:
       networks: [default, easyoffice-net]

   networks:
     easyoffice-net:
       external: true
   ```

3. Desde el backend del CRM, la API queda en `http://firma-api:8000/api/v1/...`.
   Desde tu navegador o curl, en `http://localhost:8100/api/v1/...`.

Este cambio en el CRM se hace en la Fase 6; no es necesario para probar la API sola.

## Probar

```bash
# El proceso está vivo
curl http://localhost:8100/api/v1/health

# Base de datos, Redis y MinIO responden (200 si todo ok, 503 si algo falla)
curl http://localhost:8100/api/v1/health/ready
```

Documentación interactiva (OpenAPI): http://localhost:8100/docs

## Tests

Con Docker:

```bash
docker compose run --rm api pytest -v
```

Sin Docker (Python 3.12):

```bash
pip install -r requirements.txt
pytest -v
```

También corren en GitHub Actions (`.github/workflows/firma-api.yml`) cada vez
que cambia esta carpeta.

## Seguridad (Fase 0)

- Secretos solo por variables de entorno. En `APP_ENV=production` la API no
  arranca si algún secreto sigue con el valor de desarrollo.
- Headers de seguridad en todas las respuestas; HSTS solo en producción.
- `/docs` y `/openapi.json` deshabilitados en producción.
- Logs en JSON con correos, RUTs, API keys y tokens enmascarados.
- CORS cerrado por defecto: la API se consume servidor a servidor.
- El contenedor corre con un usuario sin privilegios.
- `X-Forwarded-For` solo se acepta de los proxies en `FORWARDED_ALLOW_IPS`:
  la IP del firmante es evidencia y no debe poder falsificarse.
- Tiempos de espera acotados al consultar base de datos, Redis y MinIO.

## Plan por fases

| Fase | Contenido | Estado |
|---|---|---|
| 0 | Esqueleto: docker-compose, configuración, Alembic, health checks, tests | ✅ |
| 1 | Organizaciones, API keys, rate limit, idempotencia, auditoría encadenada | |
| 2 | Documentos: subida de PDF, SHA-256, firmantes, orden, expiración, cancelación | |
| 3 | Flujo FES: OTP por correo, evidencias, firma automática de Easy Office | |
| 4 | Sellado PAdES, hoja de evidencias, verificación por hash | |
| 5 | Webhooks con HMAC y reintentos | |
| 6 | Integración con el CRM y test de extremo a extremo | |

## Documentos iniciales

| Servicio en el CRM (seed) | Documento |
|---|---|
| 1 — Contrato de servicio | Contrato de servicios de oficina (LF-0152) |
| 2 — Autorización de domicilio tributario | Autorización de domicilio tributario |
