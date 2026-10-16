"""Conversión con sucursal, condiciones del contrato y folio automático."""
from datetime import date

import pytest

from app import condiciones, models


@pytest.fixture()
def sucursal(db_session):
    s = models.Sucursal(
        iniciales="LF", nombre="La Florida", direccion="Vicuña Mackenna Poniente #7255, Oficina 707",
        comuna="La Florida", region="Metropolitana", rol_propiedad="271-147",
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


@pytest.fixture()
def servicios(db_session):
    filas = [
        models.ServicioOfrecido(nombre="Domicilio tributario", descripcion="*Domicilio tributario", precio_referencia=59990, ciclo_pago_defecto="ANUAL"),
        models.ServicioOfrecido(nombre="Bodega", descripcion="*Bodega", precio_referencia=71388, ciclo_pago_defecto="ANUAL"),
        models.ServicioOfrecido(nombre="Web mail", descripcion="*Web mail", precio_referencia=14990, ciclo_pago_defecto="ANUAL"),
        models.ServicioOfrecido(nombre="Contabilidad", descripcion="*Contabilidad", precio_referencia=None, ciclo_pago_defecto="MENSUAL"),
        models.ServicioOfrecido(nombre="Descontinuado", descripcion="x", precio_referencia=1, ciclo_pago_defecto="ANUAL", activo=False),
    ]
    db_session.add_all(filas)
    db_session.commit()
    for f in filas:
        db_session.refresh(f)
    return filas


def cuerpo(sucursal, servicios, **cambios):
    base = {
        "id_sucursal": sucursal.id_sucursal,
        "condiciones": {
            "servicios": [{"id_servicio_ofrecido": servicios[0].id_servicio_ofrecido, "precio": 59990, "ciclo_pago": "ANUAL"}],
            "duracion_meses": 12,
            "fecha_inicio": "2026-01-15",
        },
    }
    base.update(cambios)
    return base


@pytest.fixture()
def enviar(client, headers_agente, crear_solicitud):
    def _enviar(cuerpo_json, id_solicitud=None):
        if id_solicitud is None:
            id_solicitud = crear_solicitud()["id_solicitud"]
        return client.post(f"/api/solicitudes-contacto/{id_solicitud}/convertir", json=cuerpo_json, headers=headers_agente)

    return _enviar


def tramite_guardado(db_session, id_tramite):
    db_session.expire_all()
    return db_session.get(models.Tramite, id_tramite)


def _cliente(db_session):
    c = models.Cliente(nombre="X", rut="1-9")
    db_session.add(c)
    db_session.commit()
    return c.id_cliente


def _id_servicio(db_session):
    return db_session.query(models.ServicioContratado).first().id_servicio


class TestVencimiento:
    @pytest.mark.parametrize("inicio,meses,esperado", [
        (date(2026, 1, 15), 12, date(2027, 1, 14)),
        (date(2026, 1, 1), 12, date(2026, 12, 31)),
        (date(2026, 3, 10), 6, date(2026, 9, 9)),
        (date(2026, 1, 31), 1, date(2026, 2, 28)),   # el día 31 no existe en febrero
        (date(2024, 1, 31), 1, date(2024, 2, 29)),   # año bisiesto
        (date(2026, 11, 20), 3, date(2027, 2, 19)),  # cruza de año
        (date(2026, 1, 15), 1, date(2026, 2, 14)),
    ])
    def test_calculo(self, inicio, meses, esperado):
        assert condiciones.calcular_vencimiento(inicio, meses) == esperado


class TestOpciones:
    def test_exige_login(self, client):
        assert client.get("/api/opciones-contrato").status_code == 401

    def test_entrega_los_valores_permitidos(self, client, headers_agente):
        resp = client.get("/api/opciones-contrato", headers=headers_agente)
        assert resp.status_code == 200
        assert resp.json() == {
            "ciclos_pago": ["ÚNICO", "ANUAL", "SEMESTRAL", "TRIMESTRAL", "MENSUAL"],
            "duraciones_meses": [12, 6, 4, 3, 1],
            "max_servicios": 3,
        }


class TestConvertirConCondiciones:
    def test_guarda_sucursal_folio_y_condiciones(self, enviar, db_session, sucursal, servicios):
        resp = enviar(cuerpo(sucursal, servicios))

        assert resp.status_code == 200, resp.text
        assert resp.json()["folio"] == f"LF-01-{date.today().year}"
        t = tramite_guardado(db_session, resp.json()["id_tramite"])
        assert t.id_sucursal == sucursal.id_sucursal
        assert t.folio == resp.json()["folio"]
        assert t.condiciones == {
            "servicios": [{
                "id_servicio_ofrecido": servicios[0].id_servicio_ofrecido,
                "nombre": "Domicilio tributario", "descripcion": "*Domicilio tributario",
                "precio": 59990, "ciclo_pago": "ANUAL",
            }],
            "duracion_meses": 12,
            "fecha_inicio": "2026-01-15",
            "fecha_vencimiento": "2027-01-14",
            "vencimiento_manual": False,
        }

    def test_el_vencimiento_corregido_por_el_agente_se_respeta_y_se_marca(self, enviar, db_session, sucursal, servicios):
        c = cuerpo(sucursal, servicios)
        c["condiciones"]["fecha_vencimiento"] = "2027-01-15"

        t = tramite_guardado(db_session, enviar(c).json()["id_tramite"])

        assert t.condiciones["fecha_vencimiento"] == "2027-01-15"
        assert t.condiciones["vencimiento_manual"] is True

    def test_vencimiento_igual_al_calculado_no_cuenta_como_manual(self, enviar, db_session, sucursal, servicios):
        c = cuerpo(sucursal, servicios)
        c["condiciones"]["fecha_vencimiento"] = "2027-01-14"

        t = tramite_guardado(db_session, enviar(c).json()["id_tramite"])

        assert t.condiciones["vencimiento_manual"] is False

    def test_hasta_tres_servicios_con_precio_y_ciclo_propios(self, enviar, db_session, sucursal, servicios):
        c = cuerpo(sucursal, servicios)
        c["condiciones"]["servicios"] = [
            {"id_servicio_ofrecido": servicios[0].id_servicio_ofrecido, "precio": 50000, "ciclo_pago": "mensual"},
            {"id_servicio_ofrecido": servicios[1].id_servicio_ofrecido, "precio": 0, "ciclo_pago": "unico"},
            {"id_servicio_ofrecido": servicios[3].id_servicio_ofrecido, "precio": 30000, "ciclo_pago": "SEMESTRAL"},
        ]

        t = tramite_guardado(db_session, enviar(c).json()["id_tramite"])

        assert [(s["nombre"], s["precio"], s["ciclo_pago"]) for s in t.condiciones["servicios"]] == [
            ("Domicilio tributario", 50000, "MENSUAL"), ("Bodega", 0, "ÚNICO"), ("Contabilidad", 30000, "SEMESTRAL"),
        ]

    def test_el_historial_menciona_sucursal_y_folio(self, enviar, db_session, sucursal, servicios):
        id_tramite = enviar(cuerpo(sucursal, servicios)).json()["id_tramite"]

        h = db_session.query(models.HistorialEstado).filter_by(id_tramite=id_tramite).one()

        assert "La Florida" in h.comentario and f"LF-01-{date.today().year}" in h.comentario

    def test_solo_sucursal_sin_condiciones_asigna_folio(self, enviar, db_session, sucursal):
        resp = enviar({"id_sucursal": sucursal.id_sucursal})

        assert resp.status_code == 200
        t = tramite_guardado(db_session, resp.json()["id_tramite"])
        assert t.folio == f"LF-01-{date.today().year}" and t.condiciones is None

    def test_se_puede_combinar_con_empresa(self, enviar, db_session, sucursal, servicios):
        e = models.Empresa(rut_empresa="76123456-7", razon_social="Empresa Uno SpA")
        db_session.add(e)
        db_session.commit()

        resp = enviar(cuerpo(sucursal, servicios, id_empresa=e.id_empresa))

        assert tramite_guardado(db_session, resp.json()["id_tramite"]).id_empresa == e.id_empresa

    def test_sin_cuerpo_sigue_funcionando_como_antes(self, convertir, crear_solicitud, db_session):
        resp = convertir(crear_solicitud()["id_solicitud"])

        assert resp.status_code == 200
        assert resp.json()["folio"] is None
        t = tramite_guardado(db_session, resp.json()["id_tramite"])
        assert t.id_sucursal is None and t.folio is None and t.condiciones is None


class TestFolio:
    def test_correlativo_por_sucursal_y_anio(self, enviar, sucursal, servicios, db_session):
        otra = models.Sucursal(iniciales="VL", nombre="Valparaíso", direccion="Blanco 1215", comuna="Valparaíso", region="Valparaíso")
        db_session.add(otra)
        db_session.commit()
        anio = date.today().year

        folios = [enviar({"id_sucursal": sucursal.id_sucursal}).json()["folio"] for _ in range(2)]
        folios.append(enviar({"id_sucursal": otra.id_sucursal}).json()["folio"])

        assert folios == [f"LF-01-{anio}", f"LF-02-{anio}", f"VL-01-{anio}"]

    def test_un_folio_de_otro_anio_no_cuenta(self, enviar, sucursal, servicios, db_session):
        db_session.add(models.Tramite(
            id_cliente=_cliente(db_session), id_servicio=_id_servicio(db_session), codigo_seguimiento="ABCD2345",
            id_sucursal=sucursal.id_sucursal, folio="LF-50-2020",
        ))
        db_session.commit()

        assert enviar({"id_sucursal": sucursal.id_sucursal}).json()["folio"] == f"LF-01-{date.today().year}"

    def test_pasa_de_99_sin_perder_el_orden(self, enviar, sucursal, db_session):
        anio = date.today().year
        db_session.add(models.Tramite(
            id_cliente=_cliente(db_session), id_servicio=_id_servicio(db_session), codigo_seguimiento="ABCD2345",
            id_sucursal=sucursal.id_sucursal, folio=f"LF-99-{anio}",
        ))
        db_session.commit()

        assert enviar({"id_sucursal": sucursal.id_sucursal}).json()["folio"] == f"LF-100-{anio}"

    def test_choque_de_folio_responde_409_y_no_guarda_nada(self, enviar, client, sucursal, db_session, monkeypatch, crear_solicitud):
        anio = date.today().year
        assert enviar({"id_sucursal": sucursal.id_sucursal}).status_code == 200
        monkeypatch.setattr(condiciones, "siguiente_folio", lambda *_a, **_k: f"LF-01-{anio}")
        id_solicitud = crear_solicitud()["id_solicitud"]

        resp = enviar({"id_sucursal": sucursal.id_sucursal}, id_solicitud)

        assert resp.status_code == 409
        assert "intenta nuevamente" in resp.json()["detail"].lower()
        db_session.expire_all()
        solicitud = db_session.get(models.SolicitudContacto, id_solicitud)
        assert solicitud.estado != "convertido" and solicitud.id_tramite_generado is None
        assert db_session.query(models.Tramite).count() == 1

    def test_tras_el_choque_se_puede_reintentar(self, enviar, sucursal, db_session, monkeypatch, crear_solicitud):
        anio = date.today().year
        enviar({"id_sucursal": sucursal.id_sucursal})
        real = condiciones.siguiente_folio
        monkeypatch.setattr(condiciones, "siguiente_folio", lambda *_a, **_k: f"LF-01-{anio}")
        id_solicitud = crear_solicitud()["id_solicitud"]
        assert enviar({"id_sucursal": sucursal.id_sucursal}, id_solicitud).status_code == 409
        monkeypatch.setattr(condiciones, "siguiente_folio", real)

        resp = enviar({"id_sucursal": sucursal.id_sucursal}, id_solicitud)

        assert resp.status_code == 200 and resp.json()["folio"] == f"LF-02-{anio}"


class TestRechazos:
    @pytest.mark.parametrize("cambio,codigo", [
        ({"duracion_meses": 5}, 422),
        ({"duracion_meses": 0}, 422),
        ({"fecha_inicio": "no-es-fecha"}, 422),
        ({"fecha_vencimiento": "2026-01-15"}, 422),   # igual al inicio
        ({"fecha_vencimiento": "2025-12-31"}, 422),   # anterior al inicio
        ({"servicios": []}, 422),
    ])
    def test_condiciones_invalidas(self, enviar, db_session, sucursal, servicios, cambio, codigo):
        c = cuerpo(sucursal, servicios)
        c["condiciones"].update(cambio)

        assert enviar(c).status_code == codigo
        assert db_session.query(models.Tramite).count() == 0

    @pytest.mark.parametrize("servicio", [
        {"precio": -1, "ciclo_pago": "ANUAL"},
        {"precio": 100_000_001, "ciclo_pago": "ANUAL"},
        {"precio": 1000, "ciclo_pago": "QUINCENAL"},
        {"precio": 1000, "ciclo_pago": ""},
        {"precio": "mucho", "ciclo_pago": "ANUAL"},
        {"precio": 10.5, "ciclo_pago": "ANUAL"},
    ])
    def test_servicio_invalido(self, enviar, sucursal, servicios, servicio):
        c = cuerpo(sucursal, servicios)
        c["condiciones"]["servicios"] = [{"id_servicio_ofrecido": servicios[0].id_servicio_ofrecido, **servicio}]

        assert enviar(c).status_code == 422

    def test_mas_de_tres_servicios(self, enviar, sucursal, servicios):
        c = cuerpo(sucursal, servicios)
        c["condiciones"]["servicios"] = [
            {"id_servicio_ofrecido": s.id_servicio_ofrecido, "precio": 1, "ciclo_pago": "ANUAL"} for s in servicios[:4]
        ]

        assert enviar(c).status_code == 422

    def test_servicio_repetido(self, enviar, sucursal, servicios):
        c = cuerpo(sucursal, servicios)
        item = c["condiciones"]["servicios"][0]
        c["condiciones"]["servicios"] = [item, dict(item)]

        assert enviar(c).status_code == 422

    def test_condiciones_sin_sucursal(self, enviar, db_session, sucursal, servicios):
        c = cuerpo(sucursal, servicios)
        del c["id_sucursal"]

        assert enviar(c).status_code == 422
        assert db_session.query(models.Tramite).count() == 0

    @pytest.mark.parametrize("id_servicio", [99999, "inactivo"])
    def test_servicio_inexistente_o_inactivo_responde_400_y_no_guarda_nada(self, enviar, db_session, sucursal, servicios, id_servicio):
        c = cuerpo(sucursal, servicios)
        c["condiciones"]["servicios"][0]["id_servicio_ofrecido"] = (
            servicios[4].id_servicio_ofrecido if id_servicio == "inactivo" else id_servicio
        )

        resp = enviar(c)

        assert resp.status_code == 400
        assert "no existe o no está activo" in resp.json()["detail"]
        assert db_session.query(models.Tramite).count() == 0
        assert db_session.query(models.Cliente).count() == 0

    def test_sucursal_inexistente(self, enviar):
        assert enviar({"id_sucursal": 9999}).status_code == 404

    def test_sucursal_inactiva(self, enviar, db_session, sucursal):
        sucursal.activa = False
        db_session.commit()

        assert enviar({"id_sucursal": sucursal.id_sucursal}).status_code == 404

    def test_sucursal_con_id_invalido(self, enviar):
        assert enviar({"id_sucursal": 0}).status_code == 422

    def test_una_solicitud_ya_convertida_no_gasta_folio(self, enviar, sucursal, crear_solicitud):
        id_solicitud = crear_solicitud()["id_solicitud"]
        assert enviar({"id_sucursal": sucursal.id_sucursal}, id_solicitud).status_code == 200

        assert enviar({"id_sucursal": sucursal.id_sucursal}, id_solicitud).status_code == 400
        assert enviar({"id_sucursal": sucursal.id_sucursal}).json()["folio"].startswith("LF-02-")


class TestListadoMuestraElFolio:
    def test_listado_incluye_folio(self, client, enviar, headers_agente, sucursal, servicios):
        enviar(cuerpo(sucursal, servicios))

        item = client.get("/api/solicitudes-contacto", headers=headers_agente).json()[0]

        assert item["folio"] == f"LF-01-{date.today().year}"

    def test_pendiente_o_sin_sucursal_sale_con_folio_null(self, client, convertir, crear_solicitud, headers_agente):
        crear_solicitud()
        convertido = crear_solicitud()
        convertir(convertido["id_solicitud"])

        assert all(i["folio"] is None for i in client.get("/api/solicitudes-contacto", headers=headers_agente).json())