"""Worker de Celery (colas sobre Redis).

En la Fase 5 aquí se registran las tareas de entrega de webhooks con
reintentos y backoff. En la Fase 0 solo existe `ping` para comprobar que el
worker está vivo.
"""
from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("firma", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Una tarea se confirma al terminar, no al recibirla: si el worker muere,
    # la tarea vuelve a la cola (importante para no perder webhooks).
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
)


@celery_app.task(name="firma.ping")
def ping() -> str:
    return "pong"
