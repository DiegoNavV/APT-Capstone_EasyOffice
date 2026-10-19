"""
Marcas de las plantillas de documentos (contrato, autorización, etc.).

Una "marca" es el lugar de la plantilla Word donde el sistema pondrá un dato.
Se aceptan dos formas, porque conviene que Easy Office pueda seguir usando el formato que ya tiene:

  1. Campos de combinar correspondencia de Word (MERGEFIELD), como los del contrato actual de Easy Office.
  2. Texto escrito a mano con dobles llaves:  {{RAZON_SOCIAL}}

El nombre de una marca se normaliza antes de compararlo: sin tildes, en mayúsculas y con "_" en vez de espacios o símbolos. Así "Razón Social",
"RAZON_SOCIAL" y "razon_social" son la misma marca.

Este módulo solo LEE la plantilla y valida sus marcas. Reemplazar las marcas por los datos del trámite (generar el documento) es el paso 
5 del plan.

SUPUESTO A CONFIRMAR CON EASY OFFICE: el catálogo de abajo sale del contrato actual (CONTRATO_DE_SERVICIOS_OFICINA_EASY_OFFICE_2026). 
Si ellos agregan una marca nueva, se agrega aquí y se vuelve a subir la plantilla.
"""
import re
import unicodedata
import zipfile
from io import BytesIO

# ---------- Límites de seguridad para archivos subidos ----------

MAX_TAMANO_BYTES = 10 * 1024 * 1024            # archivo subido: 10 MB
MAX_DESCOMPRIMIDO_BYTES = 100 * 1024 * 1024    # contenido total ya descomprimido
MAX_ENTRADAS_ZIP = 1000                        # cantidad de archivos dentro del .docx
MAX_XML_BYTES = 30 * 1024 * 1024               # un solo XML interno

# ---------- Catálogo de marcas ----------

# (nombre normalizado, descripción para mostrar en el panel)
_MARCAS_BASE = [
    ("FOLIO", "Folio del contrato (ej. LF-01-2026)"),
    ("FECHA_DE_INICIO", "Fecha de inicio del contrato"),
    ("VENCIMIENTO", "Fecha de vencimiento del contrato"),
    ("DURACION", "Duración del contrato"),
    ("RAZON_SOCIAL", "Razón social de la empresa"),
    ("RUT", "RUT de la empresa"),
    ("GIRO_PRINCIPAL", "Giro principal de la empresa"),
    ("REPRESENTANTE_LEGAL", "Nombre del representante legal"),
    ("RUT_REP_LEGAL", "RUT del representante legal"),
    ("DOMIC_REP_LEGAL", "Domicilio del representante legal"),
    ("COMUNA_REP_LEGAL", "Comuna del representante legal"),
    ("REGION_REP_LEGAL", "Región del representante legal"),
    ("MAIL", "Correo electrónico del cliente"),
    ("CELULAR_8_DIGITOS", "Celular del cliente (8 dígitos)"),
    ("FECHA_ESCRITURAESTATUTO_ACTUALIZADO", "Fecha de la escritura o estatuto actualizado"),
    ("SITIONOTARIA", "Notaría de la escritura"),
    ("SUCURSAL", "Sucursal contratada"),
    ("COMUNA_SUCURSAL", "Comuna de la sucursal"),
    ("REGION_SUCURSAL", "Región de la sucursal"),
    ("ROL_PROPIEDAD", "Rol de la propiedad de la sucursal"),
    ("BANCOLINK", "Datos bancarios para el pago"),
]
# Los contratos pueden llevar hasta 3 servicios (condiciones.MAX_SERVICIOS).
for _n in (1, 2, 3):
    _MARCAS_BASE += [
        (f"SERVICIO_{_n}", f"Nombre del servicio {_n}"),
        (f"DESCRIPCION_SS_{_n}", f"Descripción del servicio {_n}"),
        (f"PRECIO_SS_{_n}", f"Precio del servicio {_n}"),
        (f"CICLO_PAGO_SS_{_n}", f"Ciclo de pago del servicio {_n}"),
    ]

CATALOGO_MARCAS: dict[str, str] = dict(_MARCAS_BASE)


class PlantillaInvalida(Exception):
    """El archivo subido no sirve como plantilla. El mensaje se muestra tal cual
    al usuario del panel, por eso va en lenguaje simple."""


