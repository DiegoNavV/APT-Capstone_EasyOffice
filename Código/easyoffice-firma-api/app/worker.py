"""Worker de Celery (colas sobre Redis).

Tareas: `ping` (comprobar que el worker vive), `deliver_webhook_task`
(entrega de webhooks al CRM con reintentos y espera creciente) y
`expire_documents_task` (cada 5 minutos, expira documentos sin firmar vencidos).
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


# Tarea periódica (Celery beat, embebido en el worker con -B): expira documentos vencidos.
celery_app.conf.beat_schedule = {
    "expirar-documentos": {"task": "firma.expire_documents", "schedule": 300.0},
}


@celery_app.task(name="firma.expire_documents")
def expire_documents_task() -> int:
    from app.db.session import SessionLocal
    from app.services.signing import expire_due_documents

    db = SessionLocal()
    try:
        return expire_due_documents(db)
    finally:
        db.close()


@celery_app.task(name="firma.ping")
def ping() -> str:
    return "pong"


@celery_app.task(name="firma.deliver_webhook", bind=True, max_retries=None)
def deliver_webhook_task(self, delivery_id: str) -> bool:
    """Envía un webhook; si el CRM no responde 2xx reintenta con espera creciente
    (10 s, 20 s, 40 s, ... hasta 10 min) hasta WEBHOOK_MAX_ATTEMPTS intentos."""
    from app import models
    from app.db.session import SessionLocal
    from app.services import webhooks

    db = SessionLocal()
    try:
        if webhooks.deliver(db, delivery_id):
            return True
        entrega = db.get(models.WebhookDelivery, delivery_id)
        if entrega is not None and entrega.status == "pending":
            raise self.retry(countdown=min(600, 10 * 2 ** (entrega.attempts - 1)))
        return False
    finally:
        db.close()
