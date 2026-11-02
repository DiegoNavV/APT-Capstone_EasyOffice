"""
Tabla datos_empresa_tramite: registro del envío ÚNICO de datos que hace el cliente con su código. Aquí se prueban las garantías 
a nivel de base de datos (envío único, versión del consentimiento obligatoria). El endpoint público que escribe en esta tabla llega en una fase posterior.
"""
import pytest
from sqlalchemy.exc import IntegrityError

from app import models


@pytest.fixture()
def tramite(crear_solicitud, convertir, db_session):
    sol = crear_solicitud()
    resp = convertir(sol["id_solicitud"])
    assert resp.status_code == 200
    return db_session.get(models.Tramite, resp.json()["id_tramite"])


def _envio(id_tramite, **overrides):
    base = dict(
        id_tramite=id_tramite,
        solicitante_es_representante=False,
        version_consentimiento="2026-10",
    )
    base.update(overrides)
    return models.DatosEmpresaTramite(**base)


class TestDatosEmpresaTramite:
    def test_guarda_y_relee_el_envio(self, db_session, tramite):
        db_session.add(_envio(tramite.id_tramite))
        db_session.commit()
        db_session.expire_all()

        fila = db_session.get(models.Tramite, tramite.id_tramite).datos_empresa
        assert fila.solicitante_es_representante is False
        assert fila.version_consentimiento == "2026-10"
        assert fila.fecha_envio is not None

    def test_tramite_sin_envio_devuelve_none(self, tramite):
        assert tramite.datos_empresa is None

    def test_solo_un_envio_por_tramite(self, db_session, tramite):
        db_session.add(_envio(tramite.id_tramite))
        db_session.commit()
        db_session.add(_envio(tramite.id_tramite, solicitante_es_representante=True))
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_sin_version_de_consentimiento_no_se_guarda(self, db_session, tramite):
        db_session.add(_envio(tramite.id_tramite, version_consentimiento=None))
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_el_tramite_debe_existir(self, db_session, tramite):
        db_session.add(_envio(99999))
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_solicitante_es_representante_es_obligatorio(self, db_session, tramite):
        db_session.add(_envio(tramite.id_tramite, solicitante_es_representante=None))
        with pytest.raises(IntegrityError):
            db_session.commit()