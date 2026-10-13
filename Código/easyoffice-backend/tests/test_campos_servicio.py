"""
Definición y validación de los campos que el cliente completa con su código.
Son pruebas de funciones puras: no usan base de datos ni endpoints.
"""
from datetime import date, timedelta

import pytest

from app.campos_servicio import (
    CAMPOS_AUTORIZACION,
    CAMPOS_CONTRATO,
    ErrorCampos,
    _digito_verificador,
    campos_para_servicio,
    separar_para_guardar,
    validar_campos,
)

VALIDOS = {
    "razon_social": "Comercial   Prueba SpA",
    "rut_empresa": "76.123.456-0",
    "representante_legal": "Ana Pérez Soto",
    "rut_representante": "12.345.678-5",
    "domicilio_representante": "Los Aromos 123",
    "comuna_representante": "San Bernardo",
    "region_representante": "Metropolitana",
    "giro_principal": "Venta de artículos de oficina",
    "email": "Contacto@Prueba.CL",
    "celular": "+56 9 4983 6363",
    "fecha_escritura": "2024-03-15",
    "notaria": "Notaría Gómez",
}


def validar(**cambios):
    valores = {**VALIDOS, **cambios}
    return validar_campos(CAMPOS_CONTRATO, valores)


def errores_de(**cambios):
    with pytest.raises(ErrorCampos) as exc:
        validar(**cambios)
    return exc.value.errores


class TestDefinicion:
    def test_el_contrato_tiene_12_campos_con_claves_unicas(self):
        claves = [c.clave for c in CAMPOS_CONTRATO]
        assert len(claves) == 12
        assert len(set(claves)) == 12

    def test_cada_campo_tiene_su_columna_excel(self):
        columnas = [c.columna_excel for c in CAMPOS_CONTRATO]
        assert all(columnas)
        assert len(set(columnas)) == 12

    def test_solo_razon_social_y_rut_van_en_columna_propia(self):
        assert [c.clave for c in CAMPOS_CONTRATO if c.en_columna] == ["razon_social", "rut_empresa"]

    def test_la_autorizacion_tiene_4_campos(self):
        assert [c.clave for c in CAMPOS_AUTORIZACION] == [
            "razon_social",
            "rut_empresa",
            "representante_legal",
            "rut_representante",
        ]

    def test_los_campos_de_la_autorizacion_son_los_mismos_del_contrato(self):
        # Mismo objeto, no una copia: así nunca pueden quedar desalineados.
        contrato = {c.clave: c for c in CAMPOS_CONTRATO}
        assert all(contrato[c.clave] is c for c in CAMPOS_AUTORIZACION)

    @pytest.mark.parametrize("nombre", ["Contrato de servicio", "CONTRATO  DE SERVICIO", "contrato de servicio"])
    def test_contrato_usa_sus_12_campos(self, nombre):
        assert campos_para_servicio(nombre) is CAMPOS_CONTRATO

    @pytest.mark.parametrize(
        "nombre",
        ["Autorización de domicilio tributario", "AUTORIZACION DE  DOMICILIO TRIBUTARIO", "autorizacion de domicilio tributario"],
    )
    def test_autorizacion_usa_sus_4_campos(self, nombre):
        assert campos_para_servicio(nombre) is CAMPOS_AUTORIZACION

    def test_servicio_sin_formulario_devuelve_none(self):
        assert campos_para_servicio("Otro servicio") is None

    def test_el_dato_de_prueba_cubre_todos_los_campos(self):
        assert set(VALIDOS) == {c.clave for c in CAMPOS_CONTRATO}


class TestAutorizacion:
    """La autorización valida solo sus 4 campos; el resto no corresponde."""

    DATOS = {k: VALIDOS[k] for k in ("razon_social", "rut_empresa", "representante_legal", "rut_representante")}

    def test_acepta_sus_4_campos(self):
        limpios = validar_campos(CAMPOS_AUTORIZACION, self.DATOS)
        assert set(limpios) == set(self.DATOS)

    def test_rechaza_campos_que_no_le_corresponden(self):
        with pytest.raises(ErrorCampos) as exc:
            validar_campos(CAMPOS_AUTORIZACION, {**self.DATOS, "giro_principal": "Venta"})
        assert exc.value.errores == {"giro_principal": "Campo no permitido."}

    def test_separa_columnas_y_json(self):
        columnas, datos = separar_para_guardar(CAMPOS_AUTORIZACION, validar_campos(CAMPOS_AUTORIZACION, self.DATOS))
        assert set(columnas) == {"razon_social", "rut_empresa"}
        assert set(datos) == {"representante_legal", "rut_representante"}

    def test_se_puede_validar_solo_lo_que_falta(self):
        # Una empresa que ya hizo la autorización completa solo los 8 campos
        # restantes del contrato.
        claves_autorizacion = {c.clave for c in CAMPOS_AUTORIZACION}
        faltantes = tuple(c for c in CAMPOS_CONTRATO if c.clave not in claves_autorizacion)
        valores = {c.clave: VALIDOS[c.clave] for c in faltantes}
        assert len(faltantes) == 8
        assert set(validar_campos(faltantes, valores)) == {c.clave for c in faltantes}


