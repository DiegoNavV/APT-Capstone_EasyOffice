# easyoffice-firma-api

API REST de firma electrónica simple (FES) para pruebas del CRM Easy Office (Código/easyoffice-backend).

Estado: carpeta creada. El código se agregará por fases.

## Objetivo
1. El agente convierte una solicitud en trámite en el CRM.
2. El CRM envía el PDF y los firmantes a POST /api/v1/documents.
3. Cada firmante recibe un enlace único y confirma con un código OTP por correo.
4. Con todas las firmas, la API sella el PDF (PAdES) y agrega una hoja de evidencias.
5. La API avisa al CRM con un webhook document.completed y el trámite queda "firmado".
6. Cualquiera puede verificar el documento por su hash SHA-256.

## Documentos iniciales
- Servicio 1: Contrato de servicios de oficina (LF-0152)
- Servicio 2: Autorización de domicilio tributario

## Alcance
Solo FES. La firma electrónica avanzada (FEA) requiere un prestador acreditado (Ley 19.799) y queda fuera de esta etapa.

## Stack
Python 3.12, FastAPI, PostgreSQL 16, SQLAlchemy, Alembic, Redis, MinIO, Celery, pyHanko, Docker Compose, Pytest.