import pytest

from app.services.cifrado import ErrorDescifrado, cifrar, descifrar

CLAVE = "11" * 32
OTRA_CLAVE = "22" * 32


def test_ida_y_vuelta():
    cifrado = cifrar("secreto-de-cliente", CLAVE, asociado="cliente-1")
    assert cifrado.startswith("v1:")
    assert "secreto-de-cliente" not in cifrado
    assert descifrar(cifrado, CLAVE, asociado="cliente-1") == "secreto-de-cliente"


def test_nonce_distinto_en_cada_cifrado():
    assert cifrar("mismo texto", CLAVE) != cifrar("mismo texto", CLAVE)


def test_clave_incorrecta_falla():
    cifrado = cifrar("dato", CLAVE)
    with pytest.raises(ErrorDescifrado):
        descifrar(cifrado, OTRA_CLAVE)


def test_contexto_distinto_falla():
    cifrado = cifrar("dato", CLAVE, asociado="cliente-1")
    with pytest.raises(ErrorDescifrado):
        descifrar(cifrado, CLAVE, asociado="cliente-2")


def test_valor_alterado_falla():
    cifrado = cifrar("dato", CLAVE)
    cambiado = cifrado[:-2] + ("AA" if not cifrado.endswith("AA") else "BB")
    with pytest.raises(ErrorDescifrado):
        descifrar(cambiado, CLAVE)


@pytest.mark.parametrize("valor", ["sin-prefijo", "v1:%%%", "v1:AAAA"])
def test_formato_invalido(valor):
    with pytest.raises(ErrorDescifrado):
        descifrar(valor, CLAVE)


def test_texto_vacio_no_se_cifra():
    with pytest.raises(ValueError):
        cifrar("", CLAVE)


@pytest.mark.parametrize("clave", ["11" * 31, "zz" * 32])
def test_clave_de_largo_o_formato_incorrecto(clave):
    with pytest.raises(ValueError):
        cifrar("dato", clave)