def normalizar_marca(nombre: str) -> str:
    """'Razón Social ' -> 'RAZON_SOCIAL'."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", nombre) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^A-Z0-9]+", "_", sin_tildes.upper()).strip("_")


# ---------- Lectura del .docx ----------

_RE_MERGEFIELD = re.compile(r'MERGEFIELD\s+(?:"([^"]+)"|([^\s\\"]+))', re.IGNORECASE)
_RE_LLAVES = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_RE_PARRAFO = re.compile(r"<w:p[ >/].*?</w:p>", re.DOTALL)
_RE_TEXTO = re.compile(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>")
_RE_INSTR = re.compile(r"<w:instrText(?:\s[^>]*)?>([^<]*)</w:instrText>")
_RE_FLDSIMPLE = re.compile(r'<w:fldSimple\s[^>]*w:instr="([^"]*)"')

_PARTES_CON_TEXTO = re.compile(r"^word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$")


def _desescapar(texto: str) -> str:
    return (
        texto.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
        .replace("&apos;", "'").replace("&amp;", "&")
    )


def _marcas_de_xml(xml: str) -> set[str]:
    encontradas: set[str] = set()
    for parrafo in _RE_PARRAFO.findall(xml):
        # MERGEFIELD: el texto del campo puede venir partido en varios pedazos.
        instrucciones = _desescapar("".join(_RE_INSTR.findall(parrafo)))
        instrucciones += " " + " ".join(_desescapar(i) for i in _RE_FLDSIMPLE.findall(parrafo))
        for entre_comillas, simple in _RE_MERGEFIELD.findall(instrucciones):
            encontradas.add(normalizar_marca(entre_comillas or simple))
        # {{MARCA}}: Word suele partir el texto en varios pedazos al escribirlo.
        texto = _desescapar("".join(_RE_TEXTO.findall(parrafo)))
        for nombre in _RE_LLAVES.findall(texto):
            encontradas.add(normalizar_marca(nombre))
    encontradas.discard("")
    return encontradas


def revisar_docx(contenido: bytes) -> list[str]:
    """Valida el archivo subido y devuelve sus marcas (normalizadas, ordenadas).
    Lanza PlantillaInvalida si no es un Word seguro y utilizable."""
    if len(contenido) > MAX_TAMANO_BYTES:
        raise PlantillaInvalida(
            f"El archivo pesa demasiado (máximo {MAX_TAMANO_BYTES // (1024 * 1024)} MB)."
        )
    if not contenido.startswith(b"PK"):
        raise PlantillaInvalida("El archivo no es un documento Word (.docx) válido.")
    try:
        zf = zipfile.ZipFile(BytesIO(contenido))
    except zipfile.BadZipFile:
        raise PlantillaInvalida("El archivo no es un documento Word (.docx) válido.")

    with zf:
        entradas = zf.infolist()
        nombres = {e.filename for e in entradas}
        if len(entradas) > MAX_ENTRADAS_ZIP:
            raise PlantillaInvalida("El archivo tiene una estructura interna inusual y fue rechazado.")
        if sum(e.file_size for e in entradas) > MAX_DESCOMPRIMIDO_BYTES:
            raise PlantillaInvalida("El archivo tiene una estructura interna inusual y fue rechazado.")
        if "[Content_Types].xml" not in nombres or "word/document.xml" not in nombres:
            raise PlantillaInvalida("El archivo no es un documento Word (.docx) válido.")
        if any("vbaproject" in n.lower() for n in nombres):
            raise PlantillaInvalida("El documento contiene macros. Guárdalo como .docx sin macros.")
        try:
            contenido_tipos = zf.read("[Content_Types].xml").decode("utf-8", "ignore").lower()
        except Exception:
            raise PlantillaInvalida("El archivo no es un documento Word (.docx) válido.")
        if "macroenabled" in contenido_tipos:
            raise PlantillaInvalida("El documento contiene macros. Guárdalo como .docx sin macros.")

        marcas: set[str] = set()
        for entrada in entradas:
            if not _PARTES_CON_TEXTO.match(entrada.filename):
                continue
            if entrada.file_size > MAX_XML_BYTES:
                raise PlantillaInvalida("El archivo tiene una estructura interna inusual y fue rechazado.")
            try:
                xml = zf.read(entrada).decode("utf-8", "ignore")
            except Exception:
                raise PlantillaInvalida("El archivo no es un documento Word (.docx) válido.")
            marcas |= _marcas_de_xml(xml)

    if not marcas:
        raise PlantillaInvalida(
            "No se encontró ninguna marca en el documento. Usa campos de combinar "
            "correspondencia de Word o escribe las marcas como {{RAZON_SOCIAL}}."
        )
    desconocidas = sorted(m for m in marcas if m not in CATALOGO_MARCAS)
    if desconocidas:
        raise PlantillaInvalida(
            "El documento tiene marcas que el sistema no reconoce: "
            + ", ".join(desconocidas)
            + ". Revisa que estén bien escritas."
        )
    return sorted(marcas)