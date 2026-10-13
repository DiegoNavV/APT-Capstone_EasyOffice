"""
Envío de datos del cliente (escritura): con su código el cliente entrega UNA sola vez los datos que faltan. Es público, así 
que se prueba lo que debe rechazarse (segundo envío, campos ya registrados, RUT ajeno, falta de confirmaciones) y que un rechazo 
nunca deje datos a medias.
"""
import pytest

from app import crud, models, schemas
from app.seguridad import limiter

CONTRATO = "Contrato de servicio"
AUTORIZACION = "Autorización de domicilio tributario"

CAMPOS_CONTRATO = {
    "razon_social": "Comercial Prueba SpA",
    "rut_empresa": "76.123.456-0",
    "representante_legal": "Ana Soto Pérez",
    "rut_representante": "11.222.333-9",
    "domicilio_representante": "Av. Siempre Viva 742",
    "comuna_representante": "Providencia",
    "region_representante": "Metropolitana",
    "giro_principal": "Venta de artículos de oficina",
    "email": "Ana@Prueba.cl",
    "celular": "9 1234 5678",
    "fecha_escritura": "2020-05-15",
    "notaria": "Notaría 5",
}
CAMPOS_AUTORIZACION = {
    k: CAMPOS_CONTRATO[k]
    for k in ("razon_social", "rut_empresa", "representante_legal", "rut_representante")
}


def _cuerpo(campos, **confirmaciones):
    base = {
        "campos": campos,
        "solicitante_es_representante": True,
        "consentimiento_aceptado": True,
        "acepta_no_editar": True,
    }
    base.update(confirmaciones)
    return base


@pytest.fixture()
def tramite_de(crear_solicitud, convertir, seed, db_session):
    def _crear(nombre_servicio=CONTRATO, empresa=None, requiere_revision=False):
        seed["servicio"].nombre = nombre_servicio
        seed["servicio"].requiere_revision_humana = requiere_revision
        db_session.commit()
        resp = convertir(crear_solicitud()["id_solicitud"])
        assert resp.status_code == 200
        tramite = db_session.get(models.Tramite, resp.json()["id_tramite"])
        if empresa is not None:
            tramite.id_empresa = empresa.id_empresa
            db_session.commit()
        return tramite

    return _crear


@pytest.fixture()
def empresa_completa(db_session):
    empresa = models.Empresa(
        rut_empresa="76123456-0",
        razon_social="Comercial Prueba SpA",
        datos={
            "representante_legal": "Ana Soto Pérez",
            "rut_representante": "11222333-9",
            "domicilio_representante": "Av. Siempre Viva 742",
            "comuna_representante": "Providencia",
            "region_representante": "Metropolitana",
            "giro_principal": "Venta de artículos de oficina",
            "email": "ana@prueba.cl",
            "celular": "912345678",
            "fecha_escritura": "2020-05-15",
            "notaria": "Notaría 5",
        },
    )
    db_session.add(empresa)
    db_session.commit()
    db_session.refresh(empresa)
    return empresa


def _enviar(client, codigo, cuerpo):
    return client.post(f"/api/tramites/codigo/{codigo}/datos", json=cuerpo)


def _estado_guardado(db_session, tramite):
    db_session.expire_all()
    return db_session.get(models.Tramite, tramite.id_tramite)


