"""
Vista previa del borrador para el cliente (pública, con su código). Se prueba lo importante: no guarda nada, enmascara lo ya
registrado, comparte las reglas del envío, NUNCA entrega un PDF (solo imágenes con marca de agua), no filtra detalles técnicos
y se frena con los límites.

LibreOffice y pdftoppm se reemplazan por funciones falsas (el enmascarado se revisa en el .docx que recibe el conversor, antes
de pasar a imágenes); la marca de agua sí es la real. La prueba de punta a punta con pdftoppm real se omite si no está instalado
(en Docker sí está).
"""
import base64
import itertools
import logging
import shutil
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from app import convertir_pdf, marca_agua, models, vista_previa
from app.convertir_pdf import ErrorConversion, ServidorOcupado
from app.seguridad import limiter
from tests.test_cliente_envio import CAMPOS_CONTRATO, CONTRATO, empresa_completa, tramite_de  # noqa: F401
from tests.test_plantillas import carpeta_plantillas, docx_con, headers_admin, subir  # noqa: F401
from tests.test_rellenar_docx import textos_de

PDF_FALSO = b"%PDF-1.4 borrador de prueba"
PLANTILLA = "{{FOLIO}} | {{RAZON_SOCIAL}} | {{RUT}} | {{MAIL}} | {{CELULAR_8_DIGITOS}} | {{GIRO_PRINCIPAL}}"
PREFIJO = "data:image/jpeg;base64,"
TEXTO_NEGRO = (40, 40, 360, 80)          # zona "con texto" de la página falsa


def pagina_falsa(ancho: int = 400, alto: int = 520) -> bytes:
    """Página blanca con un bloque negro que hace de texto, como la entregaría pdftoppm."""
    imagen = Image.new("RGB", (ancho, alto), "white")
    ImageDraw.Draw(imagen).rectangle(TEXTO_NEGRO, fill="black")
    buf = BytesIO()
    imagen.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


PAGINAS_FALSAS = [pagina_falsa(), pagina_falsa()]


@pytest.fixture(autouse=True)
def entorno(monkeypatch):
    """Sin LibreOffice real: se guarda el .docx recibido y se devuelve un PDF falso."""
    for nombre in ("MARCA_POR_DEFECTO", "BANCO_TEXTO_EASY_OFFICE", "BANCO_TEXTO_INOFFICE"):
        monkeypatch.delenv(nombre, raising=False)      # las pruebas no dependen del .env de cada uno
    vista_previa.vaciar_cache()
    recibidos = []

    def falso(docx, espera_maxima=None):
        recibidos.append(docx)
        return PDF_FALSO

    monkeypatch.setattr("app.vista_previa.docx_a_pdf", falso)
    yield recibidos
    vista_previa.vaciar_cache()


@pytest.fixture(autouse=True)
def rasterizados(monkeypatch):
    """Sin pdftoppm real: se guarda el PDF recibido y se devuelven dos páginas falsas."""
    recibidos = []

    def falso(pdf, espera_maxima=None):
        recibidos.append(pdf)
        return list(PAGINAS_FALSAS)

    monkeypatch.setattr("app.vista_previa.pdf_a_imagenes", falso)
    return recibidos


@pytest.fixture()
def tramite(tramite_de, subir, db_session):  # noqa: F811
    t = tramite_de()
    t.folio = "LF-01-2026"
    db_session.commit()
    r = subir(docx_con(PLANTILLA), id_servicio=t.id_servicio)
    assert r.status_code == 201, r.text
    return t


def pedir(client, tramite, campos):
    return client.post(f"/api/tramites/codigo/{tramite.codigo_seguimiento}/vista-previa", json={"campos": campos})


def texto(docx: bytes) -> str:
    return " ".join(textos_de(docx))


