"""
Catálogos para armar el contrato: sucursales y servicios que vende Easy Office, más las columnas nuevas del trámite 
(folio, sucursal y condiciones).
"""
import pytest
from sqlalchemy.exc import IntegrityError

from app import models


@pytest.fixture()
def crear_sucursal(db_session):
    def _crear(iniciales="LF", nombre="La Florida", **extra):
        datos = {
            "direccion": "Vicuña Mackenna Poniente #7255, Oficina 707",
            "comuna": "La Florida",
            "region": "Metropolitana",
            "rol_propiedad": "271-147",
        }
        datos.update(extra)
        sucursal = models.Sucursal(iniciales=iniciales, nombre=nombre, **datos)
        db_session.add(sucursal)
        db_session.commit()
        db_session.refresh(sucursal)
        return sucursal

    return _crear


@pytest.fixture()
def crear_servicio_ofrecido(db_session):
    def _crear(nombre="Domicilio tributario", **extra):
        datos = {"descripcion": "*Domicilio tributario", "precio_referencia": 59990, "ciclo_pago_defecto": "ANUAL"}
        datos.update(extra)
        servicio = models.ServicioOfrecido(nombre=nombre, **datos)
        db_session.add(servicio)
        db_session.commit()
        db_session.refresh(servicio)
        return servicio

    return _crear


class TestSucursales:
    URL = "/api/sucursales"

    def test_exige_login(self, client):
        assert client.get(self.URL).status_code == 401

    def test_lista_las_activas_ordenadas_por_nombre(self, client, headers_agente, crear_sucursal):
        crear_sucursal(iniciales="VL", nombre="Valparaíso")
        crear_sucursal(iniciales="LF", nombre="La Florida")
        crear_sucursal(iniciales="XX", nombre="Cerrada", activa=False)

        resp = client.get(self.URL, headers=headers_agente)

        assert resp.status_code == 200
        assert [s["iniciales"] for s in resp.json()] == ["LF", "VL"]

    def test_entrega_los_datos_que_van_en_el_contrato(self, client, headers_agente, crear_sucursal):
        crear_sucursal()

        sucursal = client.get(self.URL, headers=headers_agente).json()[0]

        assert sucursal == {
            "id_sucursal": sucursal["id_sucursal"],
            "iniciales": "LF",
            "nombre": "La Florida",
            "direccion": "Vicuña Mackenna Poniente #7255, Oficina 707",
            "comuna": "La Florida",
            "region": "Metropolitana",
            "rol_propiedad": "271-147",
        }

    def test_la_sucursal_sin_rol_de_propiedad_sale_con_null(self, client, headers_agente, crear_sucursal):
        crear_sucursal(rol_propiedad=None)

        assert client.get(self.URL, headers=headers_agente).json()[0]["rol_propiedad"] is None

    def test_sin_sucursales_devuelve_lista_vacia(self, client, headers_agente):
        assert client.get(self.URL, headers=headers_agente).json() == []

    def test_las_iniciales_son_unicas(self, crear_sucursal):
        crear_sucursal(iniciales="LF")
        with pytest.raises(IntegrityError):
            crear_sucursal(iniciales="LF", nombre="Otra")


class TestServiciosOfrecidos:
    URL = "/api/servicios-ofrecidos"

    def test_exige_login(self, client):
        assert client.get(self.URL).status_code == 401

    def test_lista_los_activos_ordenados_por_nombre(self, client, headers_agente, crear_servicio_ofrecido):
        crear_servicio_ofrecido(nombre="Web mail + dominio", precio_referencia=14990)
        crear_servicio_ofrecido(nombre="Bodega", precio_referencia=71388)
        crear_servicio_ofrecido(nombre="Antiguo", activo=False)

        resp = client.get(self.URL, headers=headers_agente)

        assert resp.status_code == 200
        assert [s["nombre"] for s in resp.json()] == ["Bodega", "Web mail + dominio"]

    def test_entrega_precio_y_ciclo_de_referencia(self, client, headers_agente, crear_servicio_ofrecido):
        crear_servicio_ofrecido()

        servicio = client.get(self.URL, headers=headers_agente).json()[0]

        assert servicio == {
            "id_servicio_ofrecido": servicio["id_servicio_ofrecido"],
            "nombre": "Domicilio tributario",
            "descripcion": "*Domicilio tributario",
            "precio_referencia": 59990,
            "ciclo_pago_defecto": "ANUAL",
        }

    def test_un_servicio_sin_precio_ni_ciclo_sale_con_null(self, client, headers_agente, crear_servicio_ofrecido):
        crear_servicio_ofrecido(
            nombre="Contabilidad", descripcion=None, precio_referencia=None, ciclo_pago_defecto=None
        )

        servicio = client.get(self.URL, headers=headers_agente).json()[0]

        assert servicio["precio_referencia"] is None
        assert servicio["ciclo_pago_defecto"] is None

    def test_el_nombre_es_unico(self, crear_servicio_ofrecido):
        crear_servicio_ofrecido(nombre="Bodega")
        with pytest.raises(IntegrityError):
            crear_servicio_ofrecido(nombre="Bodega")


class TestColumnasNuevasDelTramite:
    @pytest.fixture()
    def tramite(self, crear_solicitud, convertir, db_session):
        resp = convertir(crear_solicitud()["id_solicitud"])
        assert resp.status_code == 200
        return db_session.get(models.Tramite, resp.json()["id_tramite"])

    def test_un_tramite_nuevo_parte_sin_folio_sucursal_ni_condiciones(self, tramite):
        assert tramite.folio is None
        assert tramite.id_sucursal is None
        assert tramite.condiciones is None
        assert tramite.sucursal is None

    def test_guarda_sucursal_folio_y_condiciones(self, tramite, crear_sucursal, db_session):
        sucursal = crear_sucursal()
        condiciones = {
            "servicios": [{"nombre": "Domicilio tributario", "precio": 59990, "ciclo_pago": "ANUAL"}],
            "duracion_meses": 12,
            "fecha_inicio": "2026-01-15",
            "fecha_vencimiento": "2027-01-14",
        }

        tramite.id_sucursal = sucursal.id_sucursal
        tramite.folio = "LF-01-2026"
        tramite.condiciones = condiciones
        db_session.commit()
        db_session.refresh(tramite)

        assert tramite.sucursal.iniciales == "LF"
        assert tramite.folio == "LF-01-2026"
        assert tramite.condiciones == condiciones

    def test_el_folio_no_se_repite(self, tramite, crear_solicitud, convertir, db_session):
        otro = db_session.get(models.Tramite, convertir(crear_solicitud()["id_solicitud"]).json()["id_tramite"])
        tramite.folio = "LF-01-2026"
        db_session.commit()

        otro.folio = "LF-01-2026"
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_la_sucursal_debe_existir(self, tramite, db_session):
        tramite.id_sucursal = 9999
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()