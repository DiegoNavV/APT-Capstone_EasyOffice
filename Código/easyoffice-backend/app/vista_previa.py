"""
Vista previa del borrador del documento para el cliente (pública, con su código).

Antes de enviar sus datos, el cliente puede ver cómo quedaría su documento. Se arma con la plantilla activa, los datos que acaba 
de escribir y los que su empresa ya tiene registrados. NO se guarda nada: ni datos, ni PDF, ni cambio de estado.

El cliente NUNCA recibe un PDF (podría hacerlo pasar por el contrato): recibe una imagen JPEG por página, con la marca de agua
"BORRADOR - SIN VALIDEZ" quemada en el servidor (ver marca_agua.py). El PDF solo existe en memoria mientras se arma.

Reglas de seguridad (es público, así que se piensa como si lo atacaran):
  - Los datos que la empresa ya tenía salen ENMASCARADOS en el borrador, igual que en el formulario; los que escribió el client
    salen completos (son suyos).
  - Solo funciona mientras el trámite espera datos; después ya no hay nada que ver.
  - Los errores que ve el cliente son genéricos: nunca nombran marcas, plantillas ni detalles técnicos (esos quedan en el registro del servidor).
  - Convertir es lo caro, así que hay caché (mismos datos, mismas imágenes), una espera máxima corta en la cola y límites de uso (ver el router).
"""
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict

from sqlalchemy.orm import Session

from app import campos_servicio, crud, documentos, enmascarado, marca_agua, models
from app.convertir_pdf import ErrorConversion, ServidorOcupado, docx_a_pdf, pdf_a_imagenes
from app.valores_documento import valores_para_documento

log = logging.getLogger("easyoffice.vista_previa")

# Cuánto espera su turno en la cola de conversiones (más corto que el del panel:
# el cliente no debe quedarse mirando una pantalla colgada).
ESPERA_MAXIMA_SEGUNDOS = 8
CACHE_SEGUNDOS = 600                        # un borrador guardado vale 10 minutos
CACHE_MAXIMO = 50                           # no se guardan más de 50 a la vez
CACHE_MAXIMO_BYTES = 40 * 1024 * 1024       # ni más de 40 MB de imágenes en total

MENSAJE_NO_DISPONIBLE = "Por ahora no podemos mostrar el borrador de tu documento. Puedes continuar y enviar tus datos."


class VistaPreviaNoDisponible(Exception):
    """No se puede mostrar el borrador. `mensaje` es apto para el cliente."""

    def __init__(self, mensaje: str, codigo_http: int = 409):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo_http = codigo_http


# ---------- caché en memoria ----------
# Guarda las imágenes ya marcadas (con datos del cliente): por eso dura poco, es
# pequeña y vive solo en la memoria del servidor (nunca en disco). Se guardan los
# JPEG en bytes (el base64 se arma al responder) y se lleva la cuenta del total
# para respetar CACHE_MAXIMO_BYTES. Al pasarse, sale primero la entrada usada hace
# más tiempo.

_cache: "OrderedDict[str, tuple[float, tuple[bytes, ...]]]" = OrderedDict()
_cache_bytes = 0
_candado = threading.Lock()


def _peso(paginas: tuple[bytes, ...]) -> int:
    return sum(len(p) for p in paginas)


def vaciar_cache() -> None:
    global _cache_bytes
    with _candado:
        _cache.clear()
        _cache_bytes = 0


def _cache_leer(clave: str) -> tuple[bytes, ...] | None:
    global _cache_bytes
    with _candado:
        item = _cache.get(clave)
        if item is None:
            return None
        vence, paginas = item
        if vence < time.monotonic():
            del _cache[clave]
            _cache_bytes -= _peso(paginas)
            return None
        _cache.move_to_end(clave)
        return paginas