def imagenes_de(respuesta) -> list[Image.Image]:
    """Decodifica las páginas de la respuesta; falla si alguna no es un JPEG válido."""
    imagenes = []
    for pagina in respuesta.json()["paginas"]:
        assert pagina["imagen"].startswith(PREFIJO)
        crudo = base64.b64decode(pagina["imagen"][len(PREFIJO):], validate=True)
        assert crudo[:3] == b"\xff\xd8\xff"                       # firma JPEG
        with Image.open(BytesIO(crudo)) as img:
            img.verify()                                          # estructura válida
        img = Image.open(BytesIO(crudo))
        img.load()                                                # y decodifica entera
        assert img.format == "JPEG"
        imagenes.append(img.convert("RGB"))
    return imagenes


def pixeles_rojos(imagen: Image.Image) -> int:
    return sum(1 for r, g, b in imagen.convert("RGB").getdata() if r > g + 40 and r > b + 40)


# ---------- respuesta: imágenes, nunca PDF ----------

def test_borrador_con_los_datos_escritos(client, tramite, entorno):
    r = pedir(client, tramite, CAMPOS_CONTRATO)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"
    cuerpo = r.json()
    assert cuerpo["total"] == 2 and [p["numero"] for p in cuerpo["paginas"]] == [1, 2]
    t = texto(entorno[0])
    assert "LF-01-2026" in t and "COMERCIAL PRUEBA SPA" in t and "76.123.456-0" in t
    assert "ana@prueba.cl" in t and "912345678" in t and "VENTA DE ARTÍCULOS DE OFICINA" in t


def test_nunca_entrega_un_pdf(client, tramite):
    r = pedir(client, tramite, CAMPOS_CONTRATO)
    assert r.status_code == 200
    assert "pdf" not in r.headers["content-type"]
    assert "content-disposition" not in r.headers
    assert b"%PDF" not in r.content
    for pagina in r.json()["paginas"]:
        assert not base64.b64decode(pagina["imagen"][len(PREFIJO):]).startswith(b"%PDF")


def test_cada_pagina_es_un_jpeg_valido(client, tramite):
    imagenes = imagenes_de(pedir(client, tramite, CAMPOS_CONTRATO))
    assert len(imagenes) == 2 and all(img.size == (400, 520) for img in imagenes)


def test_el_pdf_armado_es_el_que_se_pasa_a_imagenes(client, tramite, rasterizados):
    pedir(client, tramite, CAMPOS_CONTRATO)
    assert rasterizados == [PDF_FALSO]


def test_la_marca_de_agua_queda_en_la_imagen(client, tramite):
    sin_marca = Image.open(BytesIO(PAGINAS_FALSAS[0])).convert("RGB")
    con_marca = imagenes_de(pedir(client, tramite, CAMPOS_CONTRATO))[0]
    rojos = pixeles_rojos(con_marca)
    assert pixeles_rojos(sin_marca) == 0
    assert rojos > 0.02 * con_marca.width * con_marca.height         # repartida por la página, no un punto
    # cubre la página entera: hay rojo en la mitad de arriba y en la de abajo
    mitad = con_marca.height // 2
    assert pixeles_rojos(con_marca.crop((0, 0, con_marca.width, mitad))) > 0
    assert pixeles_rojos(con_marca.crop((0, mitad, con_marca.width, con_marca.height))) > 0


def test_la_marca_de_agua_deja_leer_el_texto(client, tramite):
    con_marca = imagenes_de(pedir(client, tramite, CAMPOS_CONTRATO))[0]
    zona = con_marca.crop(TEXTO_NEGRO).convert("L")
    promedio = sum(zona.getdata()) / (zona.width * zona.height)
    assert promedio < 90                       # el "texto" negro sigue oscuro bajo la marca


def test_no_guarda_nada(client, tramite, db_session):
    antes = db_session.query(models.HistorialEstado).count()
    assert pedir(client, tramite, CAMPOS_CONTRATO).status_code == 200
    db_session.expire_all()
    t = db_session.get(models.Tramite, tramite.id_tramite)
    assert t.estado_actual == "generado" and t.datos_empresa is None and t.id_empresa is None
    assert t.ruta_documento_generado is None
    assert db_session.query(models.Empresa).count() == 0
    assert db_session.query(models.HistorialEstado).count() == antes


