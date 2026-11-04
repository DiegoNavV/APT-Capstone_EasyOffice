"""
Aplicacion de los avisos de la API de firma al tramite: firmado, rechazado, repetidos y avisos raros.
La descarga del PDF firmado se reemplaza por una funcion falsa.
"""
import hashlib

import pytest

from app import aviso_firma, firma_client, models
from app.firma_client import ErrorFirma
from tests.test_valores_documento import tramite  # noqa: F401  (fixture)

ID_DOCUMENTO = "11111111-2222-3333-4444-555555555555"
PDF_SIN_FIRMAR = b"%PDF-1.4 sin firmar"
PDF_FIRMADO = b"%PDF-1.7 firmado"


@pytest.fixture(autouse=True)
def carpeta_documentos(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCUMENTOS_DIR", str(tmp_path / "documentos"))
    return tmp_path / "documentos"


@pytest.fixture()
def en_firma(db_session, seed, tramite, carpeta_documentos):  # noqa: F811
    """El tramite tal como queda despues de enviarlo a firma: PDF sin firmar generado, id de documento
    guardado y estado procesando_firma."""
    plantilla = models.PlantillaDocumento(
        id_servicio=seed["servicio"].id_servicio, nombre="Contrato", version=1,
        ruta_archivo="plantilla_prueba.docx", nombre_original="contrato.docx",
        hash_sha256="a" * 64, tamano_bytes=10, marcas=[], id_usuario_subio=seed["usuario"].id_usuario,
    )
    db_session.add(plantilla)
    db_session.flush()

    ruta = f"tramite_{tramite.id_tramite}.pdf"
    carpeta_documentos.mkdir(parents=True)
    (carpeta_documentos / ruta).write_bytes(PDF_SIN_FIRMAR)

    tramite.ruta_documento_generado = ruta
    tramite.id_plantilla = plantilla.id_plantilla
    tramite.documento_firma_id = ID_DOCUMENTO
    tramite.estado_actual = "procesando_firma"
    db_session.add(models.HistorialEstado(
        id_tramite=tramite.id_tramite, estado="procesando_firma", origen="cliente", comentario="Datos enviados.",
    ))
    db_session.commit()
    return tramite


@pytest.fixture()
def descarga(monkeypatch):
    """Reemplaza la descarga del PDF firmado. Devuelve la lista de ids pedidos."""
    pedidos = []

    def descargar(document_id):
        pedidos.append(document_id)
        return PDF_FIRMADO

    monkeypatch.setattr(firma_client, "descargar_firmado", descargar)
    return pedidos


def evento(tipo="document.completed", **extra):
    return {"event": tipo, "document_id": ID_DOCUMENTO, "external_ref": "LF-01-2026", **extra}


def estado(db_session, tramite):
    db_session.expire_all()
    return db_session.get(models.Tramite, tramite.id_tramite).estado_actual


def historial(db_session, tramite):
    return (
        db_session.query(models.HistorialEstado)
        .filter_by(id_tramite=tramite.id_tramite)
        .order_by(models.HistorialEstado.id_historial)
        .all()
    )


def pdf_guardado(carpeta, tramite):
    return (carpeta / f"tramite_{tramite.id_tramite}.pdf").read_bytes()


class TestCompletado:
    def test_guarda_la_copia_firmada_y_deja_el_tramite_firmado(self, db_session, en_firma, descarga, carpeta_documentos):
        assert aviso_firma.procesar_aviso(db_session, evento()) == aviso_firma.FIRMADO

        assert descarga == [ID_DOCUMENTO]
        assert pdf_guardado(carpeta_documentos, en_firma) == PDF_FIRMADO
        assert estado(db_session, en_firma) == "firmado"
        ultimo = historial(db_session, en_firma)[-1]
        assert (ultimo.estado, ultimo.origen, ultimo.id_usuario) == ("firmado", "sistema", None)

    def test_acepta_la_huella_correcta(self, db_session, en_firma, descarga):
        huella = hashlib.sha256(PDF_FIRMADO).hexdigest()
        assert aviso_firma.procesar_aviso(db_session, evento(signed_sha256=huella)) == aviso_firma.FIRMADO

    def test_huella_distinta_se_rechaza_y_no_cambia_nada(self, db_session, en_firma, descarga, carpeta_documentos):
        with pytest.raises(aviso_firma.AvisoNoProcesable):
            aviso_firma.procesar_aviso(db_session, evento(signed_sha256="0" * 64))

        assert estado(db_session, en_firma) == "procesando_firma"
        assert pdf_guardado(carpeta_documentos, en_firma) == PDF_SIN_FIRMAR

    def test_archivo_que_no_es_pdf_se_rechaza(self, db_session, en_firma, monkeypatch, carpeta_documentos):
        monkeypatch.setattr(firma_client, "descargar_firmado", lambda document_id: b"<html>error</html>")

        with pytest.raises(aviso_firma.AvisoNoProcesable):
            aviso_firma.procesar_aviso(db_session, evento())

        assert estado(db_session, en_firma) == "procesando_firma"
        assert pdf_guardado(carpeta_documentos, en_firma) == PDF_SIN_FIRMAR

    def test_si_la_api_no_entrega_el_pdf_el_error_sube_para_que_reintente(self, db_session, en_firma, monkeypatch):
        def cae(document_id):
            raise ErrorFirma("sin conexion", reintentable=True)

        monkeypatch.setattr(firma_client, "descargar_firmado", cae)

        with pytest.raises(ErrorFirma):
            aviso_firma.procesar_aviso(db_session, evento())

        assert estado(db_session, en_firma) == "procesando_firma"

    def test_aviso_repetido_no_descarga_ni_cambia_nada(self, db_session, en_firma, descarga):
        aviso_firma.procesar_aviso(db_session, evento())
        resultado = aviso_firma.procesar_aviso(db_session, evento())

        assert resultado == aviso_firma.SIN_CAMBIOS
        assert descarga == [ID_DOCUMENTO]
        assert [h.estado for h in historial(db_session, en_firma)].count("firmado") == 1

    def test_tramite_entregado_no_se_toca(self, db_session, en_firma, descarga):
        db_session.add(models.HistorialEstado(
            id_tramite=en_firma.id_tramite, estado="entregado", origen="sistema", comentario="Descargado.",
        ))
        db_session.commit()

        assert aviso_firma.procesar_aviso(db_session, evento()) == aviso_firma.SIN_CAMBIOS
        assert descarga == []
        assert estado(db_session, en_firma) == "entregado"


class TestRechazado:
    def test_rechazo_del_cliente_deja_el_tramite_rechazado_con_el_motivo(self, db_session, en_firma):
        resultado = aviso_firma.procesar_aviso(
            db_session, evento("document.rejected", rejection_reason="Los datos están mal")
        )

        assert resultado == aviso_firma.RECHAZADO
        assert estado(db_session, en_firma) == "rechazado"
        ultimo = historial(db_session, en_firma)[-1]
        assert (ultimo.estado, ultimo.origen) == ("rechazado", "sistema")
        assert "Los datos están mal" in ultimo.comentario

    def test_rechazo_sin_motivo(self, db_session, en_firma):
        aviso_firma.procesar_aviso(db_session, evento("document.rejected"))
        assert "Motivo" not in historial(db_session, en_firma)[-1].comentario

    def test_motivo_muy_largo_se_recorta(self, db_session, en_firma):
        aviso_firma.procesar_aviso(db_session, evento("document.rejected", rejection_reason="x" * 2000))
    def test_plazo_vencido_deja_el_tramite_rechazado(self, db_session, en_firma):
        assert aviso_firma.procesar_aviso(db_session, evento("document.expired")) == aviso_firma.RECHAZADO

        assert estado(db_session, en_firma) == "rechazado"
        assert "plazo" in historial(db_session, en_firma)[-1].comentario

    def test_aviso_repetido_no_duplica_el_historial(self, db_session, en_firma):
        aviso_firma.procesar_aviso(db_session, evento("document.rejected"))
        resultado = aviso_firma.procesar_aviso(db_session, evento("document.rejected"))

        assert resultado == aviso_firma.SIN_CAMBIOS
        assert [h.estado for h in historial(db_session, en_firma)].count("rechazado") == 1

    def test_un_tramite_ya_firmado_no_se_rechaza(self, db_session, en_firma, descarga):
        aviso_firma.procesar_aviso(db_session, evento())

        assert aviso_firma.procesar_aviso(db_session, evento("document.rejected")) == aviso_firma.SIN_CAMBIOS
        assert estado(db_session, en_firma) == "firmado"


class TestAvisosQueSeIgnoran:
    def test_documento_desconocido(self, db_session, en_firma, descarga):
        aviso = {**evento(), "document_id": "00000000-0000-0000-0000-000000000000"}

        assert aviso_firma.procesar_aviso(db_session, aviso) == aviso_firma.IGNORADO
        assert descarga == []
        assert estado(db_session, en_firma) == "procesando_firma"

    def test_folio_que_no_coincide(self, db_session, en_firma, descarga):
        aviso = {**evento(), "external_ref": "XX-99-2026"}

        assert aviso_firma.procesar_aviso(db_session, aviso) == aviso_firma.IGNORADO
        assert descarga == []

    def test_cancelado_lo_hace_el_propio_crm(self, db_session, en_firma):
        assert aviso_firma.procesar_aviso(db_session, evento("document.cancelled")) == aviso_firma.IGNORADO
        assert estado(db_session, en_firma) == "procesando_firma"

    @pytest.mark.parametrize("aviso", [{}, {"event": "document.completed"}, {"document_id": ID_DOCUMENTO},
                                       {"event": 5, "document_id": ID_DOCUMENTO},
                                       {"event": "document.completed", "document_id": 7}])
    def test_aviso_incompleto_o_con_tipos_raros(self, db_session, en_firma, descarga, aviso):
        assert aviso_firma.procesar_aviso(db_session, aviso) == aviso_firma.IGNORADO
        assert descarga == []