class TestEnvioExitoso:
    def test_contrato_crea_la_empresa_y_pasa_a_procesando_firma(
        self, client, tramite_de, db_session
    ):
        tramite = tramite_de()

        resp = _enviar(client, tramite.codigo_seguimiento, _cuerpo(CAMPOS_CONTRATO))

        assert resp.status_code == 200
        assert resp.json() == {
            "codigo_seguimiento": tramite.codigo_seguimiento,
            "nombre_servicio": CONTRATO,
            "estado_actual": "procesando_firma",
            "documento_disponible": False,
        }
        guardado = _estado_guardado(db_session, tramite)
        assert guardado.estado_actual == "procesando_firma"
        empresa = db_session.query(models.Empresa).one()
        assert guardado.id_empresa == empresa.id_empresa

    def test_guarda_los_datos_ya_normalizados(self, client, tramite_de, db_session):
        tramite = tramite_de()
        _enviar(client, tramite.codigo_seguimiento, _cuerpo(CAMPOS_CONTRATO))

        empresa = db_session.query(models.Empresa).one()
        assert empresa.rut_empresa == "76123456-0"
        assert empresa.razon_social == "Comercial Prueba SpA"
        assert empresa.datos["rut_representante"] == "11222333-9"
        assert empresa.datos["celular"] == "912345678"
        assert empresa.datos["email"] == "ana@prueba.cl"
        assert "razon_social" not in empresa.datos and "rut_empresa" not in empresa.datos

    def test_registra_el_envio_con_sus_confirmaciones(self, client, tramite_de, db_session):
        tramite = tramite_de()
        _enviar(client, tramite.codigo_seguimiento, _cuerpo(CAMPOS_CONTRATO, solicitante_es_representante=False))

        envio = db_session.query(models.DatosEmpresaTramite).one()
        assert envio.id_tramite == tramite.id_tramite
        assert envio.solicitante_es_representante is False
        assert envio.consentimiento_aceptado is True

    def test_deja_constancia_en_el_historial(self, client, tramite_de, db_session):
        tramite = tramite_de()
        _enviar(client, tramite.codigo_seguimiento, _cuerpo(CAMPOS_CONTRATO))

        estados = [
            h.estado
            for h in db_session.query(models.HistorialEstado)
            .filter_by(id_tramite=tramite.id_tramite)
            .order_by(models.HistorialEstado.id_historial)
        ]
        assert estados == ["generado", "procesando_firma"]

    def test_autorizacion_pide_y_guarda_solo_sus_4_campos(self, client, tramite_de, db_session):
        tramite = tramite_de(AUTORIZACION)

        resp = _enviar(client, tramite.codigo_seguimiento, _cuerpo(CAMPOS_AUTORIZACION))

        assert resp.status_code == 200
        empresa = db_session.query(models.Empresa).one()
        assert set(empresa.datos) == {"representante_legal", "rut_representante"}

    def test_servicio_con_revision_humana_pasa_a_en_revision(self, client, tramite_de, db_session):
        tramite = tramite_de(requiere_revision=True)

        resp = _enviar(client, tramite.codigo_seguimiento, _cuerpo(CAMPOS_CONTRATO))

        assert resp.json()["estado_actual"] == "en_revision"
        assert _estado_guardado(db_session, tramite).estado_actual == "en_revision"

    def test_la_respuesta_no_devuelve_los_datos_ingresados(self, client, tramite_de):
        tramite = tramite_de()
        texto = _enviar(client, tramite.codigo_seguimiento, _cuerpo(CAMPOS_CONTRATO)).text
        for dato in ("Comercial Prueba", "Ana Soto", "Siempre Viva", "prueba.cl", "912345678", "76123456"):
            assert dato not in texto

    def test_es_publico_y_acepta_el_codigo_en_minusculas(self, client, tramite_de):
        tramite = tramite_de()
        resp = _enviar(client, tramite.codigo_seguimiento.lower(), _cuerpo(CAMPOS_CONTRATO))
        assert resp.status_code == 200


