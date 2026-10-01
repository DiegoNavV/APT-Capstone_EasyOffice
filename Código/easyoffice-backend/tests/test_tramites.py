"""
Pruebas de /api/tramites/codigo/{codigo} (consulta pública de seguimiento)
y de crud.documento_disponible.
"""
import pytest

from app import crud, models


@pytest.fixture()
def tramite_generado(crear_solicitud, convertir, seed):
    """Crea solicitud → la convierte → devuelve el JSON del trámite."""
    sol = crear_solicitud()
    resp = convertir(sol["id_solicitud"], seed["usuario"].id_usuario)
    assert resp.status_code == 200
    return resp.json()


def _set_estado(db_session, id_tramite, estado):
    t = db_session.get(models.Tramite, id_tramite)
    t.estado_actual = estado
    db_session.commit()


# ===========================================================================
# 1. Consulta por código
# ===========================================================================

class TestConsultaPorCodigo:

    def test_codigo_valido_200(self, client, tramite_generado):
        codigo = tramite_generado["codigo_seguimiento"]
        resp = client.get(f"/api/tramites/codigo/{codigo}")
        assert resp.status_code == 200
        assert resp.json() == {
            "codigo_seguimiento": codigo,
            "nombre_servicio": "Constitución de Sociedad",
            "estado_actual": "generado",
            "documento_disponible": False,
        }

    def test_respuesta_publica_no_expone_datos_personales(self, client, tramite_generado):
        """Endpoint sin login: no debe filtrar RUT, email, teléfono ni IDs internos."""
        data = client.get(f"/api/tramites/codigo/{tramite_generado['codigo_seguimiento']}").json()
        assert set(data) == {"codigo_seguimiento", "nombre_servicio",
                             "estado_actual", "documento_disponible"}
        texto = str(data)
        for dato in ("12345678-9", "juan@example.com", "+56912345678", "Juan"):
            assert dato not in texto

    def test_codigo_en_minusculas_funciona(self, client, tramite_generado):
        codigo = tramite_generado["codigo_seguimiento"]
        resp = client.get(f"/api/tramites/codigo/{codigo.lower()}")
        assert resp.status_code == 200
        assert resp.json()["codigo_seguimiento"] == codigo

    def test_codigo_con_espacios_alrededor_funciona(self, client, tramite_generado):
        """El cliente copia el código desde WhatsApp con un espacio de más."""
        codigo = tramite_generado["codigo_seguimiento"]
        resp = client.get(f"/api/tramites/codigo/%20{codigo}%20")
        assert resp.status_code == 200

    def test_codigo_inexistente_404(self, client, tramite_generado):
        otro = "ZZZZ9999" if tramite_generado["codigo_seguimiento"] != "ZZZZ9999" else "YYYY8888"
        resp = client.get(f"/api/tramites/codigo/{otro}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "No encontramos un trámite con ese código."

    def test_codigo_inexistente_con_bd_vacia_404(self, client):
        assert client.get("/api/tramites/codigo/ABCD1234").status_code == 404

    @pytest.mark.parametrize("codigo", ["A", "ABC", "ABCD123", "ABCD12345", "A" * 50, "%20%20%20"])
    def test_largo_distinto_de_8_400(self, client, codigo):
        resp = client.get(f"/api/tramites/codigo/{codigo}")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "El código debe tener 8 caracteres."

    @pytest.mark.parametrize("codigo", ["ABC", "ABCDEFGHIJ"])
    def test_largo_invalido_no_toca_la_bd(self, client, monkeypatch, codigo):
        """Regla: el 400 por largo ocurre ANTES de consultar la base de datos."""
        def _no_deberia_llamarse(*a, **k):
            raise AssertionError("Se consultó la BD con un código de largo inválido")
        monkeypatch.setattr(crud, "obtener_tramite_por_codigo", _no_deberia_llamarse)
        assert client.get(f"/api/tramites/codigo/{codigo}").status_code == 400

    @pytest.mark.parametrize("codigo", ["ABCD-123", "ABCD 123", "ÑÑÑÑÑÑÑÑ", "' OR 1=1"])
    def test_8_caracteres_no_alfanumericos_404_sin_error(self, client, codigo):
        """Largo 8 pero formato imposible: responde 404 (no 500). Intentos de
        inyección SQL quedan neutralizados por el ORM.
        OBSERVACIÓN: se podría rechazar con 400 validando ^[A-Z0-9]{8}$ y
        ahorrarse la consulta."""
        assert client.get(f"/api/tramites/codigo/{codigo}").status_code == 404

    def test_codigo_con_slash_no_llega_al_handler(self, client):
        """'ABCD/123' no matchea la ruta → 404 genérico de FastAPI ('Not Found'),
        no el mensaje propio. Comportamiento aceptable, solo se documenta."""
        resp = client.get("/api/tramites/codigo/ABCD/123")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Not Found"

    def test_ruta_sin_codigo_404(self, client):
        assert client.get("/api/tramites/codigo/").status_code == 404

    def test_codigos_de_distintos_tramites_no_se_cruzan(
            self, client, crear_solicitud, convertir, seed):
        s1 = crear_solicitud(rut="1-1")
        s2 = crear_solicitud(rut="2-2", servicio_id=seed["servicio_inactivo"].id_servicio)
        c1 = convertir(s1["id_solicitud"]).json()["codigo_seguimiento"]
        c2 = convertir(s2["id_solicitud"]).json()["codigo_seguimiento"]
        assert client.get(f"/api/tramites/codigo/{c1}").json()["nombre_servicio"] == "Constitución de Sociedad"
        assert client.get(f"/api/tramites/codigo/{c2}").json()["nombre_servicio"] == "Servicio descontinuado"

    @pytest.mark.parametrize("estado,esperado", [
        ("generado", False), ("procesando_firma", False), ("en_revision", False),
        ("firmado", True), ("entregado", True),
    ])
    def test_documento_disponible_via_endpoint(
            self, client, db_session, tramite_generado, estado, esperado):
        _set_estado(db_session, tramite_generado["id_tramite"], estado)
        data = client.get(f"/api/tramites/codigo/{tramite_generado['codigo_seguimiento']}").json()
        assert data["estado_actual"] == estado
        assert data["documento_disponible"] is esperado


# ===========================================================================
# 2. crud.documento_disponible (unitario, con Tramite en memoria)
# ===========================================================================

class TestDocumentoDisponible:

    @pytest.mark.parametrize("estado", ["firmado", "entregado"])
    def test_true_en_estados_finales(self, estado):
        assert crud.documento_disponible(models.Tramite(estado_actual=estado)) is True

    @pytest.mark.parametrize("estado", ["generado", "procesando_firma", "en_revision", "", None, "otro"])
    def test_false_en_otros_estados(self, estado):
        assert crud.documento_disponible(models.Tramite(estado_actual=estado)) is False

    @pytest.mark.parametrize("estado", ["FIRMADO", "Entregado", " firmado", "firmado "])
    def test_estados_con_otra_capitalizacion_o_espacios_dan_false(self, estado):
        """OBSERVACIÓN: los estados son strings libres (no hay Enum ni CHECK en
        BD). Un 'Firmado' cargado a mano o con un typo haría que el cliente
        NUNCA vea su documento disponible, sin ningún error visible."""
        assert crud.documento_disponible(models.Tramite(estado_actual=estado)) is False

    def test_conjunto_de_estados_exacto(self):
        """Fija la regla de negocio: si alguien agrega un estado al set por
        error, este test lo detecta."""
        assert crud.ESTADOS_DOCUMENTO_DISPONIBLE == {"firmado", "entregado"}


# ===========================================================================
# 3. Infraestructura básica
# ===========================================================================

class TestInfra:

    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_cors_origen_permitido(self, client):
        resp = client.options("/api/health", headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET"})
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"

    def test_cors_origen_no_permitido(self, client):
        resp = client.options("/api/health", headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "GET"})
        assert "access-control-allow-origin" not in resp.headers

    def test_endpoint_convertir_no_tiene_autenticacion(self, crear_solicitud, client):
        """OBSERVACIÓN IMPORTANTE: /convertir es una acción de agente interno
        (confirma un pago), pero hoy cualquiera sin login puede llamarla y
        generar trámites + códigos. Seguramente la auth está pendiente; este
        test fallará (bien) cuando se agregue, recordándote actualizarlo."""
        sol = crear_solicitud()
        resp = client.post(f"/api/solicitudes-contacto/{sol['id_solicitud']}/convertir", json={})
        assert resp.status_code == 200

    def test_drop_all_falla_por_fk_circular(self, tramite_generado, engine):
        """HALLAZGO: solicitud_contacto.id_tramite_generado -> tramite y
        tramite.id_solicitud_origen -> solicitud_contacto forman un ciclo.
        SQLAlchemy avisa 'Can't sort tables for DROP' y, con datos y FK
        activas, drop_all revienta. Solución: use_alter=True en una de las
        dos ForeignKey (o manejar el esquema con Alembic)."""
        import warnings
        from sqlalchemy.exc import IntegrityError
        from app.database import Base
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with pytest.raises(IntegrityError):
                Base.metadata.drop_all(bind=engine)