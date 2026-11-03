"""
Verificacion de los avisos de la API de firma: solo pasa un aviso autentico y reciente.
"""
import hashlib
import hmac

import pytest

from app import firma_webhook

AHORA = 1_760_900_000.0
CUERPO = b'{"event":"document.completed","document_id":"6f1c","external_ref":"LF-0152-2026"}'


@pytest.fixture(autouse=True)
def secreto(monkeypatch):
    monkeypatch.setenv("FIRMA_WEBHOOK_SECRET", "secreto-de-prueba")


def firmado(cuerpo=CUERPO, timestamp=str(int(AHORA)), secreto=b"secreto-de-prueba"):
    """Lo mismo que calcula la API de firma al enviar el aviso."""
    return "sha256=" + hmac.new(secreto, timestamp.encode() + b"." + cuerpo, hashlib.sha256).hexdigest()


def test_aviso_autentico_y_reciente_es_valido():
    assert firma_webhook.aviso_valido(CUERPO, str(int(AHORA)), firmado(), ahora=AHORA)


def test_firma_calculada_coincide_con_la_de_la_api():
    assert firma_webhook.firmar(CUERPO, str(int(AHORA))) == firmado()


def test_cuerpo_alterado_se_rechaza():
    alterado = CUERPO.replace(b"completed", b"rejected")
    assert not firma_webhook.aviso_valido(alterado, str(int(AHORA)), firmado(), ahora=AHORA)


def test_firma_con_otro_secreto_se_rechaza():
    mala = firmado(secreto=b"otro-secreto")
    assert not firma_webhook.aviso_valido(CUERPO, str(int(AHORA)), mala, ahora=AHORA)


def test_marca_de_tiempo_distinta_a_la_firmada_se_rechaza():
    assert not firma_webhook.aviso_valido(CUERPO, str(int(AHORA) + 1), firmado(), ahora=AHORA)


@pytest.mark.parametrize("segundos", [301, -301, 3600, -86400])
def test_aviso_viejo_o_del_futuro_se_rechaza(segundos):
    marca = str(int(AHORA) + segundos)
    assert not firma_webhook.aviso_valido(CUERPO, marca, firmado(timestamp=marca), ahora=AHORA)


@pytest.mark.parametrize("segundos", [0, 299, -299, 300, -300])
def test_dentro_de_la_tolerancia_es_valido(segundos):
    marca = str(int(AHORA) + segundos)
    assert firma_webhook.aviso_valido(CUERPO, marca, firmado(timestamp=marca), ahora=AHORA)


@pytest.mark.parametrize("marca", ["", "abc", "12.5", None])
def test_marca_de_tiempo_invalida_se_rechaza_sin_lanzar(marca):
    assert not firma_webhook.aviso_valido(CUERPO, marca, firmado(), ahora=AHORA)


@pytest.mark.parametrize("firma", ["", None, "sha256=", "sin-prefijo", "sha256=ñandú-con-tilde-é"])
def test_firma_vacia_o_rara_se_rechaza_sin_lanzar(firma):
    assert not firma_webhook.aviso_valido(CUERPO, str(int(AHORA)), firma, ahora=AHORA)


def test_sin_ahora_usa_la_hora_real(monkeypatch):
    monkeypatch.setattr(firma_webhook.time, "time", lambda: AHORA)
    assert firma_webhook.aviso_valido(CUERPO, str(int(AHORA)), firmado())