class TestConEmpresaVinculada:
    def test_con_todo_registrado_solo_se_envian_las_confirmaciones(
        self, client, tramite_de, empresa_completa, db_session
    ):
        tramite = tramite_de(empresa=empresa_completa)

        resp = _enviar(client, tramite.codigo_seguimiento, _cuerpo({}))

        assert resp.status_code == 200
        assert _estado_guardado(db_session, tramite).estado_actual == "procesando_firma"
        assert db_session.query(models.Empresa).count() == 1

    def test_completa_solo_lo_que_falta_sin_pisar_lo_existente(self, client, tramite_de, db_session):
        parcial = models.Empresa(
            rut_empresa="76123456-0",
            razon_social="Parcial SpA",
            datos={"email": "original@parcial.cl"},
        )
        db_session.add(parcial)
        db_session.commit()
        tramite = tramite_de(empresa=parcial)
        faltantes = {
            k: v for k, v in CAMPOS_CONTRATO.items()
            if k not in ("razon_social", "rut_empresa", "email")
        }

        resp = _enviar(client, tramite.codigo_seguimiento, _cuerpo(faltantes))

        assert resp.status_code == 200
        db_session.expire_all()
        empresa = db_session.query(models.Empresa).one()
        assert empresa.razon_social == "Parcial SpA"
        assert empresa.datos["email"] == "original@parcial.cl"
        assert empresa.datos["celular"] == "912345678"
        assert empresa.datos["notaria"] == "Notaría 5"

    def test_un_campo_ya_registrado_se_rechaza_nombrandolo_y_no_se_modifica(
        self, client, tramite_de, empresa_completa, db_session
    ):
        tramite = tramite_de(empresa=empresa_completa)

        resp = _enviar(client, tramite.codigo_seguimiento, _cuerpo({"email": "otro@lugar.cl"}))

        assert resp.status_code == 422
        errores = resp.json()["detail"]["errores"]
        assert list(errores) == ["email"]
        assert "ya está registrado" in errores["email"]
        db_session.expire_all()
        assert db_session.query(models.Empresa).one().datos["email"] == "ana@prueba.cl"
        assert db_session.query(models.DatosEmpresaTramite).count() == 0
        assert _estado_guardado(db_session, tramite).estado_actual == "generado"

    def test_la_autorizacion_reutiliza_la_empresa_creada_por_otro_tramite(
        self, client, tramite_de, empresa_completa
    ):
        tramite = tramite_de(AUTORIZACION, empresa=empresa_completa)
        resp = _enviar(client, tramite.codigo_seguimiento, _cuerpo({}))
        assert resp.status_code == 200


class TestRechazosDeCampos:
    def test_informa_todos_los_errores_juntos(self, client, tramite_de):
        tramite = tramite_de()
        campos = dict(CAMPOS_CONTRATO, email="no-es-correo", celular="123", fecha_escritura="2099-01-01")

        resp = _enviar(client, tramite.codigo_seguimiento, _cuerpo(campos))

        assert resp.status_code == 422
        detalle = resp.json()["detail"]
        assert detalle["mensaje"]
        assert set(detalle["errores"]) == {"email", "celular", "fecha_escritura"}

    def test_exige_todos_los_campos_que_faltan(self, client, tramite_de):
        tramite = tramite_de()
        resp = _enviar(client, tramite.codigo_seguimiento, _cuerpo({}))
        errores = resp.json()["detail"]["errores"]
        assert len(errores) == 12
        assert all(msg == "Este campo es obligatorio." for msg in errores.values())

    def test_rut_con_digito_verificador_incorrecto(self, client, tramite_de):
        tramite = tramite_de()
        resp = _enviar(client, tramite.codigo_seguimiento, _cuerpo(dict(CAMPOS_CONTRATO, rut_empresa="76.123.456-1")))
        assert list(resp.json()["detail"]["errores"]) == ["rut_empresa"]

    def test_campo_desconocido(self, client, tramite_de):
        tramite = tramite_de()
        resp = _enviar(client, tramite.codigo_seguimiento, _cuerpo(dict(CAMPOS_CONTRATO, hack="x")))
        assert resp.json()["detail"]["errores"] == {"hack": "Campo no permitido."}

    def test_un_servicio_no_acepta_campos_de_otro(self, client, tramite_de):
        tramite = tramite_de(AUTORIZACION)
        resp = _enviar(client, tramite.codigo_seguimiento, _cuerpo(dict(CAMPOS_AUTORIZACION, email="a@b.cl")))
        assert resp.json()["detail"]["errores"] == {"email": "Campo no permitido."}

    def test_un_rechazo_no_guarda_nada(self, client, tramite_de, db_session):
        tramite = tramite_de()
        _enviar(client, tramite.codigo_seguimiento, _cuerpo(dict(CAMPOS_CONTRATO, email="malo")))

        assert db_session.query(models.Empresa).count() == 0
        assert db_session.query(models.DatosEmpresaTramite).count() == 0
        assert _estado_guardado(db_session, tramite).estado_actual == "generado"
        assert db_session.query(models.HistorialEstado).filter_by(id_tramite=tramite.id_tramite).count() == 1


