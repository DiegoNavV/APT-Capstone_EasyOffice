"""
Cifrado de secretos en reposo con AES-256-GCM.

Formato del valor cifrado (texto): "v1:" + base64(nonce de 12 bytes + texto cifrado + etiqueta).
La clave maestra viene de MASTER_KEY_HEX (32 bytes en hex). Nunca se guarda en la base de datos.
Cada cifrado usa un nonce aleatorio nuevo.

El parámetro `asociado` es un contexto (por ejemplo, el id del cliente): queda autenticado
pero no cifrado. Si cambia, el descifrado falla.
"""
import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIJO = "v1:"
LARGO_NONCE = 12


class ErrorDescifrado(Exception):
    """El valor no se pudo descifrar: formato inválido, clave incorrecta o dato alterado."""


def _clave(master_key_hex: str) -> bytes:
    clave = bytes.fromhex(master_key_hex)
    if len(clave) != 32:
        raise ValueError("La clave maestra debe tener 32 bytes (64 caracteres hex).")
    return clave


def cifrar(texto: str, master_key_hex: str, asociado: str = "") -> str:
    if not texto:
        raise ValueError("No se puede cifrar un texto vacío.")
    nonce = os.urandom(LARGO_NONCE)
    cifrado = AESGCM(_clave(master_key_hex)).encrypt(
        nonce, texto.encode("utf-8"), asociado.encode("utf-8")
    )
    return PREFIJO + base64.b64encode(nonce + cifrado).decode("ascii")


def descifrar(valor: str, master_key_hex: str, asociado: str = "") -> str:
    if not valor.startswith(PREFIJO):
        raise ErrorDescifrado("Formato desconocido.")
    try:
        crudo = base64.b64decode(valor[len(PREFIJO):], validate=True)
    except ValueError as exc:
        raise ErrorDescifrado("Base64 inválido.") from exc
    if len(crudo) <= LARGO_NONCE:
        raise ErrorDescifrado("Valor demasiado corto.")
    nonce, cifrado = crudo[:LARGO_NONCE], crudo[LARGO_NONCE:]
    try:
        original = AESGCM(_clave(master_key_hex)).decrypt(nonce, cifrado, asociado.encode("utf-8"))
    except InvalidTag as exc:
        raise ErrorDescifrado("No se pudo descifrar: clave incorrecta o dato alterado.") from exc
    return original.decode("utf-8")
