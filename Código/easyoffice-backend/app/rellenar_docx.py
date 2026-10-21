"""
Rellena una plantilla Word (.docx) con los datos de un trámite.

Recibe el archivo de la plantilla y un diccionario {MARCA: valor}; devuelve un docx nuevo con cada marca reemplazada por su valor. 
No toca nada más del documento (formato, columnas, tipografía): el texto reemplazado hereda el formato que tenía la marca.

Reconoce las mismas dos formas de marca que `marcas_documento`:
  1. Campos de combinar correspondencia (MERGEFIELD), completos o simples.
  2. Texto {{MARCA}}, aunque Word lo haya partido en varios pedazos.

Reglas importantes:
  - Si la plantilla tiene una marca para la que no hay valor (None o ausente), NO se genera el documento: se lanza FaltanDatos con la lista. 
    Un contrato con huecos es peor que un error visible. Un valor vacío ("") sí es válido (por ejemplo, el servicio 3 de un contrato 
    que solo tiene dos).
  - Los valores se tratan siempre como texto. Si un cliente escribe "{{RUT}}" en su razón social, queda escrito tal cual; 
    no se vuelve a interpretar.
  - Una fila de tabla cuyas marcas quedaron TODAS vacías se elimina (por ejemplo, la fila del servicio 3 en un contrato que solo tiene dos). 
    Las filas sin marcas (encabezados) o con al menos un dato no se tocan, y nunca se borran todas las filas de una tabla.
  - El XML se lee sin resolver entidades externas ni acceder a la red.
"""
import zipfile
from io import BytesIO

from lxml import etree

from app.marcas_documento import (
    _PARTES_CON_TEXTO, _RE_LLAVES, _RE_MERGEFIELD, MAX_TAMANO_BYTES, MAX_XML_BYTES,
    PlantillaInvalida, normalizar_marca,
)

_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_XML_NS = "http://www.w3.org/XML/1998/namespace"


def _w(nombre: str) -> str:
    return f"{{{_NS}}}{nombre}"


_P, _R, _T, _BR = _w("p"), _w("r"), _w("t"), _w("br")
_TR, _TBL = _w("tr"), _w("tbl")
_RPR, _FLDCHAR, _INSTR, _FLDSIMPLE = _w("rPr"), _w("fldChar"), _w("instrText"), _w("fldSimple")
_TIPO = _w("fldCharType")
_ESPACIO = f"{{{_XML_NS}}}space"


class FaltanDatos(Exception):
    """La plantilla pide marcas para las que no hay valor."""

    def __init__(self, marcas: list[str]):
        super().__init__("Faltan datos para: " + ", ".join(marcas))
        self.marcas = marcas


def _nombre_mergefield(instruccion: str) -> str | None:
    m = _RE_MERGEFIELD.search(instruccion)
    return normalizar_marca(m.group(1) or m.group(2)) if m else None


def _poner_texto(t: etree._Element, texto: str) -> None:
    """Escribe `texto` en un <w:t>. Los saltos de línea se vuelven <w:br/>."""
    lineas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    t.text = lineas[0]
    t.set(_ESPACIO, "preserve")
    anterior = t
    for linea in lineas[1:]:
        br = etree.Element(_BR)
        nuevo = etree.Element(_T)
        nuevo.text = linea
        nuevo.set(_ESPACIO, "preserve")
        anterior.addnext(br)
        br.addnext(nuevo)
        anterior = nuevo


def _corrida_con_texto(texto: str, formato: etree._Element | None) -> etree._Element:
    run = etree.Element(_R)
    if formato is not None:
        run.append(etree.fromstring(etree.tostring(formato)))  # copia del formato
    t = etree.SubElement(run, _T)
    _poner_texto(t, texto)
    return run