class TestConfirmaciones:
    @pytest.mark.parametrize("faltante", ["consentimiento_aceptado", "acepta_no_editar"])
    def test_exige_cada_confirmacion(self, client, tramite_de, db_session, faltante):
        tramite = tramite_de()

        resp = _enviar(client, tramite.codigo_seguimiento, _cuerpo(CAMPOS_CONTRATO, **{faltante: False}))

        assert resp.status_code == 422
        assert list(resp.json()["detail"]["errores"]) == [faltante]
        assert db_session.query(models.Empresa).count() == 0
        assert _estado_guardado(db_session, tramite).estado_actual == "generado"

    def test_sin_ninguna_confirmacion_informa_ambas(self, client, tramite_de):
        tramite = tramite_de()
        cuerpo = _cuerpo(CAMPOS_CONTRATO, consentimiento_aceptado=False, acepta_no_editar=False)
        resp = _enviar(client, tramite.codigo_seguimiento, cuerpo)
        assert set(resp.json()["detail"]["errores"]) == {"consentimiento_aceptado", "acepta_no_editar"}

    @pytest.mark.parametrize("valor", ["true", 1, "si", None])
    def test_las_confirmaciones_deben_ser_booleanos_reales(self, client, tramite_de, valor):
        tramite = tramite_de()
        resp = _enviar(client, tramite.codigo_seguimiento, _cuerpo(CAMPOS_CONTRATO, consentimiento_aceptado=valor))
        assert resp.status_code == 422

    @pytest.mark.parametrize("faltante", ["solicitante_es_representante", "consentimiento_aceptado", "acepta_no_editar"])
    def test_no_se_pueden_omitir(self, client, tramite_de, faltante):
        tramite = tramite_de()
        cuerpo = _cuerpo(CAMPOS_CONTRATO)
        del cuerpo[faltante]
        assert _enviar(client, tramite.codigo_seguimiento, cuerpo).status_code == 422

    def test_rechaza_campos_sueltos_en_el_cuerpo(self, client, tramite_de):
        tramite = tramite_de()
        cuerpo = _cuerpo(CAMPOS_CONTRATO, estado_actual="entregado")
        assert _enviar(client, tramite.codigo_seguimiento, cuerpo).status_code == 422


class TestEnvioUnico:
    def test_el_segundo_envio_da_409_y_no_cambia_nada(self, client, tramite_de, db_session):
        tramite = tramite_de()
        assert _enviar(client, tramite.codigo_seguimiento, _cuerpo(CAMPOS_CONTRATO)).status_code == 200

        otro = dict(CAMPOS_CONTRATO, razon_social="Otra Razón SpA")
        resp = _enviar(client, tramite.codigo_seguimiento, _cuerpo(otro))

        assert resp.status_code == 409
        assert "Ya recibimos tus datos" in resp.json()["detail"]
        db_session.expire_all()
        assert db_session.query(models.Empresa).one().razon_social == "Comercial Prueba SpA"
        assert db_session.query(models.DatosEmpresaTramite).count() == 1

    def test_dos_envios_casi_simultaneos_el_segundo_lo_corta_la_base_de_datos(
        self, TestingSessionLocal, tramite_de, empresa_completa, db_session
    ):
        tramite = tramite_de(empresa=empresa_completa)
        envio = schemas.EnvioDatosIn(
            campos={}, solicitante_es_representante=True,
            consentimiento_aceptado=True, acepta_no_editar=True,
        )
        # Dos "peticiones" cargan el trámite cuando todavía no tiene envío.
        otra_sesion = TestingSessionLocal()
        try:
            copia = otra_sesion.get(models.Tramite, tramite.id_tramite)
            assert copia.datos_empresa is None

            crud.registrar_envio_datos(db_session, tramite, envio)

            with pytest.raises(crud.DatosYaEnviados):
                crud.registrar_envio_datos(otra_sesion, copia, envio)
        finally:
            otra_sesion.close()
        assert db_session.query(models.DatosEmpresaTramite).count() == 1

    @pytest.mark.parametrize("estado", ["procesando_firma", "en_revision", "firmado", "entregado"])
    def test_si_el_tramite_ya_no_espera_datos_da_409(self, client, tramite_de, db_session, estado):
        tramite = tramite_de()
        tramite.estado_actual = estado
        db_session.commit()

        resp = _enviar(client, tramite.codigo_seguimiento, _cuerpo(CAMPOS_CONTRATO))

        assert resp.status_code == 409
        assert db_session.query(models.Empresa).count() == 0

    def test_servicio_sin_formulario_definido_da_409(self, client, tramite_de):
        tramite = tramite_de("Constitución de Sociedad")
        resp = _enviar(client, tramite.codigo_seguimiento, _cuerpo(CAMPOS_CONTRATO))
        assert resp.status_code == 409


