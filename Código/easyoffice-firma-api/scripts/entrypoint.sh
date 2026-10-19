#!/bin/sh
# Arranque del contenedor de la API: migraciones, bucket y servidor.
set -e

# --no-access-log: el log de acceso de uvicorn escribe la URL completa (con la
# query string) sin pasar por el filtro de datos sensibles. En su lugar,
# AccessLogMiddleware (app/core/middleware.py) registra método, ruta SIN query,
# estado y duración, a través del logger que enmascara correos, RUT y claves.
# Regla: ningún token ni API key viaja en la URL (siempre en header o body).

alembic upgrade head
python scripts/init_storage.py

if [ "$APP_ENV" = "development" ]; then
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --no-access-log
else
  # Solo se confía en X-Forwarded-For de los proxies listados (ej. Nginx):
  # la IP del firmante se guarda como evidencia y no debe poder falsificarse.
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log \
    --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1}"
fi
