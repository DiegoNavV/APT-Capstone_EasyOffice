"""
Tarea periodica: anonimizar las solicitudes de contacto descartadas vencidas (Ley 21.719,
ver app/retencion_datos.py). Se registra al levantar la app (lifespan en app/main.py) con
APScheduler en vez de un cron del sistema operativo o un contenedor sidecar aparte: el backend
ya corre como un proceso largo en Docker, asi que no hace falta infraestructura nueva, solo que
ese proceso se programe la tarea solo.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.database import SessionLocal
from app.retencion_datos import anonimizar_solicitudes_vencidas

log = logging.getLogger("easyoffice.scheduler")

ID_JOB_ANONIMIZACION = "anonimizar_solicitudes_vencidas"


def _correr_anonimizacion() -> None:
    """Corre en el hilo de APScheduler: abre su propia sesion (mismo patron que
    envio_firma.enviar_en_segundo_plano, porque no hay una peticion HTTP de la que colgarse) y
    nunca lanza, para no tumbar el scheduler si algo falla."""
    db = SessionLocal()
    try:
        total = anonimizar_solicitudes_vencidas(db)
        if total:
            log.info("%s solicitud(es) de contacto anonimizada(s).", total)
    except Exception:
        log.exception("Error al anonimizar solicitudes vencidas.")
    finally:
        db.close()


def iniciar_scheduler() -> BackgroundScheduler:
    """Crea y arranca el scheduler con el job de anonimizacion diario (3:00 UTC). Quien llama a
    esto (el lifespan de la app) es responsable de apagarlo despues con scheduler.shutdown()."""
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(_correr_anonimizacion, "cron", hour=3, minute=0, id=ID_JOB_ANONIMIZACION)
    scheduler.start()
    return scheduler
