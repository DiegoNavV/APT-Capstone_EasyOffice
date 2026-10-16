#!/bin/sh
# Arranque del contenedor de la API: migraciones, bucket y servidor.
set -e

alembic upgrade head
python scripts/init_storage.py

if [ "$APP_ENV" = "development" ]; then
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
else
  # Solo se confía en X-Forwarded-For de los proxies listados (ej. Nginx):
  # la IP del firmante se guarda como evidencia y no debe poder falsificarse.
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
    --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1}"
fi