class _Relleno:
    def __init__(self, valores: dict[str, str | None]):
        self.valores = {normalizar_marca(k): v for k, v in valores.items()}
        self.faltan: set[str] = set()
        # Por párrafo: [marcas encontradas, marcas con texto]. Sirve para detectar filas vacías.
        self.conteo: dict[etree._Element, list[int]] = {}
        self._actual: list[int] = [0, 0]

    def valor(self, marca: str) -> str | None:
        v = self.valores.get(marca)
        if v is None:
            self.faltan.add(marca)
        else:
            self._actual[0] += 1
            self._actual[1] += 1 if v.strip() else 0
        return v

    def quitar_filas_vacias(self, raiz: etree._Element) -> None:
        """Elimina las filas de tabla cuyas marcas quedaron todas vacías."""
        for tabla in list(raiz.iter(_TBL)):
            filas = [f for f in tabla.findall(_TR)]
            vacias = []
            for fila in filas:
                total = sum(self.conteo.get(p, [0, 0])[0] for p in fila.iter(_P))
                con_texto = sum(self.conteo.get(p, [0, 0])[1] for p in fila.iter(_P))
                if total > 0 and con_texto == 0:
                    vacias.append(fila)
            if vacias and len(vacias) < len(filas):
                for fila in vacias:
                    tabla.remove(fila)

    # ---- campos simples: <w:fldSimple w:instr=" MERGEFIELD X "> ----
    def _campos_simples(self, p: etree._Element) -> None:
        for campo in list(p.iter(_FLDSIMPLE)):
            marca = _nombre_mergefield(campo.get(_w("instr"), ""))
            if marca is None:
                continue
            valor = self.valor(marca)
            if valor is None:
                continue
            primera = campo.find(_R)
            formato = primera.find(_RPR) if primera is not None else None
            campo.getparent().replace(campo, _corrida_con_texto(valor, formato))

    # ---- campos complejos: begin / instrText / separate / resultado / end ----
    def _campos_complejos(self, p: etree._Element) -> None:
        corridas = list(p.iter(_R))
        i = 0
        while i < len(corridas):
            run = corridas[i]
            fc = run.find(_FLDCHAR)
            if fc is None or fc.get(_TIPO) != "begin":
                i += 1
                continue
            # Buscar el "end" que cierra este campo (puede haber campos anidados).
            profundidad, j, instr, separado = 0, i, [], None
            while j < len(corridas):
                f = corridas[j].find(_FLDCHAR)
                if f is not None:
                    tipo = f.get(_TIPO)
                    if tipo == "begin":
                        profundidad += 1
                    elif tipo == "separate" and profundidad == 1 and separado is None:
                        separado = j
                    elif tipo == "end":
                        profundidad -= 1
                        if profundidad == 0:
                            break
                elif profundidad == 1 and separado is None:
                    instr.extend(t.text or "" for t in corridas[j].findall(_INSTR))
                j += 1
            if j >= len(corridas):          # campo sin cerrar en este párrafo: no se toca
                i += 1
                continue
            marca = _nombre_mergefield("".join(instr))
            if marca is None:               # otro tipo de campo (página, fecha...): se deja
                i = j + 1
                continue
            valor = self.valor(marca)
            if valor is not None:
                # El formato del resultado manda; si no hay, el del propio campo.
                resultado = corridas[separado + 1] if separado is not None and separado + 1 < j else None
                origen = resultado if resultado is not None else run
                nueva = _corrida_con_texto(valor, origen.find(_RPR))
                run.addprevious(nueva)
                for k in range(i, j + 1):
                    corridas[k].getparent().remove(corridas[k])
            i = j + 1

    # ---- texto {{MARCA}} ----
    def _llaves(self, p: etree._Element) -> None:
        textos = [t for t in p.iter(_T)]
        if not textos:
            return
        completo = "".join(t.text or "" for t in textos)
        coincidencias = list(_RE_LLAVES.finditer(completo))
        if not coincidencias:
            return
        inicios, pos = [], 0
        for t in textos:
            inicios.append(pos)
            pos += len(t.text or "")
        # De derecha a izquierda para que los desplazamientos no afecten a los anteriores.
        for m in reversed(coincidencias):
            valor = self.valor(normalizar_marca(m.group(1)))
            if valor is None:
                continue
            ini, fin = m.start(), m.end()
            tocados = [
                k for k, t in enumerate(textos)
                if inicios[k] < fin and inicios[k] + len(t.text or "") > ini
            ]
            if not tocados:
                continue
            primero, ultimo = tocados[0], tocados[-1]
            for k in tocados:
                original = textos[k].text or ""
                desde = max(ini - inicios[k], 0)
                hasta = min(fin - inicios[k], len(original))
                antes, despues = original[:desde], original[hasta:]
                if k == primero:
                    _poner_texto(textos[k], antes + valor + (despues if k == ultimo else ""))
                elif k == ultimo:
                    textos[k].text = despues
                    textos[k].set(_ESPACIO, "preserve")
                else:
                    textos[k].text = ""

    def parrafo(self, p: etree._Element) -> None:
        self._actual = [0, 0]
        self._llaves(p)             # primero las {{ }}: así los valores no se reinterpretan
        self._campos_simples(p)
        self._campos_complejos(p)
        if self._actual[0]:
            self.conteo[p] = self._actual


def _procesar_xml(xml: bytes, relleno: _Relleno) -> bytes:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, load_dtd=False)
    raiz = etree.fromstring(xml, parser)
    for p in list(raiz.iter(_P)):
        relleno.parrafo(p)
    relleno.quitar_filas_vacias(raiz)
    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8", standalone=True)


def rellenar_docx(plantilla: bytes, valores: dict[str, str | None]) -> bytes:
    """Devuelve el .docx con las marcas reemplazadas. Ver la nota del módulo."""
    if len(plantilla) > MAX_TAMANO_BYTES:
        raise PlantillaInvalida("La plantilla pesa demasiado.")
    relleno = _Relleno(valores)
    salida = BytesIO()
    try:
        with zipfile.ZipFile(BytesIO(plantilla)) as origen, \
                zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as destino:
            for entrada in origen.infolist():
                datos = origen.read(entrada)
                if _PARTES_CON_TEXTO.match(entrada.filename):
                    if entrada.file_size > MAX_XML_BYTES:
                        raise PlantillaInvalida("La plantilla tiene una estructura interna inusual.")
                    datos = _procesar_xml(datos, relleno)
                destino.writestr(entrada.filename, datos)
    except zipfile.BadZipFile:
        raise PlantillaInvalida("La plantilla no es un documento Word (.docx) válido.") from None
    if relleno.faltan:
        raise FaltanDatos(sorted(relleno.faltan))
    return salida.getvalue()