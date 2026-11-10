"""
Pruebas de app.scheduler (tarea periodica de anonimizacion, ver app/retencion_datos.py).
"""
from datetime import datetime, timedelta, timezone

from app import crud, models, scheduler


def _hace_dias(dias: int) -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=dias)


class TestIniciarScheduler:

    def test_registra_el_job_de_anonimizacion_con_un_cron_diario(self):
        sched = scheduler.iniciar_scheduler()
        try:
            job = sched.get_job(scheduler.ID_JOB_ANONIMIZACION)
            assert job is not None
            assert "cron" in type(job.trigger).__name__.lower()
        finally:
            sched.shutdown()

    def test_se_puede_apagar_sin_lanzar(self):
        sched = scheduler.iniciar_scheduler()
        sched.shutdown()  # no debe lanzar


class TestCorrerAnonimizacion:

    def test_anonimiza_usando_su_propia_sesion(self, seed, db_session, TestingSessionLocal, monkeypatch):
        monkeypatch.setattr(scheduler, "SessionLocal", TestingSessionLocal)
        solicitud = models.SolicitudContacto(
            nombre="Juan Pérez", rut="12345678-9", email="juan@prueba.cl", telefono="912345678",
            mensaje="Quiero formalizar mi emprendimiento", id_servicio=seed["servicio"].id_servicio,
            estado=crud.SOLICITUD_DESCARTADA, motivo_descarte="No respondió",
            fecha_cierre=crud.ahora_utc(), fecha_actualizacion=_hace_dias(210),
        )
        db_session.add(solicitud)
        db_session.commit()
        db_session.refresh(solicitud)

        scheduler._correr_anonimizacion()

        db_session.refresh(solicitud)
        assert solicitud.nombre is None
        assert solicitud.fecha_anonimizacion is not None

    def test_si_falla_no_lanza(self, TestingSessionLocal, monkeypatch):
        monkeypatch.setattr(scheduler, "SessionLocal", TestingSessionLocal)

        def revienta(db):
            raise RuntimeError("falla simulada")

        monkeypatch.setattr(scheduler, "anonimizar_solicitudes_vencidas", revienta)

        scheduler._correr_anonimizacion()  # no debe lanzar
