"""
Pruebas de GET /api/tramites (listado del panel) y GET /api/tramites/resumen (KPIs y opciones de filtros). Ambos requieren 
login: devuelven datos de clientes.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.seguridad import crear_access_token

URL = "/api/tramites"
URL_RESUMEN = "/api/tramites/resumen"


@pytest.fixture()
def auth(seed):
    """Header Bearer de la cuenta semilla (mismo token que entrega /api/auth/login)."""
    u = seed["usuario"]
    return {"Authorization": f"Bearer {crear_access_token(u.id_usuario, 'agente')}"}


@pytest.fixture()
def hacer_tramite(crear_solicitud, convertir, db_session):
    """Crea solicitud -> convierte -> devuelve el JSON del trámite. La conversión
    deja como responsable al usuario de la sesión; con agente=False se le quita
    (puede ocurrir más adelante, p. ej. al reasignar) para probar "Sin asignar"."""
    contador = {"n": 0}

    def _hacer(rut=None, nombre="Juan Pérez", agente=False, **overrides):
        contador["n"] += 1
        if rut is None:
            rut = f"{10000000 + contador['n']}-{contador['n'] % 10}"
        sol = crear_solicitud(rut=rut, nombre=nombre, **overrides)
        resp = convertir(sol["id_solicitud"])
        assert resp.status_code == 200, resp.text
        if not agente:
            db_session.get(models.Tramite, resp.json()["id_tramite"]).id_usuario_responsable = None
            db_session.commit()
        return resp.json()

    return _hacer


def _set_estado(db_session, id_tramite, estado):
    t = db_session.get(models.Tramite, id_tramite)
    t.estado_actual = estado
    db_session.commit()


class TestAcceso:

    @pytest.mark.parametrize("url", [URL, URL_RESUMEN])
    def test_sin_token_401(self, client, url):
        assert client.get(url).status_code == 401

    @pytest.mark.parametrize("url", [URL, URL_RESUMEN])
    def test_token_invalido_401(self, client, url):
        assert client.get(url, headers={"Authorization": "Bearer basura"}).status_code == 401

    def test_no_queda_publico_aunque_haya_tramites(self, client, hacer_tramite):
        hacer_tramite()
        assert client.get(URL).status_code == 401
        assert client.get(URL_RESUMEN).status_code == 401

    def test_seguimiento_publico_sigue_funcionando(self, client, hacer_tramite):
        codigo = hacer_tramite()["codigo_seguimiento"]
        assert client.get(f"{URL}/codigo/{codigo}").status_code == 200

    def test_resumen_no_se_confunde_con_codigo(self, client, auth):
        """'/resumen' tiene 7 letras: no debe entrar a la ruta de código."""
        assert client.get(URL_RESUMEN, headers=auth).status_code == 200


class TestListado:

    def test_sin_tramites(self, client, auth):
        resp = client.get(URL, headers=auth)
        assert resp.status_code == 200
        assert resp.json() == {"items": [], "total": 0}

    def test_forma_de_un_item(self, client, auth, hacer_tramite, seed):
        t = hacer_tramite(rut="12345678-9", nombre="Ana Soto", agente=True)
        fila = client.get(URL, headers=auth).json()["items"][0]
        assert fila["id_tramite"] == t["id_tramite"]
        assert fila["codigo_seguimiento"] == t["codigo_seguimiento"]
        assert fila["cliente"] == {
            "nombre": "Ana Soto", "rut": "12345678-9", "datos_pendientes": True}
        assert fila["id_servicio"] == seed["servicio"].id_servicio
        assert fila["nombre_servicio"] == "Constitución de Sociedad"
        assert fila["estado_actual"] == "generado"
        assert fila["id_usuario_responsable"] == seed["usuario"].id_usuario
        assert fila["nombre_agente"] == "Agente Prueba"
        assert fila["fecha_actualizacion"]

    def test_sin_agente_nombre_null(self, client, auth, hacer_tramite):
        hacer_tramite()
        fila = client.get(URL, headers=auth).json()["items"][0]
        assert fila["id_usuario_responsable"] is None
        assert fila["nombre_agente"] is None

    def test_no_expone_email_telefono_ni_mensaje(self, client, auth, hacer_tramite):
        hacer_tramite()
        fila = client.get(URL, headers=auth).json()["items"][0]
        texto = str(fila)
        for dato in ("juan@example.com", "+56912345678", "Quiero formalizar"):
            assert dato not in texto
        assert set(fila["cliente"]) == {"nombre", "rut", "datos_pendientes"}

    def test_orden_mas_recientes_primero(self, client, auth, hacer_tramite, db_session):
        t1 = hacer_tramite()
        t2 = hacer_tramite()
        t3 = hacer_tramite()
        base = datetime(2026, 1, 1, 12, 0, 0)
        for t, minutos in ((t1, 30), (t2, 0), (t3, 10)):
            fila = db_session.get(models.Tramite, t["id_tramite"])
            fila.fecha_actualizacion = base + timedelta(minutes=minutos)
        db_session.commit()
        ids = [f["id_tramite"] for f in client.get(URL, headers=auth).json()["items"]]
        assert ids == [t1["id_tramite"], t3["id_tramite"], t2["id_tramite"]]

    def test_cambiar_estado_actualiza_la_fecha(self, client, auth, hacer_tramite, db_session):
        t = hacer_tramite()
        fila = db_session.get(models.Tramite, t["id_tramite"])
        fila.fecha_actualizacion = datetime(2020, 1, 1)
        db_session.commit()
        _set_estado(db_session, t["id_tramite"], "firmado")
        actualizado = client.get(URL, headers=auth).json()["items"][0]["fecha_actualizacion"]
        assert not actualizado.startswith("2020")


class TestFiltros:

    def test_por_servicio(self, client, auth, hacer_tramite, seed):
        hacer_tramite()
        hacer_tramite(servicio_id=seed["servicio_inactivo"].id_servicio)
        resp = client.get(URL, headers=auth, params={
            "servicio_id": seed["servicio_inactivo"].id_servicio}).json()
        assert resp["total"] == 1
        assert resp["items"][0]["nombre_servicio"] == "Servicio descontinuado"

    def test_por_estado(self, client, auth, hacer_tramite, db_session):
        t1 = hacer_tramite()
        hacer_tramite()
        _set_estado(db_session, t1["id_tramite"], "firmado")
        resp = client.get(URL, headers=auth, params={"estado": "firmado"}).json()
        assert resp["total"] == 1
        assert resp["items"][0]["id_tramite"] == t1["id_tramite"]

    def test_por_agente(self, client, auth, hacer_tramite, seed):
        hacer_tramite(agente=True)
        hacer_tramite()
        resp = client.get(URL, headers=auth, params={
            "agente_id": seed["usuario"].id_usuario}).json()
        assert resp["total"] == 1

    def test_filtros_combinados(self, client, auth, hacer_tramite, db_session, seed):
        t1 = hacer_tramite(agente=True)
        t2 = hacer_tramite(agente=True)
        _set_estado(db_session, t1["id_tramite"], "firmado")
        resp = client.get(URL, headers=auth, params={
            "estado": "firmado", "agente_id": seed["usuario"].id_usuario,
            "servicio_id": seed["servicio"].id_servicio}).json()
        assert [f["id_tramite"] for f in resp["items"]] == [t1["id_tramite"]]
        assert t2["id_tramite"] not in [f["id_tramite"] for f in resp["items"]]

    def test_filtro_sin_resultados(self, client, auth, hacer_tramite):
        hacer_tramite()
        resp = client.get(URL, headers=auth, params={"estado": "entregado"}).json()
        assert resp == {"items": [], "total": 0}

    @pytest.mark.parametrize("params", [
        {"servicio_id": 0}, {"servicio_id": "abc"}, {"agente_id": 0},
        {"limit": 0}, {"limit": 101}, {"offset": -1}, {"estado": "x" * 31},
        {"q": "x" * 101},
    ])
    def test_parametros_invalidos_422(self, client, auth, params):
        assert client.get(URL, headers=auth, params=params).status_code == 422


class TestBusqueda:

    def test_por_nombre_parcial_sin_importar_mayusculas(self, client, auth, hacer_tramite):
        hacer_tramite(nombre="María Ríos Tapia")
        hacer_tramite(nombre="Pedro Gómez")
        resp = client.get(URL, headers=auth, params={"q": "TAPIA"}).json()
        assert resp["total"] == 1
        assert resp["items"][0]["cliente"]["nombre"] == "María Ríos Tapia"

    def test_los_acentos_no_se_normalizan(self, client, auth, hacer_tramite):
        """Límite conocido: "rios" no encuentra "Ríos". Se documenta, no se corrige."""
        hacer_tramite(nombre="María Ríos Tapia")
        assert client.get(URL, headers=auth, params={"q": "rios"}).json()["total"] == 0

    def test_por_rut_con_puntos_o_sin_ellos(self, client, auth, hacer_tramite):
        hacer_tramite(rut="12345678-9")
        hacer_tramite(rut="22222222-2")
        for q in ("12.345.678-9", "12345678-9", "12345678"):
            resp = client.get(URL, headers=auth, params={"q": q}).json()
            assert resp["total"] == 1, q

    def test_por_codigo(self, client, auth, hacer_tramite):
        t = hacer_tramite()
        hacer_tramite()
        resp = client.get(URL, headers=auth, params={
            "q": t["codigo_seguimiento"].lower()}).json()
        assert [f["id_tramite"] for f in resp["items"]] == [t["id_tramite"]]

    def test_busqueda_vacia_o_espacios_no_filtra(self, client, auth, hacer_tramite):
        hacer_tramite()
        hacer_tramite()
        for q in ("", "   "):
            assert client.get(URL, headers=auth, params={"q": q}).json()["total"] == 2

    @pytest.mark.parametrize("q", ["%", "_", "\\", "' OR 1=1 --"])
    def test_comodines_e_inyeccion_se_tratan_como_texto(self, client, auth, hacer_tramite, q):
        hacer_tramite()
        resp = client.get(URL, headers=auth, params={"q": q})
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_busqueda_combinada_con_filtro(self, client, auth, hacer_tramite, db_session):
        t1 = hacer_tramite(nombre="Ana Soto")
        hacer_tramite(nombre="Ana Pérez")
        _set_estado(db_session, t1["id_tramite"], "firmado")
        resp = client.get(URL, headers=auth, params={"q": "ana", "estado": "firmado"}).json()
        assert resp["total"] == 1


class TestPaginacion:

    def test_limit_y_offset_con_total(self, client, auth, hacer_tramite):
        for _ in range(5):
            hacer_tramite()
        p1 = client.get(URL, headers=auth, params={"limit": 2, "offset": 0}).json()
        p2 = client.get(URL, headers=auth, params={"limit": 2, "offset": 2}).json()
        p3 = client.get(URL, headers=auth, params={"limit": 2, "offset": 4}).json()
        assert p1["total"] == p2["total"] == p3["total"] == 5
        assert (len(p1["items"]), len(p2["items"]), len(p3["items"])) == (2, 2, 1)
        ids = [f["id_tramite"] for p in (p1, p2, p3) for f in p["items"]]
        assert len(set(ids)) == 5

    def test_offset_mas_alla_del_total(self, client, auth, hacer_tramite):
        hacer_tramite()
        resp = client.get(URL, headers=auth, params={"offset": 50}).json()
        assert resp == {"items": [], "total": 1}

    def test_limite_por_defecto_20(self, client, auth, hacer_tramite):
        for _ in range(21):
            hacer_tramite()
        resp = client.get(URL, headers=auth).json()
        assert len(resp["items"]) == 20 and resp["total"] == 21


class TestResumen:

    def test_vacio(self, client, auth):
        data = client.get(URL_RESUMEN, headers=auth).json()
        assert data["kpis"] == {
            "pendientes_datos": 0, "en_proceso": 0, "firmados_24h": 0, "entregados": 0}

    def test_agrupa_los_estados(self, client, auth, hacer_tramite, db_session):
        estados = ["generado", "generado", "procesando_firma", "en_revision",
                   "firmado", "entregado", "entregado"]
        for e in estados:
            t = hacer_tramite()
            _set_estado(db_session, t["id_tramite"], e)
        kpis = client.get(URL_RESUMEN, headers=auth).json()["kpis"]
        assert kpis["pendientes_datos"] == 2
        assert kpis["en_proceso"] == 2
        assert kpis["entregados"] == 2

    def test_firmados_24h_usa_el_historial(self, client, auth, hacer_tramite, db_session):
        ahora = datetime.now(timezone.utc).replace(tzinfo=None)
        reciente = hacer_tramite()
        antiguo = hacer_tramite()
        db_session.add_all([
            models.HistorialEstado(id_tramite=reciente["id_tramite"], estado="firmado",
                                   fecha=ahora - timedelta(hours=2)),
            # Dos registros del mismo trámite cuentan una sola vez.
            models.HistorialEstado(id_tramite=reciente["id_tramite"], estado="firmado",
                                   fecha=ahora - timedelta(hours=1)),
            models.HistorialEstado(id_tramite=antiguo["id_tramite"], estado="firmado",
                                   fecha=ahora - timedelta(hours=30)),
        ])
        db_session.commit()
        kpis = client.get(URL_RESUMEN, headers=auth).json()["kpis"]
        assert kpis["firmados_24h"] == 1

    def test_opciones_de_filtros(self, client, auth, seed, db_session):
        db_session.add(models.Usuario(
            nombre="Inactivo", email="x@easyoffice.cl", password_hash="x",
            id_rol=seed["usuario"].id_rol, activo=False))
        db_session.commit()
        data = client.get(URL_RESUMEN, headers=auth).json()
        # Solo servicios activos y usuarios activos.
        assert data["servicios"] == [{
            "id_servicio": seed["servicio"].id_servicio,
            "nombre": "Constitución de Sociedad"}]
        assert data["agentes"] == [{
            "id_usuario": seed["usuario"].id_usuario, "nombre": "Agente Prueba"}]

    def test_no_incluye_datos_de_clientes(self, client, auth, hacer_tramite):
        hacer_tramite()
        texto = str(client.get(URL_RESUMEN, headers=auth).json())
        for dato in ("Juan", "12345678", "juan@example.com"):
            assert dato not in texto