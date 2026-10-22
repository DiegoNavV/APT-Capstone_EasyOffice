from datetime import datetime, timezone

import pytest

from app.services.psc import TIPO_SIMULADA, MockPSC, PSCProvider

HASH = "ab" * 32
AHORA = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


def test_mock_marca_la_firma_como_simulada():
    resultado = MockPSC("secreto-de-prueba").firmar(HASH, "Juan Pérez", ahora=AHORA)
    assert resultado.tipo == TIPO_SIMULADA
    assert resultado.proveedor == "mock"
    assert resultado.sha256_documento == HASH


def test_mismo_insumo_mismo_resultado():
    psc = MockPSC("secreto-de-prueba")
    assert psc.firmar(HASH, "Juan", ahora=AHORA) == psc.firmar(HASH, "Juan", ahora=AHORA)


def test_otro_secreto_otra_firma():
    a = MockPSC("uno").firmar(HASH, "Juan", ahora=AHORA)
    b = MockPSC("dos").firmar(HASH, "Juan", ahora=AHORA)
    assert a.firma != b.firma


@pytest.mark.parametrize("hash_malo", ["ABC", "zz" * 32, "ab" * 31, "AB" * 32])
def test_hash_invalido_rechazado(hash_malo):
    with pytest.raises(ValueError):
        MockPSC("secreto").firmar(hash_malo, "Juan", ahora=AHORA)


@pytest.mark.parametrize("firmante", ["", "   "])
def test_firmante_vacio_rechazado(firmante):
    with pytest.raises(ValueError):
        MockPSC("secreto").firmar(HASH, firmante, ahora=AHORA)


def test_secreto_vacio_rechazado():
    with pytest.raises(ValueError):
        MockPSC("")


def test_la_interfaz_no_se_puede_instanciar():
    with pytest.raises(TypeError):
        PSCProvider()
