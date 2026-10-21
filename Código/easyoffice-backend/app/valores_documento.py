"""
Arma los datos que se escriben en las marcas de un documento (contrato, autorización...) a partir de un trámite.

Devuelve un diccionario {MARCA: texto}. Una marca sin dato queda en None y `rellenar_docx` se niega a generar el documento 
(mejor un error claro que un contrato con huecos). Un texto vacío ("") significa "este dato no aplica", por ejemplo el servicio 3 de 
un contrato que solo tiene dos.

Formato tomado del contrato actual de Easy Office:
  - Fechas:   "02 DE OCTUBRE DE 2026"
  - Duración: "(12 MESES)"
  - Datos escritos por el cliente (nombres, direcciones...): en MAYÚSCULAS.
  - RUT con puntos y guión: 76.123.456-0
  - Precios con punto de miles: 59.990

SUPUESTOS A CONFIRMAR CON EASY OFFICE: las mayúsculas, el punto de miles en los precios y el texto bancario (ver `texto_bancario`).
"""
import os
from datetime import date

from app import condiciones as reglas_condiciones
from app.marcas_documento import normalizar_marca

MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
MARCA_POR_DEFECTO = "EASY OFFICE"


def fecha_larga(valor: str | date | None, mayusculas: bool = True) -> str | None:
    """'2026-10-02' -> '02 DE OCTUBRE DE 2026'. None si no hay fecha o no se entiende."""
    if not valor:
        return None
    try:
        fecha = valor if isinstance(valor, date) else date.fromisoformat(str(valor))
    except ValueError:
        return None
    texto = f"{fecha.day:02d} de {MESES[fecha.month - 1]} de {fecha.year}"
    return texto.upper() if mayusculas else texto


def rut_con_puntos(rut: str | None) -> str | None:
    """'76123456-0' -> '76.123.456-0'. Si no tiene la forma esperada, lo deja igual."""
    if not rut:
        return None
    limpio = rut.replace(".", "").strip().upper()
    cuerpo, _, dv = limpio.partition("-")
    if not cuerpo.isdigit() or not dv:
        return rut
    return f"{int(cuerpo):,}".replace(",", ".") + f"-{dv}"


def precio_con_miles(precio: int | None) -> str | None:
    return None if precio is None else f"{precio:,}".replace(",", ".")


def _mayus(valor: str | None) -> str | None:
    return valor.strip().upper() if valor and valor.strip() else None


def _texto(valor: str | None) -> str | None:
    return valor.strip() if valor and valor.strip() else None


def marca_del_tramite(tramite) -> str:
    """Marca comercial con la que se emite el documento: EASY OFFICE o INOFFICE.
    Hoy el trámite no la guarda, así que se usa la de MARCA_POR_DEFECTO (variable
    de entorno, por defecto 'EASY OFFICE'). Si el trámite trae `marca` en sus
    condiciones, esa manda."""
    en_condiciones = (tramite.condiciones or {}).get("marca")
    return (en_condiciones or os.getenv("MARCA_POR_DEFECTO") or MARCA_POR_DEFECTO).strip()


def texto_bancario(marca: str) -> str | None:
    """Datos de pago de la marca. Se leen de la variable de entorno
    BANCO_TEXTO_<MARCA> (BANCO_TEXTO_EASY_OFFICE, BANCO_TEXTO_INOFFICE) para que
    el número de cuenta nunca quede en el código ni en el repositorio.

    En el contrato la frase dice "...a la cuenta corriente N° <BANCOLINK>.", así
    que el texto debe seguir esa frase, por ejemplo:
      25770158951 del Banco Estado, a nombre de su titular EASY OFFICE SpA, R.U.T. 76.767.272-1
    Sin configurar devuelve None y el documento no se genera."""
    return _texto(os.getenv(f"BANCO_TEXTO_{normalizar_marca(marca)}"))


def valores_para_documento(tramite) -> dict[str, str | None]:
    empresa, sucursal = tramite.empresa, tramite.sucursal
    datos = (empresa.datos or {}) if empresa else {}
    cond = tramite.condiciones or {}

    valores: dict[str, str | None] = {
        "FOLIO": _texto(tramite.folio),
        # Empresa y representante (los escribió el cliente)
        "RAZON_SOCIAL": _mayus(empresa.razon_social) if empresa else None,
        "RUT": rut_con_puntos(empresa.rut_empresa) if empresa else None,
        "GIRO_PRINCIPAL": _mayus(datos.get("giro_principal")),
        "REPRESENTANTE_LEGAL": _mayus(datos.get("representante_legal")),
        "RUT_REP_LEGAL": rut_con_puntos(datos.get("rut_representante")),
        "DOMIC_REP_LEGAL": _mayus(datos.get("domicilio_representante")),
        "COMUNA_REP_LEGAL": _mayus(datos.get("comuna_representante")),
        "REGION_REP_LEGAL": _mayus(datos.get("region_representante")),
        "MAIL": _texto(datos.get("email")),
        "CELULAR_8_DIGITOS": _texto(datos.get("celular")),
        "FECHA_ESCRITURAESTATUTO_ACTUALIZADO": fecha_larga(datos.get("fecha_escritura"), mayusculas=False),
        "SITIONOTARIA": _mayus(datos.get("notaria")),
        # Sucursal
        "SUCURSAL": _mayus(sucursal.direccion) if sucursal else None,
        "COMUNA_SUCURSAL": _mayus(sucursal.comuna) if sucursal else None,
        "REGION_SUCURSAL": _mayus(sucursal.region) if sucursal else None,
        "ROL_PROPIEDAD": _texto(sucursal.rol_propiedad) if sucursal else None,
        # Condiciones fijadas por el agente
        "FECHA_DE_INICIO": fecha_larga(cond.get("fecha_inicio")),
        "VENCIMIENTO": fecha_larga(cond.get("fecha_vencimiento")),
        "DURACION": None,
        "BANCOLINK": texto_bancario(marca_del_tramite(tramite)),
    }

    meses = cond.get("duracion_meses")
    if meses:
        valores["DURACION"] = f"({meses} {'MES' if meses == 1 else 'MESES'})"

    # Servicios del contrato (hasta 3). Los que no existen quedan vacíos.
    # Sin condiciones no hay servicios: las marcas quedan sin dato.
    servicios = cond.get("servicios") if cond else None
    for n in range(1, reglas_condiciones.MAX_SERVICIOS + 1):
        if servicios is None:
            item = None
            vacio = None
        else:
            item = servicios[n - 1] if n <= len(servicios) else None
            vacio = ""
        valores[f"SERVICIO_{n}"] = _mayus(item["nombre"]) if item else vacio
        valores[f"DESCRIPCION_SS_{n}"] = (item.get("descripcion") or "") if item else vacio
        valores[f"PRECIO_SS_{n}"] = precio_con_miles(item["precio"]) if item else vacio
        valores[f"CICLO_PAGO_SS_{n}"] = item["ciclo_pago"] if item else vacio
    return valores