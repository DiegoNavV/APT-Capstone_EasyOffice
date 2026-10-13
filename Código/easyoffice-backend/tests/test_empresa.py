"""
Tabla empresa: los datos de cada empresa cliente se guardan una sola vez y se reutilizan entre trámites. Se prueba el modelo 
y sus garantías en la base de datos; la lógica que vincula y completa datos llega en fases posteriores.
"""
import pytest
from sqlalchemy.exc import IntegrityError

from app import models


@pytest.fixture()
def crear_tramite(crear_solicitud, convertir, db_session):
    def _crear():
        sol = crear_solicitud()
        resp = convertir(sol["id_solicitud"])
        assert resp.status_code == 200
        return db_session.get(models.Tramite, resp.json()["id_tramite"])

    return _crear


def _empresa(**overrides):
    base = dict(
        rut_empresa="76123456-0",
        razon_social="Comercial Prueba SpA",
        datos={"giro_principal": "Venta de artículos de oficina", "email": "contacto@prueba.cl"},
    )
    base.update(overrides)
    return models.Empresa(**base)


class TestEmpresa:
    def test_guarda_y_relee_los_datos(self, db_session):
        db_session.add(_empresa())
        db_session.commit()
        db_session.expire_all()

        fila = db_session.query(models.Empresa).one()
        assert fila.razon_social == "Comercial Prueba SpA"
        assert fila.datos["giro_principal"] == "Venta de artículos de oficina"
        assert fila.fecha_creacion is not None
        assert fila.fecha_actualizacion is not None

    def test_datos_por_defecto_es_dict_vacio(self, db_session):
        db_session.add(models.Empresa(rut_empresa="76123456-0", razon_social="Comercial Prueba SpA"))
        db_session.commit()
        db_session.expire_all()
        assert db_session.query(models.Empresa).one().datos == {}

    def test_el_rut_no_se_puede_repetir(self, db_session):
        db_session.add(_empresa())
        db_session.commit()
        db_session.add(_empresa(razon_social="Otra razón social"))
        with pytest.raises(IntegrityError):
            db_session.commit()

    @pytest.mark.parametrize("campo", ["rut_empresa", "razon_social"])
    def test_campos_obligatorios(self, db_session, campo):
        db_session.add(_empresa(**{campo: None}))
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestVinculoConTramite:
    def test_tramite_nace_sin_empresa(self, crear_tramite):
        assert crear_tramite().empresa is None

    def test_un_tramite_se_vincula_a_una_empresa(self, db_session, crear_tramite):
        tramite = crear_tramite()
        empresa = _empresa()
        tramite.empresa = empresa
        db_session.commit()
        db_session.expire_all()

        assert db_session.get(models.Tramite, tramite.id_tramite).empresa.rut_empresa == "76123456-0"

    def test_dos_tramites_comparten_la_misma_empresa(self, db_session, crear_tramite):
        empresa = _empresa()
        db_session.add(empresa)
        db_session.commit()

        t1, t2 = crear_tramite(), crear_tramite()
        t1.id_empresa = empresa.id_empresa
        t2.id_empresa = empresa.id_empresa
        db_session.commit()
        db_session.expire_all()

        assert len(db_session.get(models.Empresa, empresa.id_empresa).tramites) == 2

    def test_la_empresa_del_tramite_debe_existir(self, db_session, crear_tramite):
        tramite = crear_tramite()
        tramite.id_empresa = 99999
        with pytest.raises(IntegrityError):
            db_session.commit()