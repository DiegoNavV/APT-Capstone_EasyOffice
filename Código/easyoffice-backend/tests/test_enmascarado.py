"""
Enmascarado de los datos ya registrados: el cliente reconoce lo suyo sin ver el dato completo, y el resultado no depende del largo del original.
"""
import pytest

from app.campos_servicio import Campo
from app.enmascarado import TEXTO_REGISTRADO, enmascarar


def _campo(tipo):
    return Campo("x", "X", tipo, "X")


class TestCorreo:
    def test_largo_fijo_sin_importar_el_original(self):
        largo = enmascarar(_campo("email"), "peruanolindo@hotmail.com")
        corto = enmascarar(_campo("email"), "peru@gmail.com")
        assert largo == corto == "pe•••••@•••.com"

    def test_parte_local_corta_muestra_una_sola_letra(self):
        assert enmascarar(_campo("email"), "ab@x.cl") == "a•••••@•••.cl"

    def test_no_muestra_el_proveedor(self):
        assert "hotmail" not in enmascarar(_campo("email"), "peruanolindo@hotmail.com")

    @pytest.mark.parametrize("malo", ["sin-arroba", "@x.cl", "a@sinpunto"])
    def test_formato_inesperado_no_muestra_nada(self, malo):
        assert enmascarar(_campo("email"), malo) == TEXTO_REGISTRADO


class TestCelular:
    def test_muestra_solo_los_dos_ultimos_digitos(self):
        assert enmascarar(_campo("celular"), "912345678") == "9 •••• ••78"

    @pytest.mark.parametrize("malo", ["12345", "9123456789", "91234567a"])
    def test_formato_inesperado_no_muestra_nada(self, malo):
        assert enmascarar(_campo("celular"), malo) == TEXTO_REGISTRADO


class TestRut:
    @pytest.mark.parametrize("rut,esperado", [
        ("76123456-0", "76•••••-0"),
        ("9123456-7", "91•••••-7"),
        ("12345678-K", "12•••••-K"),
    ])
    def test_muestra_dos_digitos_y_el_verificador(self, rut, esperado):
        assert enmascarar(_campo("rut"), rut) == esperado

    def test_mismo_largo_con_cuerpo_de_7_u_8_digitos(self):
        assert len(enmascarar(_campo("rut"), "9123456-7")) == len(enmascarar(_campo("rut"), "76123456-0"))

    @pytest.mark.parametrize("malo", ["761234560", "123-4", "76123456-00"])
    def test_formato_inesperado_no_muestra_nada(self, malo):
        assert enmascarar(_campo("rut"), malo) == TEXTO_REGISTRADO


class TestFechaYTexto:
    def test_la_fecha_se_muestra_completa(self):
        assert enmascarar(_campo("fecha"), "2020-05-15") == "2020-05-15"

    def test_el_texto_no_muestra_ni_un_caracter(self):
        assert enmascarar(_campo("texto"), "Av. Siempre Viva 742") == TEXTO_REGISTRADO

    @pytest.mark.parametrize("tipo", ["texto", "email", "celular", "rut", "fecha"])
    @pytest.mark.parametrize("vacio", [None, "", 123])
    def test_valor_vacio_o_no_texto_no_muestra_nada(self, tipo, vacio):
        assert enmascarar(_campo(tipo), vacio) == TEXTO_REGISTRADO