# ---------- empresa ya registrada ----------

def test_lo_ya_registrado_sale_enmascarado(client, tramite, empresa_completa, db_session, entorno):  # noqa: F811
    tramite.id_empresa = empresa_completa.id_empresa
    db_session.commit()
    r = pedir(client, tramite, {})
    assert r.status_code == 200, r.text
    t = texto(entorno[0])
    for completo in ("ana@prueba.cl", "76.123.456-0", "76123456", "912345678", "COMERCIAL PRUEBA", "VENTA DE ARTÍCULOS"):
        assert completo not in t
    assert "DATO YA REGISTRADO" in t and "•" in t


def test_mezcla_de_registrado_y_escrito(client, tramite, db_session, entorno):
    empresa = models.Empresa(rut_empresa="76123456-0", razon_social="Comercial Prueba SpA", datos={})
    db_session.add(empresa)
    db_session.commit()
    tramite.id_empresa = empresa.id_empresa
    db_session.commit()
    escritos = {k: v for k, v in CAMPOS_CONTRATO.items() if k not in ("razon_social", "rut_empresa")}
    r = pedir(client, tramite, escritos)
    assert r.status_code == 200, r.text
    t = texto(entorno[0])
    assert "COMERCIAL PRUEBA" not in t and "76.123.456-0" not in t      # lo registrado, oculto
    assert "ana@prueba.cl" in t and "VENTA DE ARTÍCULOS DE OFICINA" in t  # lo escrito, completo


# ---------- mismas reglas que el envío ----------

def test_campo_ya_registrado_se_rechaza(client, tramite, empresa_completa, db_session):  # noqa: F811
    tramite.id_empresa = empresa_completa.id_empresa
    db_session.commit()
    r = pedir(client, tramite, {"email": "otro@correo.cl"})
    assert r.status_code == 422 and "email" in r.json()["detail"]["errores"]


def test_campos_con_errores_se_informan_todos_juntos(client, tramite):
    r = pedir(client, tramite, {**CAMPOS_CONTRATO, "rut_empresa": "1-9", "celular": "123"})
    assert r.status_code == 422
    assert set(r.json()["detail"]["errores"]) == {"rut_empresa", "celular"}


def test_faltan_campos_obligatorios(client, tramite):
    r = pedir(client, tramite, {})
    assert r.status_code == 422 and "razon_social" in r.json()["detail"]["errores"]


def test_no_acepta_campos_de_mas_en_el_cuerpo(client, tramite):
    r = client.post(
        f"/api/tramites/codigo/{tramite.codigo_seguimiento}/vista-previa",
        json={"campos": CAMPOS_CONTRATO, "consentimiento_aceptado": True},
    )
    assert r.status_code == 422


# ---------- cuándo no hay borrador ----------

def test_codigo_corto_y_codigo_inexistente(client, tramite):
    assert client.post("/api/tramites/codigo/ABC/vista-previa", json={"campos": {}}).status_code == 400
    assert client.post("/api/tramites/codigo/ZZZZZZZZ/vista-previa", json={"campos": {}}).status_code == 404


def test_tramite_que_ya_envio_sus_datos(client, tramite, db_session):
    tramite.estado_actual = "procesando_firma"
    db_session.commit()
    assert pedir(client, tramite, CAMPOS_CONTRATO).status_code == 409


def test_tramite_con_datos_de_empresa_ya_enviados(client, tramite, db_session):
    db_session.add(models.DatosEmpresaTramite(
        id_tramite=tramite.id_tramite, solicitante_es_representante=True, consentimiento_aceptado=True,
    ))
    db_session.commit()
    db_session.refresh(tramite)
    r = pedir(client, tramite, CAMPOS_CONTRATO)
    assert r.status_code == 409 and "paginas" not in r.text


