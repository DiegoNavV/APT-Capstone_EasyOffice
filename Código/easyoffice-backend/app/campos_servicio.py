"""
Campos que el cliente completa con su código de seguimiento.

Este módulo es el ÚNICO lugar donde se define qué datos pide cada servicio.
Si Easy Office corrige algo (un campo nuevo, uno que sobra, otra etiqueta), se edita aquí; el formulario del cliente y la validación 
del servidor se adaptan solos porque ambos leen esta misma definición.

Hoy hay dos servicios, cada uno con su lista:
  - Contrato de servicio: 12 campos.
  - Autorización de domicilio tributario: 4 campos, todos incluidos en los del contrato. Así, una empresa que ya hizo uno de los dos trámites 
    completa solo lo que le falta para el otro.

Cada campo guarda además `columna_excel`: el encabezado exacto de la planilla de Easy Office (MUESTRA_DE_CAMPOS_BB_DD_EASY_OFFICE.xlsx). 
Es la única correspondencia con sus planillas y se usará al generar el documento.
"""
import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from pydantic import EmailStr, TypeAdapter, ValidationError

from app.utils import normalizar_email, normalizar_rut

_EMAIL = TypeAdapter(EmailStr)


@dataclass(frozen=True)
class Campo:
    clave: str            # nombre interno y clave del JSON
    etiqueta: str         # texto que ve el cliente en el formulario
    tipo: str             # texto | rut | email | celular | fecha
    columna_excel: str    # encabezado exacto en la planilla de Easy Office
    en_columna: bool = False   # True: va en una columna propia de la tabla
    max_largo: int = 150
    ayuda: str = ""


# Los 12 datos que usa el contrato. Los dos primeros van en columnas propias
# de la tabla empresa (la lista del panel los muestra y los busca); el resto,
# en su JSON `datos`.
CAMPOS_CONTRATO: tuple[Campo, ...] = (
    Campo("razon_social", "Razón social", "texto", "RAZON SOCIAL", en_columna=True, max_largo=200),
    Campo("rut_empresa", "RUT de la empresa", "rut", "R.U.T.", en_columna=True, max_largo=15,
          ayuda="Ejemplo: 76.123.456-0"),
    Campo("representante_legal", "Nombre del representante legal", "texto", "REPRESENTANTE LEGAL"),
    Campo("rut_representante", "RUT del representante legal", "rut", "RUT REP. LEGAL", max_largo=15),
    Campo("domicilio_representante", "Domicilio del representante legal", "texto", "DOMIC. REP. LEGAL",
          max_largo=200, ayuda="Es el domicilio de la persona, no el de la empresa."),
    Campo("comuna_representante", "Comuna del representante legal", "texto", "COMUNA REP. LEGAL", max_largo=100),
    Campo("region_representante", "Región del representante legal", "texto", "REGIÓN REP. LEGAL", max_largo=100),
    Campo("giro_principal", "Giro principal", "texto", "GIRO PRINCIPAL", max_largo=200),
    Campo("email", "Correo electrónico", "email", "MAIL"),
    Campo("celular", "Celular", "celular", "CELULAR 8 DIGITOS", max_largo=20,
          ayuda="9 dígitos, parte con 9. Ejemplo: 9 1234 5678"),
    Campo("fecha_escritura", "Fecha de la escritura o del estatuto actualizado", "fecha",
          "FECHA ESCRITURA/ESTATUTO ACTUALIZADO", max_largo=10, ayuda="Formato AAAA-MM-DD"),
    Campo("notaria", "Notaría", "texto", "SITIO/NOTARÍA"),
)

# La autorización solo identifica a la empresa y a quien la representa.
_CLAVES_AUTORIZACION = {"razon_social", "rut_empresa", "representante_legal", "rut_representante"}
CAMPOS_AUTORIZACION: tuple[Campo, ...] = tuple(c for c in CAMPOS_CONTRATO if c.clave in _CLAVES_AUTORIZACION)

# Clave: nombre del servicio en minúsculas y sin tildes (ver _clave_servicio).
CAMPOS_POR_SERVICIO: dict[str, tuple[Campo, ...]] = {
    "contrato de servicio": CAMPOS_CONTRATO,
    "autorizacion de domicilio tributario": CAMPOS_AUTORIZACION,
}


def _clave_servicio(nombre: str) -> str:
    sin_tildes = unicodedata.normalize("NFD", nombre)
    sin_tildes = "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")
    return " ".join(sin_tildes.lower().split())


