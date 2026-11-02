"""
Pruebas de /api/solicitudes-contacto (creación y conversión a trámite).
"""
import re

import pytest

from app import crud, models

CODIGO_RE = re.compile(r"^[2-9A-HJKMNP-Z]{8}$")  # sin 0/O/1/I/L


# ===========================================================================
# 1. Crear solicitud de contacto
# ===========================================================================

class TestCrearSolicitud:

    def test_solicitud_valida_201(self, client, seed):
        payload = {
            "nombre": "Juan Pérez",
            "rut": "12345678-9",
            "email": "juan@example.com",
            "telefono": "+56912345678",
            "servicio_id": seed["servicio"].id_servicio,
            "mensaje": "Hola",
        }
        resp = client.post("/api/solicitudes-contacto", json=payload)

        assert resp.status_code == 201
        data = resp.json()
        assert isinstance(data["id_solicitud"], int)
        assert data["nombre"] == "Juan Pérez"
        assert data["rut"] == "12345678-9"
        assert data["email"] == "juan@example.com"
        assert data["telefono"] == "+56912345678"
        assert data["mensaje"] == "Hola"
        assert data["id_servicio"] == seed["servicio"].id_servicio
        assert data["estado"] == "pendiente"
        assert data["fecha_creacion"]  # server_default se llenó

    def test_solicitud_no_genera_tramite_ni_codigo(self, client, crear_solicitud, db_session):
        """Regla: al crear la solicitud NO se genera código todavía."""
        sol = crear_solicitud()
        assert "codigo_seguimiento" not in sol
        assert db_session.query(models.Tramite).count() == 0
        assert db_session.query(models.Cliente).count() == 0
        fila = db_session.get(models.SolicitudContacto, sol["id_solicitud"])
        assert fila.id_tramite_generado is None

    def test_estado_no_puede_inyectarse_desde_el_payload(self, client, seed, db_session):
        """Un cliente público no debería poder crear una solicitud ya 'convertida'."""
        resp = client.post("/api/solicitudes-contacto", json={
            "nombre": "Ana", "servicio_id": seed["servicio"].id_servicio, "rut": "11111111-1", "email": "a@b.cl",
            "estado": "convertida", "id_tramite_generado": 1,
        })
        assert resp.status_code == 201
        assert resp.json()["estado"] == "pendiente"

    @pytest.mark.parametrize("nombre", ["", "   ", "\t\n "])
    def test_nombre_vacio_o_espacios_422(self, client, nombre):
        resp = client.post("/api/solicitudes-contacto", json={"nombre": nombre})
        assert resp.status_code == 422

    def test_sin_nombre_422(self, client):
        resp = client.post("/api/solicitudes-contacto", json={"email": "a@b.cl"})
        assert resp.status_code == 422

    def test_nombre_null_422(self, client):
        resp = client.post("/api/solicitudes-contacto", json={"nombre": None})
        assert resp.status_code == 422

    def test_nombre_se_guarda_sin_espacios_extremos(self, client):
        resp = client.post("/api/solicitudes-contacto", json={"nombre": "  María  ", "rut": "11111111-1", "email": "a@b.cl"})
        assert resp.status_code == 201
        assert resp.json()["nombre"] == "María"

    @pytest.mark.parametrize("email", ["no-es-email", "a@", "@dominio.cl", "a b@c.cl", "a@@b.cl"])
    def test_email_mal_formado_422(self, client, email):
        resp = client.post("/api/solicitudes-contacto", json={"nombre": "X", "email": email})
        assert resp.status_code == 422

    def test_sin_servicio_permitido(self, client):
        resp = client.post("/api/solicitudes-contacto", json={"nombre": "Pedro", "servicio_id": None, "rut": "11111111-1", "email": "a@b.cl"})
        assert resp.status_code == 201
        assert resp.json()["id_servicio"] is None

    def test_minimo_nombre_rut_y_un_contacto(self, client):
        resp = client.post("/api/solicitudes-contacto", json={
            "nombre": "Pedro", "rut": "11111111-1", "telefono": "912345678"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] is None and data["id_servicio"] is None

    @pytest.mark.parametrize("rut", [None, "", "   "])
    def test_sin_rut_422(self, client, rut):
        """El RUN es obligatorio: identifica al cliente al convertir (cliente.run es obligatorio)."""
        payload = {"nombre": "Pedro", "email": "a@b.cl"}
        if rut is not None:
            payload["rut"] = rut
        assert client.post("/api/solicitudes-contacto", json=payload).status_code == 422

    @pytest.mark.parametrize("rut", ["1-1", "123-4", "12345678-X", "abcdefgh-1"])
    def test_rut_con_formato_invalido_422(self, client, rut):
        resp = client.post("/api/solicitudes-contacto", json={"nombre": "X", "rut": rut, "email": "a@b.cl"})
        assert resp.status_code == 422

    def test_sin_email_ni_telefono_422(self, client):
        resp = client.post("/api/solicitudes-contacto", json={"nombre": "Pedro", "rut": "11111111-1"})
        assert resp.status_code == 422

    def test_mensaje_mas_largo_que_500_422(self, client):
        resp = client.post("/api/solicitudes-contacto", json={
            "nombre": "Pedro", "rut": "11111111-1", "email": "a@b.cl", "mensaje": "x" * 501})
        assert resp.status_code == 422

    def test_servicio_id_no_numerico_422(self, client):
        resp = client.post("/api/solicitudes-contacto", json={"nombre": "X", "servicio_id": "abc"})
        assert resp.status_code == 422

    def test_body_vacio_422(self, client):
        resp = client.post("/api/solicitudes-contacto")
        assert resp.status_code == 422

    # ---- Hallazgos (ya corregidos) ----------------------------------------

    def test_servicio_inexistente_da_404(self, client):
        """FIX: servicio_id inexistente ahora se valida antes de crear la
        solicitud y responde 404, en vez de un 500 por IntegrityError."""
        resp = client.post("/api/solicitudes-contacto", json={"nombre": "X", "servicio_id": 99999, "rut": "11111111-1", "email": "a@b.cl"})
        assert resp.status_code == 404
        assert resp.json()["detail"] == "El servicio indicado no existe."

    def test_servicio_inactivo_es_aceptado_sin_validar(self, client, seed):
        """OBSERVACIÓN (no es regla de negocio explícita): se aceptan solicitudes
        para un servicio con activo=False. Si no debe ofrecerse, falta validarlo."""
        resp = client.post("/api/solicitudes-contacto", json={
            "nombre": "X", "servicio_id": seed["servicio_inactivo"].id_servicio, "rut": "11111111-1", "email": "a@b.cl"})
        assert resp.status_code == 201

    def test_campos_con_largo_maximo_rechazan_422(self, client):
        """FIX: el schema ahora limita largos (rut<=15, telefono<=15, nombre<=150)
        para que Pydantic rechace con 422 antes de llegar a Postgres."""
        resp = client.post("/api/solicitudes-contacto", json={
            "nombre": "N" * 300, "rut": "1" * 40, "telefono": "9" * 50})
        assert resp.status_code == 422

    def test_rut_demasiado_largo_422(self, client):
        resp = client.post("/api/solicitudes-contacto", json={"nombre": "X", "rut": "1" * 40})
        assert resp.status_code == 422


# ===========================================================================
# 2. Convertir solicitud en trámite
# ===========================================================================

class TestConvertirSolicitud:

    def test_conversion_valida_200(self, crear_solicitud, convertir, seed, db_session):
        sol = crear_solicitud()
        resp = convertir(sol["id_solicitud"])

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert CODIGO_RE.match(data["codigo_seguimiento"]), data["codigo_seguimiento"]
        assert len(data["codigo_seguimiento"]) == 8
        assert data["estado_actual"] == "esperando_datos"
        assert data["nombre_servicio"] == "Constitución de Sociedad"

        # Efectos en BD
        tramite = db_session.get(models.Tramite, data["id_tramite"])
        assert tramite.id_solicitud_origen == sol["id_solicitud"]
        assert tramite.id_servicio == seed["servicio"].id_servicio
        assert tramite.id_usuario_responsable == seed["usuario"].id_usuario

        solicitud = db_session.get(models.SolicitudContacto, sol["id_solicitud"])
        assert solicitud.estado == "convertida"
        assert solicitud.id_tramite_generado == tramite.id_tramite
        assert solicitud.fecha_cierre is not None

        cliente = db_session.get(models.Cliente, tramite.id_cliente)
        assert cliente.rut == "12345678-9"
        assert cliente.nombre == "Juan Pérez"
        assert cliente.email == "juan@example.com"

    def test_conversion_crea_historial_inicial(self, crear_solicitud, convertir, seed, db_session):
        sol = crear_solicitud()
        data = convertir(sol["id_solicitud"]).json()
        historial = db_session.query(models.HistorialEstado).filter_by(
            id_tramite=data["id_tramite"]).all()
        assert len(historial) == 1
        assert historial[0].estado == "esperando_datos"
        assert historial[0].origen == "agente"
        assert historial[0].id_usuario == seed["usuario"].id_usuario

    def test_el_responsable_es_siempre_quien_convierte(
            self, crear_solicitud, convertir, seed, db_session):
        sol = crear_solicitud()
        resp = convertir(sol["id_solicitud"])
        assert resp.status_code == 200
        tramite = db_session.get(models.Tramite, resp.json()["id_tramite"])
        assert tramite.id_usuario_responsable == seed["usuario"].id_usuario

    def test_doble_conversion_400(self, crear_solicitud, convertir, db_session):
        sol = crear_solicitud()
        assert convertir(sol["id_solicitud"]).status_code == 200

        resp = convertir(sol["id_solicitud"])
        assert resp.status_code == 400
        assert "ya fue convertida" in resp.json()["detail"]
        # No se creó un segundo trámite ni historial
        assert db_session.query(models.Tramite).count() == 1
        assert db_session.query(models.HistorialEstado).count() == 1

    def test_solicitud_inexistente_404(self, convertir):
        resp = convertir(999999)
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Solicitud no encontrada."

    @pytest.mark.parametrize("id_invalido", ["abc", "1.5"])
    def test_id_no_entero_422(self, client, headers_agente, id_invalido):
        resp = client.post(
            f"/api/solicitudes-contacto/{id_invalido}/convertir", headers=headers_agente)
        assert resp.status_code == 422

    def test_sin_servicio_400(self, crear_solicitud, convertir, db_session):
        sol = crear_solicitud(servicio_id=None)
        resp = convertir(sol["id_solicitud"])
        assert resp.status_code == 400
        assert "servicio" in resp.json()["detail"]
        # Nada quedó a medio crear
        assert db_session.query(models.Tramite).count() == 0
        assert db_session.query(models.Cliente).count() == 0
        assert db_session.get(models.SolicitudContacto, sol["id_solicitud"]).estado == "pendiente"

    def test_convertir_no_necesita_body(self, client, crear_solicitud, headers_agente):
        """Ya no se envía nada en el cuerpo: el responsable sale de la sesión."""
        sol = crear_solicitud()
        resp = client.post(
            f"/api/solicitudes-contacto/{sol['id_solicitud']}/convertir", headers=headers_agente)
        assert resp.status_code == 200

    # ---- Clientes / RUT -------------------------------------------------

    def test_mismo_rut_reutiliza_cliente(self, crear_solicitud, convertir, db_session):
        s1 = crear_solicitud(rut="11111111-1", nombre="Ana")
        s2 = crear_solicitud(rut="11111111-1", nombre="Ana Soto")
        t1 = convertir(s1["id_solicitud"]).json()
        t2 = convertir(s2["id_solicitud"]).json()

        tr1 = db_session.get(models.Tramite, t1["id_tramite"])
        tr2 = db_session.get(models.Tramite, t2["id_tramite"])
        assert tr1.id_cliente == tr2.id_cliente
        assert db_session.query(models.Cliente).count() == 1
        assert tr1.codigo_seguimiento != tr2.codigo_seguimiento

    def test_ruts_distintos_crean_clientes_distintos(self, crear_solicitud, convertir, db_session):
        convertir(crear_solicitud(rut="11111111-1")["id_solicitud"])
        convertir(crear_solicitud(rut="22222222-2")["id_solicitud"])
        assert db_session.query(models.Cliente).count() == 2

    def test_solicitud_sin_rut_no_se_convierte(self, crear_solicitud, convertir, db_session):
        """El formulario ya exige el RUN, pero una solicitud cargada por otra vía no lo tiene: sin RUN no
        se puede identificar al cliente, así que la conversión se rechaza sin crear nada."""
        sol = crear_solicitud()
        db_session.get(models.SolicitudContacto, sol["id_solicitud"]).rut = None
        db_session.commit()
        resp = convertir(sol["id_solicitud"])
        assert resp.status_code == 400
        assert "RUN" in resp.json()["detail"]
        assert db_session.query(models.Cliente).count() == 0
        assert db_session.query(models.Tramite).count() == 0

    def test_mismo_rut_con_distinto_formato_reutiliza_cliente(
            self, crear_solicitud, convertir, db_session):
        """FIX: el RUT se normaliza (sin puntos ni espacios, DV en mayúscula),
        así que estos tres formatos ahora son el mismo cliente."""
        convertir(crear_solicitud(rut="12.345.678-9")["id_solicitud"])
        convertir(crear_solicitud(rut="12345678-9")["id_solicitud"])
        convertir(crear_solicitud(rut="12345678-9 ")["id_solicitud"])
        assert db_session.query(models.Cliente).count() == 1

    def test_rut_k_mayuscula_minuscula_mismo_cliente(self, crear_solicitud, convertir, db_session):
        convertir(crear_solicitud(rut="7654321-k")["id_solicitud"])
        convertir(crear_solicitud(rut="7654321-K")["id_solicitud"])
        assert db_session.query(models.Cliente).count() == 1

    def test_cliente_reutilizado_no_actualiza_datos_de_contacto(
            self, crear_solicitud, convertir, db_session):
        """OBSERVACIÓN: si el cliente vuelve con email/teléfono nuevos, se
        reutiliza el registro pero sus datos de contacto quedan los ANTIGUOS.
        Puede ser intencional; conviene decidirlo explícitamente."""
        convertir(crear_solicitud(rut="33333333-3", email="viejo@x.cl")["id_solicitud"])
        convertir(crear_solicitud(rut="33333333-3", email="nuevo@x.cl")["id_solicitud"])
        cliente = db_session.query(models.Cliente).one()
        assert cliente.email == "viejo@x.cl"

    # ---- Usuario responsable ----------------------------------------------

    @pytest.mark.parametrize("id_enviado", [99999, 0, -1])
    def test_responsable_enviado_en_el_body_se_ignora(
            self, crear_solicitud, client, headers_agente, seed, db_session, id_enviado):
        """Nadie puede asignar el trámite a otro usuario (ni a uno inexistente)
        desde la petición: el responsable es el usuario de la sesión."""
        sol = crear_solicitud()
        resp = client.post(
            f"/api/solicitudes-contacto/{sol['id_solicitud']}/convertir",
            headers=headers_agente, json={"id_usuario_responsable": id_enviado})
        assert resp.status_code == 200, resp.text
        tramite = db_session.get(models.Tramite, resp.json()["id_tramite"])
        assert tramite.id_usuario_responsable == seed["usuario"].id_usuario

    def test_no_se_puede_asignar_a_otro_usuario_existente(
            self, crear_solicitud, client, headers_agente, seed, db_session):
        otro = models.Usuario(
            nombre="Otra Agente", email="otra@easyoffice.cl", password_hash="x",
            id_rol=seed["usuario"].id_rol)
        db_session.add(otro)
        db_session.commit()
        sol = crear_solicitud()
        resp = client.post(
            f"/api/solicitudes-contacto/{sol['id_solicitud']}/convertir",
            headers=headers_agente, json={"id_usuario_responsable": otro.id_usuario})
        tramite = db_session.get(models.Tramite, resp.json()["id_tramite"])
        assert tramite.id_usuario_responsable == seed["usuario"].id_usuario != otro.id_usuario

    # ---- Servicio de la solicitud ----------------------------------------

    def test_servicio_inactivo_igual_se_convierte(self, crear_solicitud, convertir, seed):
        """OBSERVACIÓN: no se valida ServicioContratado.activo al convertir."""
        sol = crear_solicitud(servicio_id=seed["servicio_inactivo"].id_servicio)
        resp = convertir(sol["id_solicitud"])
        assert resp.status_code == 200
        assert resp.json()["nombre_servicio"] == "Servicio descontinuado"

    def test_estado_distinto_de_pendiente_se_puede_convertir(
            self, crear_solicitud, convertir, db_session):
        """Solo se bloquea estado == 'convertida': una solicitud descartada todavía se puede convertir
        (si el cliente vuelve y paga). Al convertirla pierde el motivo de descarte."""
        sol = crear_solicitud()
        fila = db_session.get(models.SolicitudContacto, sol["id_solicitud"])
        fila.estado = "descartada"
        fila.motivo_descarte = "No respondió"
        # estado != 'pendiente' exige fecha_cierre (ck_solicitud_cierre).
        fila.fecha_cierre = crud.ahora_utc()
        db_session.commit()
        assert convertir(sol["id_solicitud"]).status_code == 200
        db_session.expire_all()
        fila = db_session.get(models.SolicitudContacto, sol["id_solicitud"])
        assert fila.estado == "convertida" and fila.motivo_descarte is None

    def test_estado_inconsistente_no_permite_segundo_tramite(
            self, crear_solicitud, convertir, db_session):
        """FIX (antes era un bug latente): aunque `estado` vuelva a 'pendiente' por error, la base no
        deja un segundo trámite para la misma solicitud (tramite.solicitud_contacto_id es único)."""
        sol = crear_solicitud()
        convertir(sol["id_solicitud"])
        fila = db_session.get(models.SolicitudContacto, sol["id_solicitud"])
        # Simula el estado corrupto completo (no solo "estado"): sin esto,
        # fecha_cierre no-nula con estado='pendiente' viola ck_solicitud_cierre.
        fila.estado = "pendiente"
        fila.fecha_cierre = None
        db_session.commit()
        resp = convertir(sol["id_solicitud"])
        assert resp.status_code == 400
        assert "ya fue convertida" in resp.json()["detail"]
        assert db_session.query(models.Tramite).count() == 1


# ===========================================================================
# 2b. Acceso a /convertir (requiere login)
# ===========================================================================

class TestConvertirAcceso:
    """/convertir confirma un pago y genera un código: solo para agentes/admins."""

    def _url(self, sol):
        return f"/api/solicitudes-contacto/{sol['id_solicitud']}/convertir"

    def test_sin_token_401_y_no_crea_nada(self, client, crear_solicitud, db_session):
        sol = crear_solicitud()
        assert client.post(self._url(sol)).status_code == 401
        assert db_session.query(models.Tramite).count() == 0
        assert db_session.query(models.Cliente).count() == 0
        assert db_session.get(
            models.SolicitudContacto, sol["id_solicitud"]).estado == "pendiente"

    def test_sin_token_aunque_mande_un_body_401(self, client, crear_solicitud):
        sol = crear_solicitud()
        resp = client.post(self._url(sol), json={"id_usuario_responsable": 1})
        assert resp.status_code == 401

    def test_token_invalido_401(self, client, crear_solicitud):
        sol = crear_solicitud()
        resp = client.post(self._url(sol), headers={"Authorization": "Bearer basura"})
        assert resp.status_code == 401

    def test_cuenta_desactivada_401(
            self, client, crear_solicitud, headers_agente, seed, db_session):
        sol = crear_solicitud()
        db_session.get(models.Usuario, seed["usuario"].id_usuario).activo = False
        db_session.commit()
        assert client.post(self._url(sol), headers=headers_agente).status_code == 401
        assert db_session.query(models.Tramite).count() == 0

    def test_sin_sesion_no_revela_si_la_solicitud_existe(self, client):
        """Sin login siempre 401: no se distingue una solicitud real de una inventada."""
        assert client.post("/api/solicitudes-contacto/999999/convertir").status_code == 401


# ===========================================================================
# 3. Generación de código (unitario sobre crud)
# ===========================================================================

class TestGeneracionCodigo:

    def test_formato_codigo(self, db_session, seed):
        for _ in range(200):
            assert CODIGO_RE.match(crud._generar_codigo_unico(db_session))

    def test_codigos_unicos_en_varias_conversiones(self, crear_solicitud, convertir):
        codigos = {
            convertir(crear_solicitud(rut=f"{10000000 + i}-{i % 10}")["id_solicitud"]).json()["codigo_seguimiento"]
            for i in range(30)
        }
        assert len(codigos) == 30

    def test_reintenta_si_hay_colision(self, crear_solicitud, convertir, db_session, monkeypatch):
        t1 = convertir(crear_solicitud(rut="11111111-1")["id_solicitud"]).json()
        existente = t1["codigo_seguimiento"]

        secuencia = iter([existente, "NUEVO234"])
        monkeypatch.setattr(crud, "_generar_codigo", lambda: next(secuencia))

        assert crud._generar_codigo_unico(db_session) == "NUEVO234"

    def test_agota_reintentos_lanza_runtime_error(self, crear_solicitud, convertir, db_session, monkeypatch):
        existente = convertir(crear_solicitud(rut="11111111-1")["id_solicitud"]).json()["codigo_seguimiento"]
        monkeypatch.setattr(crud, "_generar_codigo", lambda: existente)
        with pytest.raises(RuntimeError):
            crud._generar_codigo_unico(db_session)

    def test_agotar_reintentos_en_endpoint_da_500(
            self, crear_solicitud, convertir, client_500, headers_agente, monkeypatch, db_session):
        """El router captura RuntimeError y responde 500 con detalle (en vez de
        un 500 genérico sin mensaje). Además el cliente ya fue flusheado →
        verificamos que no quede huérfano (no hay commit)."""
        existente = convertir(crear_solicitud(rut="11111111-1")["id_solicitud"]).json()["codigo_seguimiento"]
        sol = crear_solicitud(rut="22222222-2")
        monkeypatch.setattr(crud, "_generar_codigo", lambda: existente)
        resp = client_500.post(
            f"/api/solicitudes-contacto/{sol['id_solicitud']}/convertir", headers=headers_agente)
        assert resp.status_code == 500
        assert db_session.query(models.Cliente).filter_by(rut="22222222-2").count() == 0

    def test_unique_en_bd_protege_aunque_falle_el_chequeo(self, db_session, seed):
        """La restricción UNIQUE es la red de seguridad real (p. ej. ante dos
        conversiones concurrentes que generen el mismo código)."""
        from sqlalchemy.exc import IntegrityError
        cli = models.Cliente(nombre="X", rut="11111111-1", email="x@x.cl")
        solicitudes = [models.SolicitudContacto(nombre="X", rut="11111111-1", email="x@x.cl") for _ in range(2)]
        db_session.add_all([cli, *solicitudes])
        db_session.flush()
        for sol in solicitudes:
            db_session.add(models.Tramite(
                id_cliente=cli.id_cliente, id_servicio=seed["servicio"].id_servicio,
                id_usuario_responsable=seed["usuario"].id_usuario, id_solicitud_origen=sol.id_solicitud,
                codigo_seguimiento="AAAA1111"))
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_codigo_usa_secrets_no_random(self):
        """El código es la ÚNICA credencial del cliente para ver su trámite:
        debe salir de un generador criptográfico (`secrets`), no de `random`."""
        import inspect
        fuente = inspect.getsource(crud._generar_codigo)
        assert "secrets.choice" in fuente and "random" not in fuente

    def test_alfabeto_sin_caracteres_ambiguos(self):
        assert len(crud.ALFABETO_CODIGO) == 31
        assert len(set(crud.ALFABETO_CODIGO)) == 31
        for c in "01OIL":
            assert c not in crud.ALFABETO_CODIGO

    def test_codigos_generados_solo_usan_el_alfabeto(self):
        permitidos = set(crud.ALFABETO_CODIGO)
        for _ in range(2000):
            codigo = crud._generar_codigo()
            assert len(codigo) == crud.LARGO_CODIGO == 8
            assert set(codigo) <= permitidos