def test_sin_plantilla_el_mensaje_es_simple(client, tramite, db_session):
    db_session.query(models.PlantillaDocumento).delete()
    db_session.commit()
    r = pedir(client, tramite, CAMPOS_CONTRATO)
    assert r.status_code == 409
    assert "plantilla" not in r.json()["detail"].lower()
    assert "puedes continuar" in r.json()["detail"].lower()


def test_si_falta_algo_del_agente_no_se_nombra_la_marca(client, tramite, db_session, subir):
    subir(docx_con("{{FOLIO}} {{BANCOLINK}}"), id_servicio=tramite.id_servicio)   # banco sin configurar
    r = pedir(client, tramite, CAMPOS_CONTRATO)
    assert r.status_code == 409 and "BANCOLINK" not in r.text and "banco" not in r.text.lower()


# ---------- conversión, caché y cola ----------

def test_mismos_datos_no_se_convierten_dos_veces(client, tramite, entorno, rasterizados):
    primera = pedir(client, tramite, CAMPOS_CONTRATO)
    segunda = pedir(client, tramite, CAMPOS_CONTRATO)
    assert primera.status_code == segunda.status_code == 200
    assert primera.json() == segunda.json()
    assert len(entorno) == 1 and len(rasterizados) == 1           # la segunda salió de la caché
    assert pedir(client, tramite, {**CAMPOS_CONTRATO, "giro_principal": "Otro giro"}).status_code == 200
    assert len(entorno) == 2 and len(rasterizados) == 2           # datos distintos: se arma de nuevo


def test_la_cache_guarda_las_imagenes_ya_marcadas(client, tramite):
    r = pedir(client, tramite, CAMPOS_CONTRATO)
    (_vence, guardadas), = vista_previa._cache.values()
    enviadas = [base64.b64decode(p["imagen"][len(PREFIJO):]) for p in r.json()["paginas"]]
    assert list(guardadas) == enviadas and all(not g.startswith(b"%PDF") for g in guardadas)
    assert vista_previa._cache_bytes == sum(len(g) for g in guardadas)


def test_la_cache_vence(client, tramite, entorno, monkeypatch):
    assert pedir(client, tramite, CAMPOS_CONTRATO).status_code == 200
    monkeypatch.setattr(vista_previa, "CACHE_SEGUNDOS", -1)
    vista_previa.vaciar_cache()
    assert pedir(client, tramite, CAMPOS_CONTRATO).status_code == 200      # se guarda ya vencida
    assert pedir(client, tramite, CAMPOS_CONTRATO).status_code == 200
    assert len(entorno) == 3
    assert vista_previa._cache_bytes == sum(sum(map(len, p)) for _v, p in vista_previa._cache.values())


def test_la_cache_no_crece_sin_limite(client, tramite, monkeypatch):
    monkeypatch.setattr(vista_previa, "CACHE_MAXIMO", 3)
    for n in range(6):
        assert pedir(client, tramite, {**CAMPOS_CONTRATO, "giro_principal": f"Giro {n}"}).status_code == 200
    assert len(vista_previa._cache) == 3


def test_la_cache_respeta_el_tope_de_bytes_y_saca_lo_mas_antiguo(monkeypatch):
    monkeypatch.setattr(vista_previa, "CACHE_MAXIMO_BYTES", 250)
    for n in range(4):
        vista_previa._cache_guardar(f"c{n}", (b"x" * 60, b"y" * 40))          # 100 bytes cada una
    assert list(vista_previa._cache) == ["c2", "c3"]                           # salieron c0 y c1
    assert vista_previa._cache_bytes == 200
    vista_previa._cache_leer("c2")                                              # c2 pasa a ser la más reciente
    vista_previa._cache_guardar("c4", (b"z" * 100,))
    assert list(vista_previa._cache) == ["c2", "c4"] and vista_previa._cache_bytes == 200