def campos_para_servicio(nombre_servicio: str) -> tuple[Campo, ...] | None:
    """Campos que usa ese servicio, o None si el servicio no tiene formulario
    definido (quien llame debe decidir qué responder en ese caso)."""
    return CAMPOS_POR_SERVICIO.get(_clave_servicio(nombre_servicio))


# ---------- Validación ----------

class ErrorCampos(Exception):
    """Uno o más campos no pasaron la validación: {clave: mensaje}."""

    def __init__(self, errores: dict[str, str]):
        super().__init__("Hay campos con errores.")
        self.errores = errores


def _digito_verificador(cuerpo: str) -> str:
    suma, factor = 0, 2
    for digito in reversed(cuerpo):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    return "0" if resto == 11 else "K" if resto == 10 else str(resto)


def _validar_rut(valor: str) -> str:
    """Devuelve el RUT en forma canónica: sin puntos y con guión (76123456-0)."""
    limpio = (normalizar_rut(valor) or "").replace("-", "")
    cuerpo, dv = limpio[:-1], limpio[-1:]
    if not (7 <= len(cuerpo) <= 8 and cuerpo.isdigit() and (dv.isdigit() or dv == "K")):
        raise ValueError("RUT no válido. Revisa el número.")
    if _digito_verificador(cuerpo) != dv:
        raise ValueError("RUT no válido. Revisa el dígito verificador.")
    return f"{cuerpo}-{dv}"


def _validar_celular(valor: str) -> str:
    digitos = re.sub(r"\D", "", valor)
    if len(digitos) == 11 and digitos.startswith("56"):
        digitos = digitos[2:]
    if not re.fullmatch(r"9\d{8}", digitos):
        raise ValueError("Celular no válido. Debe tener 9 dígitos y partir con 9.")
    return digitos


def _validar_fecha(valor: str) -> str:
    try:
        fecha = date.fromisoformat(valor.strip())
    except ValueError:
        raise ValueError("Fecha no válida. Usa el formato AAAA-MM-DD.") from None
    if fecha.year < 1900 or fecha > date.today():
        raise ValueError("La fecha no puede ser futura ni anterior a 1900.")
    return fecha.isoformat()


def _validar_email(valor: str) -> str:
    try:
        return _EMAIL.validate_python(normalizar_email(valor) or "")
    except ValidationError:
        raise ValueError("Correo no válido.") from None


def _validar_texto(valor: str) -> str:
    return " ".join(valor.split())


_VALIDADORES = {
    "texto": _validar_texto,
    "rut": _validar_rut,
    "email": _validar_email,
    "celular": _validar_celular,
    "fecha": _validar_fecha,
}


def validar_campos(definicion: tuple[Campo, ...], valores: dict) -> dict[str, str]:
    """Valida lo que envió el cliente contra la definición del servicio.

    Devuelve los valores ya limpios (RUT sin puntos, celular solo dígitos,
    espacios colapsados). Si algo falla, lanza ErrorCampos con TODOS los
    errores a la vez, para que el cliente corrija todo en una sola pasada."""
    errores: dict[str, str] = {}
    limpios: dict[str, str] = {}
    claves_validas = {c.clave for c in definicion}

    for extra in sorted(set(valores) - claves_validas):
        errores[extra] = "Campo no permitido."

    for campo in definicion:
        crudo = valores.get(campo.clave)
        if crudo is None or (isinstance(crudo, str) and not crudo.strip()):
            errores[campo.clave] = "Este campo es obligatorio."
            continue
        if not isinstance(crudo, str):
            errores[campo.clave] = "Valor no válido."
            continue
        if len(crudo.strip()) > campo.max_largo:
            errores[campo.clave] = f"Máximo {campo.max_largo} caracteres."
            continue
        try:
            limpio = _VALIDADORES[campo.tipo](crudo)
        except ValueError as exc:
            errores[campo.clave] = str(exc)
            continue
        if len(limpio) > campo.max_largo:
            errores[campo.clave] = f"Máximo {campo.max_largo} caracteres."
            continue
        limpios[campo.clave] = limpio

    if errores:
        raise ErrorCampos(errores)
    return limpios


def separar_para_guardar(definicion: tuple[Campo, ...], limpios: dict[str, str]) -> tuple[dict, dict]:
    """Divide los valores ya validados en (columnas propias, JSON `datos`)."""
    columnas = {c.clave: limpios[c.clave] for c in definicion if c.en_columna}
    datos = {c.clave: limpios[c.clave] for c in definicion if not c.en_columna}
    return columnas, datos