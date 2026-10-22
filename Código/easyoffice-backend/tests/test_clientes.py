"""Pruebas de GET /api/clientes (listado del panel) y GET /api/clientes/{id}
(ficha de cliente 360°) -- ambos requieren login."""
import pytest

from app import models

URL = "/api/clientes"


class TestAcceso:
    def test_sin_token_401(self, client):
        assert client.get(URL).status_code == 401

    def test_token_invalido_401(self, client):
        assert client.get(URL, headers={"Authorization": "Bearer basura"}).status_code == 401


class TestListado:
    def test_sin_clientes_lista_vacia(self, client, headers_agente):
        resp = client.get(URL, headers=headers_agente)
        assert resp.status_code == 200
        assert resp.json() == {"items": [], "total": 0}

    def test_cuenta_tramites_por_cliente(self, client, headers_agente, crear_solicitud, convertir):
        # Mismo RUT en dos solicitudes -> crud.py reutiliza el mismo cliente al convertir.
        sol1 = crear_solicitud(rut="11111111-1", nombre="Ana Cliente")
        sol2 = crear_solicitud(rut="11111111-1", nombre="Ana Cliente")
        sol3 = crear_solicitud(rut="22222222-2", nombre="Beto Cliente")

        assert convertir(sol1["id_solicitud"]).status_code == 200
        assert convertir(sol2["id_solicitud"]).status_code == 200
        assert convertir(sol3["id_solicitud"]).status_code == 200

        resp = client.get(URL, headers=headers_agente)
        assert resp.status_code == 200
        datos = resp.json()
        assert datos["total"] == 2

        por_rut = {item["rut"]: item["cantidad_tramites"] for item in datos["items"]}
        assert por_rut == {"11111111-1": 2, "22222222-2": 1}

    def test_filtro_por_nombre(self, client, headers_agente, crear_solicitud, convertir):
        sol = crear_solicitud(rut="33333333-3", nombre="Carola Única")
        convertir(sol["id_solicitud"])
        # Esta no se convierte -> nunca llega a generar un cliente.
        crear_solicitud(rut="44444444-4", nombre="Diego Otro")

        resp = client.get(URL, headers=headers_agente, params={"q": "Carola"})
        assert resp.status_code == 200
        datos = resp.json()
        assert datos["total"] == 1
        assert datos["items"][0]["nombre"] == "Carola Única"

    def test_filtro_por_rut(self, client, headers_agente, crear_solicitud, convertir):
        sol = crear_solicitud(rut="55555555-5", nombre="Elena Flores")
        convertir(sol["id_solicitud"])

        resp = client.get(URL, headers=headers_agente, params={"q": "55555555"})
        assert resp.status_code == 200
        datos = resp.json()
        assert datos["total"] == 1
        assert datos["items"][0]["rut"] == "55555555-5"

    def test_paginacion(self, client, headers_agente, crear_solicitud, convertir):
        for n in range(3):
            sol = crear_solicitud(rut=f"6000000{n}-{n}", nombre=f"Cliente {n}")
            convertir(sol["id_solicitud"])

        resp = client.get(URL, headers=headers_agente, params={"limit": 2, "offset": 0})
        datos = resp.json()
        assert datos["total"] == 3
        assert len(datos["items"]) == 2


@pytest.fixture()
def crear_empresa(db_session):
    def _crear(rut="76123456-0", razon_social="Comercial Prueba SpA", **datos):
        empresa = models.Empresa(rut_empresa=rut, razon_social=razon_social, datos=datos)
        db_session.add(empresa)
        db_session.commit()
        db_session.refresh(empresa)
        return empresa

    return _crear


class TestFicha360:
    def test_sin_token_401(self, client):
        assert client.get(f"{URL}/1").status_code == 401

    def test_cliente_inexistente_404(self, client, headers_agente):
        assert client.get(f"{URL}/9999", headers=headers_agente).status_code == 404

    def test_datos_empresas_y_tramites(self, client, headers_agente, crear_solicitud, convertir, crear_empresa, db_session):
        empresa = crear_empresa(razon_social="Panadería Demo SpA", giro="Alimentos")

        sol1 = crear_solicitud(rut="77777777-7", nombre="Flor Cliente", email="flor@demo.cl", telefono="+56911111111")
        resp1 = client.post(
            f"/api/solicitudes-contacto/{sol1['id_solicitud']}/convertir",
            json={"id_empresa": empresa.id_empresa},
            headers=headers_agente,
        )
        assert resp1.status_code == 200

        # Mismo RUT -> mismo cliente, segundo trámite sin empresa.
        sol2 = crear_solicitud(rut="77777777-7", nombre="Flor Cliente")
        resp2 = convertir(sol2["id_solicitud"])
        assert resp2.status_code == 200

        cliente = db_session.query(models.Cliente).filter_by(rut="77777777-7").one()

        resp = client.get(f"{URL}/{cliente.id_cliente}", headers=headers_agente)
        assert resp.status_code == 200
        datos = resp.json()

        assert datos["nombre"] == "Flor Cliente"
        assert datos["rut"] == "77777777-7"
        assert datos["email"] == "flor@demo.cl"
        assert datos["telefono"] == "+56911111111"

        assert len(datos["tramites"]) == 2
        assert all(t["estado_actual"] == "generado" for t in datos["tramites"])
        assert all(t["tiene_documento"] is False for t in datos["tramites"])

        assert len(datos["empresas"]) == 1
        assert datos["empresas"][0]["razon_social"] == "Panadería Demo SpA"
        assert datos["empresas"][0]["rut_empresa"] == empresa.rut_empresa
        assert datos["empresas"][0]["datos"] == {"giro": "Alimentos"}