def test_una_entrada_mas_grande_que_el_tope_no_se_guarda(monkeypatch):
    monkeypatch.setattr(vista_previa, "CACHE_MAXIMO_BYTES", 50)
    vista_previa._cache_guardar("grande", (b"x" * 51,))
    assert len(vista_previa._cache) == 0 and vista_previa._cache_bytes == 0


def test_la_cache_de_bytes_tambien_funciona_por_el_endpoint(client, tramite, monkeypatch):
    peso = sum(len(marca_agua.marcar(p)) for p in PAGINAS_FALSAS)            # un borrador de 2 páginas
    monkeypatch.setattr(vista_previa, "CACHE_MAXIMO_BYTES", int(peso * 2.5))   # caben ~2 borradores
    for n in range(4):
        assert pedir(client, tramite, {**CAMPOS_CONTRATO, "giro_principal": f"Giro {n}"}).status_code == 200
    assert len(vista_previa._cache) == 2
    assert vista_previa._cache_bytes <= vista_previa.CACHE_MAXIMO_BYTES


def test_cola_llena_responde_503_con_reintento(client, tramite, monkeypatch):
    def ocupado(docx, espera_maxima=None):
        raise ServidorOcupado("Hay muchas solicitudes en este momento. Intenta de nuevo en unos segundos.")

    monkeypatch.setattr("app.vista_previa.docx_a_pdf", ocupado)
    r = pedir(client, tramite, CAMPOS_CONTRATO)
    assert r.status_code == 503 and r.headers["retry-after"] == "5"


def test_cola_llena_al_pasar_a_imagenes_tambien_es_503(client, tramite, monkeypatch):
    def ocupado(pdf, espera_maxima=None):
        raise ServidorOcupado("Hay muchas solicitudes en este momento. Intenta de nuevo en unos segundos.")

    monkeypatch.setattr("app.vista_previa.pdf_a_imagenes", ocupado)
    r = pedir(client, tramite, CAMPOS_CONTRATO)
    assert r.status_code == 503 and r.headers["retry-after"] == "5"
    assert len(vista_previa._cache) == 0


def test_la_espera_en_cola_es_corta(client, tramite, monkeypatch):
    pedidos = []
    monkeypatch.setattr("app.vista_previa.docx_a_pdf", lambda docx, espera_maxima=None: pedidos.append(espera_maxima) or PDF_FALSO)
    monkeypatch.setattr(
        "app.vista_previa.pdf_a_imagenes",
        lambda pdf, espera_maxima=None: pedidos.append(espera_maxima) or list(PAGINAS_FALSAS),
    )
    pedir(client, tramite, CAMPOS_CONTRATO)
    assert pedidos == [vista_previa.ESPERA_MAXIMA_SEGUNDOS] * 2 and vista_previa.ESPERA_MAXIMA_SEGUNDOS <= 10


def test_falla_la_conversion_sin_filtrar_detalles(client, tramite, monkeypatch):
    def fallar(docx, espera_maxima=None):
        raise ErrorConversion("No se pudo convertir el documento a PDF.", detalle="secreto interno")

    monkeypatch.setattr("app.vista_previa.docx_a_pdf", fallar)
    r = pedir(client, tramite, CAMPOS_CONTRATO)
    assert r.status_code == 502 and "secreto interno" not in r.text
    assert r.json()["detail"].startswith("No pudimos preparar el borrador")


def test_demasiadas_paginas_es_error_y_queda_en_el_registro(client, tramite, monkeypatch, caplog):
    def largo(pdf, espera_maxima=None):
        raise ErrorConversion("El documento tiene demasiadas páginas para mostrarlo.", detalle="más de 10 páginas")

    monkeypatch.setattr("app.vista_previa.pdf_a_imagenes", largo)
    with caplog.at_level(logging.ERROR, logger="easyoffice.vista_previa"):
        r = pedir(client, tramite, CAMPOS_CONTRATO)
    assert r.status_code == 502 and "páginas" not in r.text and "paginas" not in r.text
    assert r.json()["detail"].startswith("No pudimos preparar el borrador")
    assert "más de 10 páginas" in caplog.text
    assert len(vista_previa._cache) == 0


