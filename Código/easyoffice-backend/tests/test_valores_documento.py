"""Datos que se escriben en las marcas del documento a partir de un trámite."""
from datetime import date

import pytest

from app import models
from app.marcas_documento import CATALOGO_MARCAS
from app.rellenar_docx import FaltanDatos, rellenar_docx
from app.valores_documento import (
    fecha_larga, marca_del_tramite, precio_con_miles, rut_con_puntos, texto_bancario, valores_para_documento,
)
from tests.test_marcas_documento import hacer_docx, parrafo_texto
from tests.test_rellenar_docx import textos_de

BANCO_EO = "25770158951 del Banco Estado, a nombre de su titular EASY OFFICE SpA, R.U.T. 76.767.272-1"


@pytest.fixture(autouse=True)
def sin_variables_de_entorno(monkeypatch):
    for nombre in ("MARCA_POR_DEFECTO", "BANCO_TEXTO_EASY_OFFICE", "BANCO_TEXTO_INOFFICE"):
        monkeypatch.delenv(nombre, raising=False)


@pytest.fixture()
def tramite(db_session, seed):
    sucursal = models.Sucursal(
        iniciales="LF", nombre="La Florida", direccion="Vicuña Mackenna Poniente #7255, Oficina 707",
        comuna="La Florida", region="Metropolitana", rol_propiedad="271-147",
    )
    cliente = models.Cliente(nombre="Oscar Contreras")
    empresa = models.Empresa(
        rut_empresa="78526673-0", razon_social="Altus and Company Co. SpA",
        datos={
            "giro_principal": "Comercializadora", "representante_legal": "Oscar Contreras Benavides",
            "rut_representante": "14144266-K", "domicilio_representante": "Panamericana Norte 213",
            "comuna_representante": "Til Til", "region_representante": "Metropolitana",
            "email": "contacto@altus.cl", "celular": "932365169",
            "fecha_escritura": "2026-10-02", "notaria": "www.tuempresaenundia.cl",
        },
    )
    db_session.add_all([sucursal, cliente, empresa])
    db_session.commit()
    t = models.Tramite(
        id_cliente=cliente.id_cliente, id_servicio=seed["servicio"].id_servicio, id_empresa=empresa.id_empresa,
        id_sucursal=sucursal.id_sucursal, folio="LF-01-2026", codigo_seguimiento="ABCD2345",
        condiciones={
            "servicios": [
                {"id_servicio_ofrecido": 1, "nombre": "Creación de empresas", "descripcion": "*Creación", "precio": 59990, "ciclo_pago": "ANUAL"},
                {"id_servicio_ofrecido": 2, "nombre": "Domicilio tributario", "descripcion": None, "precio": 1234567, "ciclo_pago": "ÚNICO"},
            ],
            "duracion_meses": 12, "fecha_inicio": "2026-10-02", "fecha_vencimiento": "2027-10-01",
        },
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


# ---------- formatos ----------

def test_fecha_larga():
    assert fecha_larga("2026-10-02") == "02 DE OCTUBRE DE 2026"
    assert fecha_larga(date(2027, 1, 15), mayusculas=False) == "15 de enero de 2027"
    assert fecha_larga(None) is None and fecha_larga("no es fecha") is None


def test_rut_con_puntos():
    assert rut_con_puntos("76123456-0") == "76.123.456-0"
    assert rut_con_puntos("14144266-k") == "14.144.266-K"
    assert rut_con_puntos("9876543-2") == "9.876.543-2"
    assert rut_con_puntos("raro") == "raro" and rut_con_puntos(None) is None


def test_precio_con_miles():
    assert precio_con_miles(59990) == "59.990"
    assert precio_con_miles(1234567) == "1.234.567"
    assert precio_con_miles(0) == "0" and precio_con_miles(None) is None


# ---------- valores del trámite ----------

def test_las_claves_son_exactamente_las_del_catalogo(tramite):
    assert set(valores_para_documento(tramite)) == set(CATALOGO_MARCAS)


def test_valores_de_un_tramite_completo(tramite, monkeypatch):
    monkeypatch.setenv("BANCO_TEXTO_EASY_OFFICE", BANCO_EO)
    v = valores_para_documento(tramite)
    assert v["FOLIO"] == "LF-01-2026"
    assert v["RAZON_SOCIAL"] == "ALTUS AND COMPANY CO. SPA"
    assert v["RUT"] == "78.526.673-0" and v["RUT_REP_LEGAL"] == "14.144.266-K"
    assert v["MAIL"] == "contacto@altus.cl"            # el correo no se pasa a mayúsculas
    assert v["CELULAR_8_DIGITOS"] == "932365169"
    assert v["FECHA_ESCRITURAESTATUTO_ACTUALIZADO"] == "02 de octubre de 2026"
    assert v["SITIONOTARIA"] == "WWW.TUEMPRESAENUNDIA.CL"
    assert v["SUCURSAL"] == "VICUÑA MACKENNA PONIENTE #7255, OFICINA 707"
    assert v["COMUNA_SUCURSAL"] == "LA FLORIDA" and v["REGION_SUCURSAL"] == "METROPOLITANA"
    assert v["ROL_PROPIEDAD"] == "271-147"
    assert v["FECHA_DE_INICIO"] == "02 DE OCTUBRE DE 2026" and v["VENCIMIENTO"] == "01 DE OCTUBRE DE 2027"
    assert v["DURACION"] == "(12 MESES)"
    assert v["BANCOLINK"] == BANCO_EO


def test_servicios_y_los_que_no_existen_quedan_vacios(tramite):
    v = valores_para_documento(tramite)
    assert (v["SERVICIO_1"], v["PRECIO_SS_1"], v["CICLO_PAGO_SS_1"], v["DESCRIPCION_SS_1"]) == (
        "CREACIÓN DE EMPRESAS", "59.990", "ANUAL", "*Creación")
    assert (v["SERVICIO_2"], v["PRECIO_SS_2"], v["CICLO_PAGO_SS_2"], v["DESCRIPCION_SS_2"]) == (
        "DOMICILIO TRIBUTARIO", "1.234.567", "ÚNICO", "")
    assert [v[f"{c}_3"] for c in ("SERVICIO", "DESCRIPCION_SS", "PRECIO_SS", "CICLO_PAGO_SS")] == ["", "", "", ""]


def test_un_mes_se_escribe_en_singular(tramite):
    tramite.condiciones = {**tramite.condiciones, "duracion_meses": 1}
    assert valores_para_documento(tramite)["DURACION"] == "(1 MES)"


def test_sin_condiciones_las_marcas_de_condiciones_quedan_sin_dato(tramite):
    tramite.condiciones = None
    v = valores_para_documento(tramite)
    for marca in ("FECHA_DE_INICIO", "VENCIMIENTO", "DURACION", "SERVICIO_1", "PRECIO_SS_3"):
        assert v[marca] is None


def test_empresa_con_datos_incompletos(tramite):
    tramite.empresa.datos = {"representante_legal": "Ana", "rut_representante": "11111111-1"}
    v = valores_para_documento(tramite)
    assert v["REPRESENTANTE_LEGAL"] == "ANA"
    assert v["GIRO_PRINCIPAL"] is None and v["MAIL"] is None and v["DOMIC_REP_LEGAL"] is None


# ---------- marca y datos bancarios ----------

def test_marca_por_defecto_y_cambios(tramite, monkeypatch):
    assert marca_del_tramite(tramite) == "EASY OFFICE"
    monkeypatch.setenv("MARCA_POR_DEFECTO", "INOFFICE")
    assert marca_del_tramite(tramite) == "INOFFICE"
    tramite.condiciones = {**tramite.condiciones, "marca": "EASY OFFICE"}
    assert marca_del_tramite(tramite) == "EASY OFFICE"      # la del trámite manda


def test_texto_bancario_por_marca(monkeypatch):
    monkeypatch.setenv("BANCO_TEXTO_EASY_OFFICE", "  banco A ")
    monkeypatch.setenv("BANCO_TEXTO_INOFFICE", "banco B")
    assert texto_bancario("EASY OFFICE") == "banco A"
    assert texto_bancario("inoffice") == "banco B"


def test_sin_texto_bancario_configurado(tramite, monkeypatch):
    assert valores_para_documento(tramite)["BANCOLINK"] is None
    monkeypatch.setenv("BANCO_TEXTO_EASY_OFFICE", "   ")
    assert valores_para_documento(tramite)["BANCOLINK"] is None


# ---------- empresa simulada (vista previa del borrador) ----------

def test_empresa_simulada_reemplaza_a_la_guardada(tramite):
    valores = valores_para_documento(tramite, empresa_simulada={
        "razon_social": "otra empresa spa", "rut_empresa": "76123456-0",
        "datos": {"giro_principal": "venta de pan", "email": "a@b.cl"},
    })
    assert valores["RAZON_SOCIAL"] == "OTRA EMPRESA SPA"
    assert valores["RUT"] == "76.123.456-0"
    assert valores["GIRO_PRINCIPAL"] == "VENTA DE PAN"
    assert valores["MAIL"] == "a@b.cl"
    assert valores["REPRESENTANTE_LEGAL"] is None       # lo que no viene en la simulada queda sin dato
    assert valores["FOLIO"] == "LF-01-2026"             # lo del trámite no cambia


def test_empresa_simulada_sirve_para_un_tramite_sin_empresa(tramite, db_session):
    tramite.id_empresa = None
    db_session.commit()
    db_session.refresh(tramite)
    assert valores_para_documento(tramite)["RUT"] is None
    valores = valores_para_documento(tramite, empresa_simulada={"razon_social": "x spa", "rut_empresa": "76123456-0", "datos": {}})
    assert valores["RAZON_SOCIAL"] == "X SPA"


def test_sin_empresa_simulada_todo_igual_que_antes(tramite):
    assert valores_para_documento(tramite)["RUT"] == "78.526.673-0"


# ---------- junto con rellenar_docx ----------

def test_documento_completo_con_todas_las_marcas(tramite, monkeypatch):
    monkeypatch.setenv("BANCO_TEXTO_EASY_OFFICE", BANCO_EO)
    cuerpo = "".join(parrafo_texto("{{%s}}" % marca) for marca in CATALOGO_MARCAS)
    salida = rellenar_docx(hacer_docx(cuerpo), valores_para_documento(tramite))
    assert not any("{{" in t for t in textos_de(salida))


def test_sin_banco_configurado_no_se_genera(tramite):
    with pytest.raises(FaltanDatos) as exc:
        rellenar_docx(hacer_docx(parrafo_texto("{{BANCOLINK}} {{FOLIO}}")), valores_para_documento(tramite))
    assert exc.value.marcas == ["BANCOLINK"]