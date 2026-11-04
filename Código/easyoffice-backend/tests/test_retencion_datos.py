"""
Pruebas de app.retencion_datos (anonimización de solicitudes descartadas, Ley 21.719).

Las solicitudes se crean directo en la base (como test_solicitudes.py::
test_unique_en_bd_protege_aunque_falle_el_chequeo), no vía /descartar: la tabla tiene un
trigger (trg_solicitud_fecha_actualizacion, ver db/init/02_funciones.sql) que fuerza
fecha_actualizacion = now() en CUALQUIER UPDATE, así que no hay forma de "envejecer" una
fila ya creada. Insertándola directamente con fecha_actualizacion ya vieja se evita el
trigger (solo dispara en UPDATE, no en INSERT) y se simula el caso real: una solicitud
que nadie volvió a tocar.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app import crud, models
from app.retencion_datos import anonimizar_solicitudes_vencidas

CAMPOS_PERSONALES = ("nombre", "rut", "email", "telefono", "mensaje")


def _hace_dias(dias: int) -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=dias)


def _crear_solicitud(db_session, seed, *, estado: str, fecha_actualizacion: datetime, **overrides):
    campos = dict(
        nombre="Juan Pérez",
        rut="12345678-9",
        email="juan@prueba.cl",
        telefono="912345678",
        mensaje="Quiero formalizar mi emprendimiento",
        id_servicio=seed["servicio"].id_servicio,
        estado=estado,
        fecha_actualizacion=fecha_actualizacion,
    )
    if estado != crud.SOLICITUD_PENDIENTE:
        campos["fecha_cierre"] = crud.ahora_utc()
    if estado == crud.SOLICITUD_DESCARTADA:
        campos["motivo_descarte"] = "No respondió"
    campos.update(overrides)
    solicitud = models.SolicitudContacto(**campos)
    db_session.add(solicitud)
    db_session.commit()
    db_session.refresh(solicitud)
    return solicitud


class TestAnonimizarSolicitudesVencidas:

    def test_anonimiza_la_descartada_vencida(self, seed, db_session):
        solicitud = _crear_solicitud(
            db_session, seed, estado=crud.SOLICITUD_DESCARTADA, fecha_actualizacion=_hace_dias(210))

        total = anonimizar_solicitudes_vencidas(db_session)

        assert total == 1
        db_session.refresh(solicitud)
        for campo in CAMPOS_PERSONALES:
            assert getattr(solicitud, campo) is None
        assert solicitud.estado == crud.SOLICITUD_DESCARTADA
        assert solicitud.fecha_anonimizacion is not None
        assert solicitud.motivo_descarte == "No respondió"  # no es un dato personal, se conserva

    def test_no_anonimiza_si_no_ha_pasado_el_plazo(self, seed, db_session):
        solicitud = _crear_solicitud(
            db_session, seed, estado=crud.SOLICITUD_DESCARTADA, fecha_actualizacion=_hace_dias(30))

        total = anonimizar_solicitudes_vencidas(db_session)

        assert total == 0
        db_session.refresh(solicitud)
        assert solicitud.nombre is not None
        assert solicitud.fecha_anonimizacion is None

    @pytest.mark.parametrize("estado", [crud.SOLICITUD_PENDIENTE, crud.SOLICITUD_CONVERTIDA])
    def test_no_anonimiza_pendientes_ni_convertidas_aunque_sean_viejas(self, seed, db_session, estado):
        solicitud = _crear_solicitud(db_session, seed, estado=estado, fecha_actualizacion=_hace_dias(365))

        total = anonimizar_solicitudes_vencidas(db_session)

        assert total == 0
        db_session.refresh(solicitud)
        assert solicitud.nombre is not None
        assert solicitud.fecha_anonimizacion is None

    def test_es_idempotente_no_vuelve_a_tocar_lo_ya_anonimizado(self, seed, db_session):
        solicitud = _crear_solicitud(
            db_session, seed, estado=crud.SOLICITUD_DESCARTADA, fecha_actualizacion=_hace_dias(210))
        assert anonimizar_solicitudes_vencidas(db_session) == 1
        db_session.refresh(solicitud)
        fecha_anonimizacion_original = solicitud.fecha_anonimizacion

        total_segunda_corrida = anonimizar_solicitudes_vencidas(db_session)

        assert total_segunda_corrida == 0
        db_session.refresh(solicitud)
        assert solicitud.fecha_anonimizacion == fecha_anonimizacion_original

    def test_respeta_el_plazo_personalizado(self, seed, db_session):
        solicitud = _crear_solicitud(
            db_session, seed, estado=crud.SOLICITUD_DESCARTADA, fecha_actualizacion=_hace_dias(60))

        assert anonimizar_solicitudes_vencidas(db_session, meses=3) == 0
        assert anonimizar_solicitudes_vencidas(db_session, meses=1) == 1
        db_session.refresh(solicitud)
        assert solicitud.fecha_anonimizacion is not None

    def test_varias_vencidas_se_anonimizan_juntas(self, seed, db_session):
        for i in range(3):
            _crear_solicitud(
                db_session, seed, estado=crud.SOLICITUD_DESCARTADA, fecha_actualizacion=_hace_dias(210),
                rut=f"{10000000 + i}-1", email=f"x{i}@prueba.cl",
            )

        assert anonimizar_solicitudes_vencidas(db_session) == 3
