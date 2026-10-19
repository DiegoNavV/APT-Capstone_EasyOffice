"""Endpoints de plantillas: subir versiones, activar, listar, descargar y permisos."""
import pytest

from app import models
from app.seguridad import crear_access_token, hash_password
from tests.test_marcas_documento import hacer_docx, parrafo_mergefield, parrafo_texto

DOCX_TIPO = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture(autouse=True)
def carpeta_plantillas(tmp_path, monkeypatch):
    """Cada prueba guarda los archivos en una carpeta temporal."""
    monkeypatch.setenv("PLANTILLAS_DIR", str(tmp_path / "plantillas"))
    monkeypatch.delenv("ROLES_GESTORES_PLANTILLAS", raising=False)
    return tmp_path / "plantillas"


@pytest.fixture()
def headers_admin(db_session, seed):
    admin = models.Usuario(
        nombre="Admin Prueba",
        email="admin@easyoffice.cl",
        password_hash=hash_password("otra-clave-123"),
        rol=models.Rol(nombre="administrador"),
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return {"Authorization": f"Bearer {crear_access_token(admin.id_usuario, 'administrador')}"}


def docx_con(texto="{{FOLIO}} {{RAZON_SOCIAL}}") -> bytes:
    return hacer_docx(parrafo_texto(texto))


@pytest.fixture()
def subir(client, headers_admin, seed):
    def _subir(contenido=None, id_servicio=None, nombre_archivo="contrato.docx", headers=None, **form):
        datos = {"id_servicio": str(id_servicio or seed["servicio"].id_servicio)}
        datos.update({k: str(v) for k, v in form.items()})
        return client.post(
            "/api/plantillas",
            data=datos,
            files={"archivo": (nombre_archivo, contenido if contenido is not None else docx_con(), DOCX_TIPO)},
            headers=headers or headers_admin,
        )

    return _subir


def test_subir_primera_version(subir, seed, carpeta_plantillas):
    r = subir()
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert cuerpo["version"] == "1"
    assert cuerpo["activa"] is True
    assert cuerpo["marcas"] == ["FOLIO", "RAZON_SOCIAL"]
    assert cuerpo["nombre"] == seed["servicio"].nombre
    assert cuerpo["subida_por"] == "Admin Prueba"
    assert cuerpo["nombre_original"] == "contrato.docx"
    assert len(list(carpeta_plantillas.rglob("*.docx"))) == 1


def test_segunda_version_desactiva_la_anterior_y_la_conserva(subir, client, headers_admin, carpeta_plantillas):
    subir(docx_con("{{FOLIO}}"))
    r2 = subir(docx_con("{{FOLIO}} {{RUT}}"))
    assert r2.json()["version"] == "2" and r2.json()["activa"] is True
    lista = client.get("/api/plantillas", headers=headers_admin).json()
    assert [(p["version"], p["activa"]) for p in lista] == [("2", True), ("1", False)]
    assert len(list(carpeta_plantillas.rglob("*.docx"))) == 2


def test_subir_sin_activar_deja_la_actual(subir, client, headers_admin):
    subir(docx_con("{{FOLIO}}"))
    r2 = subir(docx_con("{{RUT}}"), activar="false")
    assert r2.json()["activa"] is False
    lista = client.get("/api/plantillas", headers=headers_admin).json()
    assert [(p["version"], p["activa"]) for p in lista] == [("2", False), ("1", True)]


def test_activar_version_anterior(subir, client, headers_admin):
    v1 = subir(docx_con("{{FOLIO}}")).json()
    subir(docx_con("{{RUT}}"))
    r = client.post(f"/api/plantillas/{v1['id_plantilla']}/activar", headers=headers_admin)
    assert r.status_code == 200 and r.json()["activa"] is True
    lista = client.get("/api/plantillas", headers=headers_admin).json()
    assert [(p["version"], p["activa"]) for p in lista] == [("2", False), ("1", True)]


def test_activar_la_que_ya_esta_activa_no_falla(subir, client, headers_admin):
    v1 = subir().json()
    r = client.post(f"/api/plantillas/{v1['id_plantilla']}/activar", headers=headers_admin)
    assert r.status_code == 200 and r.json()["activa"] is True


def test_numero_de_version_no_se_repite_tras_activar_otra(subir, client, headers_admin):
    v1 = subir(docx_con("{{FOLIO}}")).json()
    subir(docx_con("{{RUT}}"))
    client.post(f"/api/plantillas/{v1['id_plantilla']}/activar", headers=headers_admin)
    assert subir(docx_con("{{MAIL}}")).json()["version"] == "3"


def test_archivo_identico_se_rechaza(subir):
    subir(docx_con("{{FOLIO}}"))
    r = subir(docx_con("{{FOLIO}}"))
    assert r.status_code == 409
    assert "idéntico a la versión 1" in r.json()["detail"]


def test_versiones_independientes_por_servicio(subir, db_session, seed):
    otro = models.ServicioContratado(nombre="Autorización de domicilio tributario", activo=True)
    db_session.add(otro)
    db_session.commit()
    db_session.refresh(otro)
    a = subir(docx_con("{{FOLIO}}")).json()
    b = subir(docx_con("{{FOLIO}}"), id_servicio=otro.id_servicio).json()
    assert a["version"] == "1" and b["version"] == "1"
    assert a["activa"] is True and b["activa"] is True


def test_marca_desconocida_da_422_y_no_guarda(subir, client, headers_admin, carpeta_plantillas):
    r = subir(docx_con("{{INVENTADA}}"))
    assert r.status_code == 422 and "INVENTADA" in r.json()["detail"]
    assert client.get("/api/plantillas", headers=headers_admin).json() == []
    assert not list(carpeta_plantillas.rglob("*.docx"))


def test_extension_incorrecta(subir):
    r = subir(nombre_archivo="contrato.pdf")
    assert r.status_code == 422 and ".docx" in r.json()["detail"]


def test_no_es_word_aunque_se_llame_docx(subir):
    r = subir(b"no soy un word")
    assert r.status_code == 422


def test_archivo_muy_grande(subir):
    r = subir(b"PK" + b"0" * (11 * 1024 * 1024))
    assert r.status_code == 422 and "pesa demasiado" in r.json()["detail"]


def test_servicio_inexistente_o_inactivo(subir, seed):
    assert subir(id_servicio=9999).status_code == 404
    assert subir(id_servicio=seed["servicio_inactivo"].id_servicio).status_code == 404


def test_nombre_personalizado(subir):
    assert subir(nombre="Contrato oficina 2026").json()["nombre"] == "Contrato oficina 2026"


def test_acepta_mergefield_de_word(subir):
    r = subir(hacer_docx(parrafo_mergefield("RAZON_SOCIAL") + parrafo_mergefield("RUT")))
    assert r.status_code == 201 and r.json()["marcas"] == ["RAZON_SOCIAL", "RUT"]


def test_descargar(subir, client, headers_admin):
    contenido = docx_con("{{FOLIO}}")
    v = subir(contenido).json()
    r = client.get(f"/api/plantillas/{v['id_plantilla']}/descargar", headers=headers_admin)
    assert r.status_code == 200
    assert r.content == contenido
    assert "attachment" in r.headers["content-disposition"]


def test_descargar_inexistente(client, headers_admin):
    assert client.get("/api/plantillas/999/descargar", headers=headers_admin).status_code == 404


def test_descargar_con_archivo_borrado_del_disco(subir, client, headers_admin, carpeta_plantillas):
    v = subir().json()
    for f in carpeta_plantillas.rglob("*.docx"):
        f.unlink()
    assert client.get(f"/api/plantillas/{v['id_plantilla']}/descargar", headers=headers_admin).status_code == 404


def test_ruta_manipulada_no_sale_de_la_carpeta(subir, client, headers_admin, db_session):
    v = subir().json()
    p = db_session.get(models.PlantillaDocumento, v["id_plantilla"])
    p.ruta_archivo = "../../etc/passwd"
    db_session.commit()
    assert client.get(f"/api/plantillas/{v['id_plantilla']}/descargar", headers=headers_admin).status_code == 404


# ---------- Permisos ----------

def test_sin_sesion_401(client):
    assert client.get("/api/plantillas").status_code == 401
    assert client.get("/api/plantillas/configuracion").status_code == 401
    assert client.post("/api/plantillas/1/activar").status_code == 401
    assert client.get("/api/plantillas/1/descargar").status_code == 401


def test_agente_no_puede_gestionar_por_defecto(client, headers_agente, subir):
    assert client.get("/api/plantillas", headers=headers_agente).status_code == 403
    assert subir(headers=headers_agente).status_code == 403
    assert client.post("/api/plantillas/1/activar", headers=headers_agente).status_code == 403
    assert client.get("/api/plantillas/1/descargar", headers=headers_agente).status_code == 403


def test_configuracion_del_agente_oculta_todo(client, headers_agente):
    r = client.get("/api/plantillas/configuracion", headers=headers_agente)
    assert r.status_code == 200
    assert r.json() == {"puede_gestionar": False, "max_tamano_mb": 0, "servicios": [], "marcas": []}


def test_configuracion_del_admin(client, headers_admin, seed):
    r = client.get("/api/plantillas/configuracion", headers=headers_admin).json()
    assert r["puede_gestionar"] is True and r["max_tamano_mb"] == 10
    assert [s["nombre"] for s in r["servicios"]] == [seed["servicio"].nombre]  # solo activos
    assert any(m["nombre"] == "RAZON_SOCIAL" for m in r["marcas"])


def test_roles_configurables_por_entorno(client, headers_agente, monkeypatch):
    monkeypatch.setenv("ROLES_GESTORES_PLANTILLAS", "administrador, agente")
    assert client.get("/api/plantillas", headers=headers_agente).status_code == 200
    assert client.get("/api/plantillas/configuracion", headers=headers_agente).json()["puede_gestionar"] is True


def test_filtrar_por_servicio(subir, client, headers_admin, db_session):
    otro = models.ServicioContratado(nombre="Otro", activo=True)
    db_session.add(otro)
    db_session.commit()
    db_session.refresh(otro)
    subir(docx_con("{{FOLIO}}"))
    subir(docx_con("{{FOLIO}}"), id_servicio=otro.id_servicio)
    todas = client.get("/api/plantillas", headers=headers_admin).json()
    solo = client.get(f"/api/plantillas?id_servicio={otro.id_servicio}", headers=headers_admin).json()
    assert len(todas) == 2 and len(solo) == 1 and solo[0]["id_servicio"] == otro.id_servicio