def _cache_guardar(clave: str, paginas: tuple[bytes, ...]) -> None:
    global _cache_bytes
    with _candado:
        anterior = _cache.pop(clave, None)
        if anterior is not None:
            _cache_bytes -= _peso(anterior[1])
        _cache[clave] = (time.monotonic() + CACHE_SEGUNDOS, paginas)
        _cache_bytes += _peso(paginas)
        while _cache and (len(_cache) > CACHE_MAXIMO or _cache_bytes > CACHE_MAXIMO_BYTES):
            _clave, (_vence, expulsadas) = _cache.popitem(last=False)
            _cache_bytes -= _peso(expulsadas)


def _clave_de_cache(plantilla: models.PlantillaDocumento, valores: dict) -> str:
    """Mismos valores y misma plantilla = mismo borrador. (No sirve usar los bytes del
    .docx: el zip guarda la hora de creación y cambia en cada armado.)"""
    texto = json.dumps(
        {"plantilla": plantilla.id_plantilla, "hash": plantilla.hash_sha256, "valores": valores},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


# ---------- armado ----------

def _empresa_simulada(empresa: models.Empresa | None, limpios: dict[str, str]) -> dict:
    """La empresa tal como quedaría con lo que escribió el cliente: lo que ya estaba
    registrado va enmascarado, lo nuevo va completo. Se recorren TODOS los datos
    posibles (no solo los del servicio) para que nada registrado salga completo."""
    razon_social = rut_empresa = None
    datos: dict[str, str] = {}
    for campo in campos_servicio.CAMPOS_CONTRATO:
        guardado = crud.valor_guardado(empresa, campo)
        valor = enmascarado.enmascarar(campo, guardado) if guardado else limpios.get(campo.clave)
        if campo.clave == "razon_social":
            razon_social = valor
        elif campo.clave == "rut_empresa":
            rut_empresa = valor
        elif valor is not None:
            datos[campo.clave] = valor
    return {"razon_social": razon_social, "rut_empresa": rut_empresa, "datos": datos}


def generar_borrador(db: Session, tramite: models.Tramite, campos: dict) -> tuple[bytes, ...]:
    """Devuelve las páginas del borrador como JPEG con marca de agua, en orden.
    Lanza campos_servicio.ErrorCampos si los datos
    tienen errores (se informan todos juntos) y VistaPreviaNoDisponible si no se
    puede mostrar."""
    definicion = campos_servicio.campos_para_servicio(tramite.servicio.nombre)
    if (
        definicion is None
        or tramite.datos_empresa is not None
        or tramite.estado_actual != crud.ESTADO_ESPERANDO_DATOS
    ):
        raise VistaPreviaNoDisponible(crud.FormularioNoDisponible().mensaje)

    _pendientes, limpios, errores = crud.revisar_campos_cliente(definicion, tramite.empresa, campos)
    if errores:
        raise campos_servicio.ErrorCampos(errores)

    valores = valores_para_documento(tramite, empresa_simulada=_empresa_simulada(tramite.empresa, limpios))
    try:
        docx, plantilla = documentos.armar_docx(db, tramite, valores)
    except documentos.DocumentoNoGenerable as exc:
        # Lo que falta lo debe resolver el agente: el cliente solo ve un mensaje simple.
        log.warning("Borrador no disponible (trámite %s): %s", tramite.id_tramite, exc.mensaje)
        raise VistaPreviaNoDisponible(MENSAJE_NO_DISPONIBLE) from None

    clave = _clave_de_cache(plantilla, valores)
    paginas = _cache_leer(clave)
    if paginas is not None:
        return paginas
    try:
        pdf = docx_a_pdf(docx, espera_maxima=ESPERA_MAXIMA_SEGUNDOS)
        paginas = tuple(
            marca_agua.marcar(imagen) for imagen in pdf_a_imagenes(pdf, espera_maxima=ESPERA_MAXIMA_SEGUNDOS)
        )
    except ServidorOcupado as exc:
        raise VistaPreviaNoDisponible(str(exc), codigo_http=503) from None
    except ErrorConversion as exc:
        log.error("Conversión del borrador fallida (trámite %s): %s", tramite.id_tramite, exc.detalle)
        raise VistaPreviaNoDisponible(
            "No pudimos preparar el borrador. Intenta nuevamente en unos minutos.", codigo_http=502
        ) from None
    _cache_guardar(clave, paginas)
    return paginas