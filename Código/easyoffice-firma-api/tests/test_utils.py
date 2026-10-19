import pytest

from app.utils import email_valido, normalizar_rut, rut_valido


@pytest.mark.parametrize("rut, ok", [
    ("12345678-5", True),
    ("76543210-3", True),
    ("11111111-1", True),
    ("12345678-9", False),
    ("1234567", False),
    ("abc-1", False),
])
def test_rut(rut, ok):
    assert rut_valido(rut) is ok


def test_rut_con_k():
    # 10000013-K es un RUT con dígito verificador K.
    assert rut_valido(normalizar_rut("10.000.013-k"))


def test_normalizar_rut():
    assert normalizar_rut(" 12.345.678-k ") == "12345678-K"
    assert normalizar_rut("") is None


@pytest.mark.parametrize("correo, ok", [
    ("juan@cliente.cl", True),
    ("a.b+c@sub.dominio.com", True),
    ("sin-arroba.cl", False),
    ("a@b", False),
])
def test_email(correo, ok):
    assert email_valido(correo) is ok