class TestRutDeEmpresaExistente:
    def test_si_el_rut_ya_existe_se_rechaza_con_mensaje_generico(
        self, client, tramite_de, empresa_completa, db_session
    ):
        tramite = tramite_de()  # NO vinculado: el vínculo lo hace solo un agente

        resp = _enviar(client, tramite.codigo_seguimiento, _cuerpo(CAMPOS_CONTRATO))

        assert resp.status_code == 409
        assert resp.json()["detail"] == (
            "No pudimos registrar ese RUT. Contacta a tu agente indicando tu código."
        )
        assert "Comercial Prueba" not in resp.text

    def test_el_rechazo_no_vincula_ni_guarda_nada(self, client, tramite_de, empresa_completa, db_session):
        tramite = tramite_de()
        _enviar(client, tramite.codigo_seguimiento, _cuerpo(CAMPOS_CONTRATO))

        guardado = _estado_guardado(db_session, tramite)
        assert guardado.id_empresa is None
        assert guardado.estado_actual == "generado"
        assert db_session.query(models.DatosEmpresaTramite).count() == 0
        assert db_session.query(models.Empresa).count() == 1
        # La empresa existente quedó intacta.
        assert db_session.query(models.Empresa).one().datos["email"] == "ana@prueba.cl"

    def test_se_puede_reintentar_con_otro_rut_despues_del_rechazo(
        self, client, tramite_de, empresa_completa
    ):
        tramite = tramite_de()
        assert _enviar(client, tramite.codigo_seguimiento, _cuerpo(CAMPOS_CONTRATO)).status_code == 409

        otro_rut = dict(CAMPOS_CONTRATO, rut_empresa="77.111.222-6")
        assert _enviar(client, tramite.codigo_seguimiento, _cuerpo(otro_rut)).status_code == 200


class TestCodigoYLimite:
    @pytest.mark.parametrize("codigo", ["abc", "123456789"])
    def test_codigo_de_largo_incorrecto_400(self, client, codigo):
        assert _enviar(client, codigo, _cuerpo(CAMPOS_CONTRATO)).status_code == 400

    def test_codigo_inexistente_404(self, client, tramite_de):
        tramite_de()
        assert _enviar(client, "ZZZZZZZZ", _cuerpo(CAMPOS_CONTRATO)).status_code == 404

    @pytest.fixture()
    def limite_activo(self):
        limiter.reset()
        limiter.enabled = True
        yield
        limiter.enabled = False
        limiter.reset()

    def test_pasados_10_envios_por_minuto_responde_429(self, client, limite_activo):
        respuestas = [_enviar(client, "ZZZZZZZZ", _cuerpo(CAMPOS_CONTRATO)).status_code for _ in range(11)]
        assert respuestas[:10] == [404] * 10
        assert respuestas[10] == 429