def test_imagen_corrupta_da_502_generico(client, tramite, monkeypatch):
    monkeypatch.setattr("app.vista_previa.pdf_a_imagenes", lambda pdf, espera_maxima=None: [b"\xff\xd8\xff no es jpeg"])
    r = pedir(client, tramite, CAMPOS_CONTRATO)
    assert r.status_code == 502 and r.json()["detail"].startswith("No pudimos preparar el borrador")


# ---------- de punta a punta con pdftoppm real ----------

@pytest.mark.skipif(shutil.which("pdftoppm") is None, reason="pdftoppm no instalado (paquete poppler-utils)")
def test_con_pdftoppm_real_la_marca_agrega_rojo(client, tramite, monkeypatch):
    # PDF real de 2 páginas carta (612x792 pt) hecho con Pillow; LibreOffice sigue reemplazado.
    hojas = [Image.new("RGB", (612, 792), "white") for _ in range(2)]
    for hoja in hojas:
        ImageDraw.Draw(hoja).rectangle((60, 60, 550, 100), fill="black")
    buf = BytesIO()
    hojas[0].save(buf, format="PDF", save_all=True, append_images=hojas[1:], resolution=72)
    pdf_real = buf.getvalue()
    monkeypatch.setattr("app.vista_previa.docx_a_pdf", lambda docx, espera_maxima=None: pdf_real)
    monkeypatch.setattr("app.vista_previa.pdf_a_imagenes", convertir_pdf.pdf_a_imagenes)

    r = pedir(client, tramite, CAMPOS_CONTRATO)
    assert r.status_code == 200, r.text
    imagenes = imagenes_de(r)
    sin_marca = [Image.open(BytesIO(j)).convert("RGB") for j in convertir_pdf.pdf_a_imagenes(pdf_real)]
    assert r.json()["total"] == 2 and len(imagenes) == 2
    for con, sin in zip(imagenes, sin_marca):
        assert abs(con.width - 935) <= 2 and abs(con.height - 1210) <= 2     # carta a 110 dpi
        assert con.size == sin.size
        assert pixeles_rojos(sin) == 0 and pixeles_rojos(con) > 0.02 * con.width * con.height


# ---------- límites de uso ----------

class TestLimites:
    @pytest.fixture()
    def limite_activo(self):
        limiter.reset()
        limiter.enabled = True
        yield
        limiter.enabled = False
        limiter.reset()

    def test_por_codigo_10_por_hora(self, client, tramite, limite_activo):
        respuestas = [pedir(client, tramite, CAMPOS_CONTRATO).status_code for _ in range(11)]
        assert respuestas[:10] == [200] * 10 and respuestas[10] == 429

    def test_otro_codigo_no_se_ve_afectado(self, client, tramite, limite_activo):
        for _ in range(11):
            pedir(client, tramite, CAMPOS_CONTRATO)
        r = client.post("/api/tramites/codigo/ZZZZZZZZ/vista-previa", json={"campos": {}})
        assert r.status_code == 404                                       # no 429

    def test_por_ip_15_por_minuto(self, client, limite_activo):
        codigos = [f"ABCDE{n:03d}" for n in range(16)]
        respuestas = [client.post(f"/api/tramites/codigo/{c}/vista-previa", json={"campos": {}}).status_code for c in codigos]
        assert respuestas[:15] == [404] * 15 and respuestas[15] == 429

    def test_total_30_por_minuto_aunque_cambie_la_ip(self, client, limite_activo, monkeypatch):
        ips = itertools.count(1)
        monkeypatch.setattr("app.routers.tramites.get_remote_address", lambda request: f"10.0.0.{next(ips)}")
        codigos = [f"ABCDEF{n:02d}" for n in range(31)]
        respuestas = [client.post(f"/api/tramites/codigo/{c}/vista-previa", json={"campos": {}}).status_code for c in codigos]
        assert respuestas[:30] == [404] * 30 and respuestas[30] == 429
