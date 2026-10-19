"""Utilidades compartidas."""
import re

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}$")


def normalizar_rut(rut: str | None) -> str | None:
    """'12.345.678-k' -> '12345678-K'. Devuelve None si viene vacío."""
    if rut is None:
        return None
    limpio = rut.strip().replace(".", "").replace(" ", "").upper()
    return limpio or None


def rut_valido(rut: str) -> bool:
    """Valida formato y dígito verificador (módulo 11)."""
    m = re.fullmatch(r"(\d{1,8})-([\dK])", rut)
    if not m:
        return False
    cuerpo, dv = m.groups()
    suma, factor = 0, 2
    for d in reversed(cuerpo):
        suma += int(d) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    esperado = "0" if resto == 11 else "K" if resto == 10 else str(resto)
    return dv == esperado


def email_valido(email: str) -> bool:
    return bool(_EMAIL.match(email))
