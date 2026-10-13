"""
Enmascarado de los datos ya registrados de una empresa.

El formulario del cliente nunca muestra completos los datos que ya están guardados: solo deja ver lo mínimo para que el cliente 
reconozca que son suyos.
El resultado tiene SIEMPRE el mismo largo, sin importar cuánto mida el dato original (así "peru@gmail.com" y "peruanolindo@hotmail.com" 
se ven igual y no se filtra el tamaño).

Esto es una pista para el cliente, no una medida de seguridad por sí sola: la protección real es que hace falta el 
código del trámite, que hay límite de peticiones y que solo se muestran datos de la empresa que el agente vinculó.
"""
from app.campos_servicio import Campo

PUNTO = "•"
TEXTO_REGISTRADO = "Dato ya registrado"


def _enmascarar_email(valor: str) -> str:
    local, separador, dominio = valor.rpartition("@")
    if not separador or not local or "." not in dominio:
        return TEXTO_REGISTRADO
    # Si la parte local es muy corta, dos letras revelarían casi todo el valor.
    visibles = 2 if len(local) > 3 else 1
    terminacion = dominio.rsplit(".", 1)[-1]
    return f"{local[:visibles]}{PUNTO * 5}@{PUNTO * 3}.{terminacion}"


def _enmascarar_celular(valor: str) -> str:
    # Se guarda como 9 dígitos que parten con 9.
    if len(valor) != 9 or not valor.isdigit():
        return TEXTO_REGISTRADO
    return f"9 {PUNTO * 4} {PUNTO * 2}{valor[-2:]}"


def _enmascarar_rut(valor: str) -> str:
    # Se guarda canónico: cuerpo-DV, p. ej. "76123456-0".
    cuerpo, separador, dv = valor.partition("-")
    if not separador or len(cuerpo) < 7 or len(dv) != 1:
        return TEXTO_REGISTRADO
    return f"{cuerpo[:2]}{PUNTO * 5}-{dv}"


def enmascarar(campo: Campo, valor) -> str:
    """Texto que se muestra al cliente para un dato ya registrado.

    - correo, celular y RUT: solo unos pocos caracteres, largo fijo.
    - fecha: se muestra completa. La fecha de la escritura o del estatuto consta en el Registro de Comercio (información pública) 
    y no identifica a nadie; verla completa le sirve al cliente para reconocer su empresa.
    - cualquier otro texto (razón social, nombres, domicilio, comuna, giro...): ni un carácter, solo que ya está registrado."""
    if not isinstance(valor, str) or not valor:
        return TEXTO_REGISTRADO
    if campo.tipo == "email":
        return _enmascarar_email(valor)
    if campo.tipo == "celular":
        return _enmascarar_celular(valor)
    if campo.tipo == "rut":
        return _enmascarar_rut(valor)
    if campo.tipo == "fecha":
        return valor
    return TEXTO_REGISTRADO