class TestValidacionCorrecta:
    def test_devuelve_valores_limpios(self):
        limpios = validar()
        assert limpios["razon_social"] == "Comercial Prueba SpA"
        assert limpios["rut_empresa"] == "76123456-0"
        assert limpios["rut_representante"] == "12345678-5"
        assert limpios["celular"] == "949836363"
        assert limpios["email"] == "contacto@prueba.cl"
        assert limpios["fecha_escritura"] == "2024-03-15"

    def test_separa_columnas_y_json(self):
        columnas, datos = separar_para_guardar(CAMPOS_CONTRATO, validar())
        assert set(columnas) == {"razon_social", "rut_empresa"}
        assert len(datos) == 10
        assert "razon_social" not in datos


class TestRut:
    def test_acepta_sin_puntos_ni_guion(self):
        assert validar(rut_empresa="761234560")["rut_empresa"] == "76123456-0"

    def test_acepta_k_en_minuscula(self):
        cuerpo = next(str(n) for n in range(10_000_000, 10_000_100) if _digito_verificador(str(n)) == "K")
        assert validar(rut_empresa=f"{cuerpo}-k")["rut_empresa"] == f"{cuerpo}-K"

    def test_rechaza_digito_verificador_incorrecto(self):
        assert "rut_empresa" in errores_de(rut_empresa="76.123.456-7")

    @pytest.mark.parametrize("malo", ["abc", "1-9", "123456789012", "76.123.456-", "76.123.45a-0"])
    def test_rechaza_formatos_invalidos(self, malo):
        assert "rut_empresa" in errores_de(rut_empresa=malo)


class TestCelular:
    @pytest.mark.parametrize("valor", ["949836363", "9 4983 6363", "+56949836363", "56 9 4983 6363"])
    def test_acepta_formatos_habituales(self, valor):
        assert validar(celular=valor)["celular"] == "949836363"

    @pytest.mark.parametrize("malo", ["49836363", "849836363", "9498363631", "abc", "+57 9 4983 6363"])
    def test_rechaza_invalidos(self, malo):
        assert "celular" in errores_de(celular=malo)


class TestFechaYEmail:
    def test_rechaza_fecha_futura(self):
        manana = (date.today() + timedelta(days=1)).isoformat()
        assert "fecha_escritura" in errores_de(fecha_escritura=manana)

    @pytest.mark.parametrize("malo", ["15-03-2024", "2024/03/15", "ayer", "1850-01-01", "2024-02-30"])
    def test_rechaza_fechas_invalidas(self, malo):
        assert "fecha_escritura" in errores_de(fecha_escritura=malo)

    def test_acepta_hoy(self):
        hoy = date.today().isoformat()
        assert validar(fecha_escritura=hoy)["fecha_escritura"] == hoy

    @pytest.mark.parametrize("malo", ["sin-arroba", "a@", "@b.cl", "a b@c.cl"])
    def test_rechaza_correos_invalidos(self, malo):
        assert "email" in errores_de(email=malo)


class TestObligatoriosYExtras:
    @pytest.mark.parametrize("clave", [c.clave for c in CAMPOS_CONTRATO])
    def test_cada_campo_es_obligatorio(self, clave):
        valores = {k: v for k, v in VALIDOS.items() if k != clave}
        with pytest.raises(ErrorCampos) as exc:
            validar_campos(CAMPOS_CONTRATO, valores)
        assert list(exc.value.errores) == [clave]

    @pytest.mark.parametrize("vacio", ["", "   ", None])
    def test_vacio_cuenta_como_faltante(self, vacio):
        assert errores_de(notaria=vacio) == {"notaria": "Este campo es obligatorio."}

    def test_rechaza_campos_desconocidos(self):
        assert errores_de(rol_propiedad="123") == {"rol_propiedad": "Campo no permitido."}

    def test_rechaza_valores_que_no_son_texto(self):
        assert errores_de(giro_principal=123) == {"giro_principal": "Valor no válido."}

    def test_rechaza_textos_demasiado_largos(self):
        assert "razon_social" in errores_de(razon_social="x" * 201)

    def test_informa_todos_los_errores_a_la_vez(self):
        errores = errores_de(rut_empresa="1", celular="2", email="3")
        assert set(errores) == {"rut_empresa", "celular", "email"}