"""Descarga pública del documento firmado: GET /api/tramites/codigo/{codigo}/documento."""
import pytest
from urllib.parse import unquote

from app import models, documentos
from tests.test_valores_documento import tramite  # noqa: F401  (fixture)

CODIGO = "ABCD2345"          # código de seguimiento del trámite de prueba
URL = f"/api/tramites/codigo/{CODIGO}/documento"
PDF_FIRMADO = b"%PDF-1.7 firmado"


@pytest.fixture(autouse=True)
def carpeta_documentos(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCUMENTOS_DIR", str(tmp_path / "documentos"))
    return tmp_path / "documentos"


def _con_estado(db_session, tramite, estado):  # noqa: F811
    tramite.estado_actual = estado
    db_session.add(models.HistorialEstado(
        id_tramite=tramite.id_tramite, estado=estado, origen="sistema", comentario="Preparado por la prueba.",
    ))
    db_session.commit()


def _con_pdf(db_session, seed, tramite, carpeta_documentos):  # noqa: F811
    """Deja el PDF firmado guardado como lo deja el webhook de la API de firma."""
    plantilla = models.PlantillaDocumento(
        id_servicio=seed["servicio"].id_servicio, nombre="Contrato", version=1,
        ruta_archivo="plantilla_prueba.docx", nombre_original="contrato.docx",
        hash_sha256="a" * 64, tamano_bytes=10, marcas=[], id_usuario_subio=seed["usuario"].id_usuario,
    )
    db_session.add(plantilla)
    db_session.flush()

    ruta = f"tramite_{tramite.id_tramite}.pdf"
    carpeta_documentos.mkdir(parents=True, exist_ok=True)
    (carpeta_documentos / ruta).write_bytes(PDF_FIRMADO)
    tramite.ruta_documento_generado = ruta
    tramite.id_plantilla = plantilla.id_plantilla
    db_session.commit()


@pytest.fixture()
def firmado(db_session, seed, tramite, carpeta_documentos):  # noqa: F811
    _con_pdf(db_session, seed, tramite, carpeta_documentos)
    _con_estado(db_session, tramite, "firmado")
    return tramite


def _estado(db_session, tramite):  # noqa: F811
    db_session.expire_all()
    return db_session.get(models.Tramite, tramite.id_tramite).estado_actual


def _entregas(db_session, tramite):  # noqa: F811
    db_session.expire_all()
    return (
        db_session.query(models.HistorialEstado)
        .filter_by(id_tramite=tramite.id_tramite, estado="entregado")
        .all()
    )


class TestDescargaDelCliente:

    def test_descarga_el_pdf_firmado_sin_iniciar_sesion(self, client, firmado):
        r = client.get(URL)

        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content == PDF_FIRMADO

    def test_el_archivo_se_llama_servicio_y_empresa_y_no_se_guarda_en_cache(self, client, firmado):
        r = client.get(URL)

        # Con acentos el nombre viaja codificado (filename*=utf-8''...); se decodifica para compararlo.
        nombre = unquote(r.headers["content-disposition"])
        assert f"{firmado.servicio.nombre} - Altus and Company Co. SpA.pdf" in nombre
        assert r.headers["cache-control"] == "no-store"
        assert r.headers["x-content-type-options"] == "nosniff"

    def test_la_primera_descarga_marca_el_tramite_como_entregado(self, client, db_session, firmado):
        client.get(URL)

        assert _estado(db_session, firmado) == "entregado"
        entregas = _entregas(db_session, firmado)
        assert len(entregas) == 1
        assert entregas[0].origen == "cliente"

    def test_una_segunda_descarga_funciona_y_no_repite_la_entrega(self, client, db_session, firmado):
        client.get(URL)
        r = client.get(URL)

        assert r.status_code == 200
        assert r.content == PDF_FIRMADO
        assert _estado(db_session, firmado) == "entregado"
        assert len(_entregas(db_session, firmado)) == 1

    def test_acepta_el_codigo_en_minusculas(self, client, firmado):
        assert client.get(f"/api/tramites/codigo/{CODIGO.lower()}/documento").status_code == 200


class TestSinDescarga:

    def test_codigo_con_largo_incorrecto_da_400(self, client):
        assert client.get("/api/tramites/codigo/ABC/documento").status_code == 400

    def test_codigo_que_no_existe_da_404(self, client, tramite):  # noqa: F811
        assert client.get("/api/tramites/codigo/ZZZZZZZZ/documento").status_code == 404

    @pytest.mark.parametrize("estado", ["esperando_datos", "procesando_firma", "en_revision", "rechazado"])
    def test_antes_de_la_firma_da_409_y_no_cambia_el_estado(self, client, db_session, tramite, estado):  # noqa: F811
        if estado != "esperando_datos":
            _con_estado(db_session, tramite, estado)

        r = client.get(URL)

        assert r.status_code == 409
        assert _estado(db_session, tramite) == estado
        assert _entregas(db_session, tramite) == []

    def test_firmado_pero_sin_archivo_da_404_y_no_marca_entregado(self, client, db_session, tramite):  # noqa: F811
        _con_estado(db_session, tramite, "firmado")

        r = client.get(URL)

        assert r.status_code == 404
        assert _estado(db_session, tramite) == "firmado"


class TestNombreParaCliente:

    def test_servicio_y_razon_social_de_la_empresa(self, tramite):  # noqa: F811
        assert documentos.nombre_para_cliente(tramite) == f"{tramite.servicio.nombre} - Altus and Company Co. SpA.pdf"

    def test_sin_empresa_queda_solo_el_servicio(self, db_session, tramite):  # noqa: F811
        tramite.id_empresa = None
        db_session.commit()
        db_session.refresh(tramite)

        assert documentos.nombre_para_cliente(tramite) == f"{tramite.servicio.nombre}.pdf"

    def test_reemplaza_los_caracteres_que_un_archivo_no_acepta(self, db_session, tramite):  # noqa: F811
        tramite.empresa.razon_social = 'Panadería: "El Sol" / Hnos.'
        db_session.commit()

        nombre = documentos.nombre_para_cliente(tramite)

        assert nombre.endswith(".pdf")
        assert not any(c in nombre for c in '\\/:*?"<>|')
        assert "Panadería El Sol Hnos" in nombre
        assert "  " not in nombre

    def test_limita_el_largo_del_nombre(self, db_session, tramite):  # noqa: F811
        tramite.empresa.razon_social = "A" * 100
        db_session.commit()

        nombre = documentos.nombre_para_cliente(tramite)

        assert nombre.endswith(".pdf")
        assert len(nombre) <= 124