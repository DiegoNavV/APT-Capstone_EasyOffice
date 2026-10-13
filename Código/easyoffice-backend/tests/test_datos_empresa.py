"""
Tabla datos_empresa_tramite: datos de la empresa que el cliente entrega una sola vez con su código. Aquí se prueba el modelo 
y sus garantías a nivel de base de datos (envío único, consentimiento obligatorio). El endpoint públicoque escribe en esta 
tabla llega en la parte 2.
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


def _datos(id_tramite, **overrides):
    base = dict(
        id_tramite=id_tramite,
        razon_social="Comercial Prueba SpA",
        rut_empresa="76.123.456-7",
        datos={"Giro": "Venta de articulos de oficina", "Comuna": "San Bernardo"},
        solicitante_es_representante=False,
        consentimiento_aceptado=True,
    )
    base.update(overrides)
    return models.DatosEmpresaTramite(**base)


class TestDatosEmpresaTramite:
    def test_guarda_y_relee_los_datos(self, db_session, tramite):
        db_session.add(_datos(tramite.id_tramite))
        db_session.commit()
        db_session.expire_all()

        fila = db_session.get(models.Tramite, tramite.id_tramite).datos_empresa
        assert fila.razon_social == "Comercial Prueba SpA"
        assert fila.rut_empresa == "76.123.456-7"
        assert fila.datos["Giro"] == "Venta de articulos de oficina"
        assert fila.solicitante_es_representante is False
        assert fila.fecha_envio is not None

    def test_tramite_sin_datos_devuelve_none(self, tramite):
        assert tramite.datos_empresa is None

    def test_datos_por_defecto_es_dict_vacio(self, db_session, tramite):
        fila = models.DatosEmpresaTramite(
            id_tramite=tramite.id_tramite,
            razon_social="Comercial Prueba SpA",
            rut_empresa="76.123.456-7",
            solicitante_es_representante=True,
            consentimiento_aceptado=True,
        )
        db_session.add(fila)
        db_session.commit()
        db_session.expire_all()
        assert db_session.get(models.Tramite, tramite.id_tramite).datos_empresa.datos == {}

    def test_solo_un_envio_por_tramite(self, db_session, tramite):
        db_session.add(_datos(tramite.id_tramite))
        db_session.commit()
        db_session.add(_datos(tramite.id_tramite, razon_social="Otra SpA"))
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_sin_consentimiento_no_se_guarda(self, db_session, tramite):
        db_session.add(_datos(tramite.id_tramite, consentimiento_aceptado=False))
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_el_tramite_debe_existir(self, db_session, tramite):
        db_session.add(_datos(99999))
        with pytest.raises(IntegrityError):
            db_session.commit()

    @pytest.mark.parametrize("campo", ["razon_social", "rut_empresa", "solicitante_es_representante"])
    def test_campos_obligatorios(self, db_session, tramite, campo):
        db_session.add(_datos(tramite.id_tramite, **{campo: None}))
        with pytest.raises(IntegrityError):
            db_session.commit()