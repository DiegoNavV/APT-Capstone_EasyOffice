"""
Vista previa del borrador del documento para el cliente (pública, con su código).

Antes de enviar sus datos, el cliente puede ver cómo quedaría su documento. Se arma con la plantilla activa, los datos que acaba 
de escribir y los que su empresa ya tiene registrados. NO se guarda nada: ni datos, ni PDF, ni cambio de estado.

Reglas de seguridad (es público, así que se piensa como si lo atacaran):
  - Los datos que la empresa ya tenía salen ENMASCARADOS en el PDF, igual que en el formulario; los que escribió el client 
    salen completos (son suyos).
  - Solo funciona mientras el trámite espera datos; después ya no hay nada que ver.
  - Los errores que ve el cliente son genéricos: nunca nombran marcas, plantillas ni detalles técnicos (esos quedan en el registro del servidor).
  - Convertir a PDF es lo caro, así que hay caché (mismos datos, mismo PDF), una espera máxima corta en la cola y límites de uso (ver el router).
"""
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict

from sqlalchemy.orm import Session

from app import campos_servicio, crud, documentos, enmascarado, models
from app.convertir_pdf import ErrorConversion, ServidorOcupado, docx_a_pdf
from app.valores_documento import valores_para_documento

log = logging.getLogger("easyoffice.vista_previa")

# Cuánto espera su turno en la cola de conversiones (más corto que el del panel:
# el cliente no debe quedarse mirando una pantalla colgada).
ESPERA_MAXIMA_SEGUNDOS = 8
CACHE_SEGUNDOS = 600            # un PDF guardado vale 10 minutos
CACHE_MAXIMO = 50               # y no se guardan más de 50 a la vez

MENSAJE_NO_DISPONIBLE = "Por ahora no podemos mostrar el borrador de tu documento. Puedes continuar y enviar tus datos."


class VistaPreviaNoDisponible(Exception):
    """No se puede mostrar el borrador. `mensaje` es apto para el cliente."""

    def __init__(self, mensaje: str, codigo_http: int = 409):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo_http = codigo_http


# ---------- caché en memoria ----------
# Guarda PDFs con datos del cliente: por eso dura poco, es pequeña y vive solo en
# la memoria del servidor (nunca en disco).

_cache: "OrderedDict[str, tuple[float, bytes]]" = OrderedDict()
_candado = threading.Lock()


def vaciar_cache() -> None:
    with _candado:
        _cache.clear()


def _cache_leer(clave: str) -> bytes | None:
    with _candado:
        item = _cache.get(clave)
        if item is None:
            return None
        vence, pdf = item
        if vence < time.monotonic():
            del _cache[clave]
            return None
        _cache.move_to_end(clave)
        return pdf


def _cache_guardar(clave: str, pdf: bytes) -> None:
    with _candado:
        _cache[clave] = (time.monotonic() + CACHE_SEGUNDOS, pdf)
        _cache.move_to_end(clave)
        while len(_cache) > CACHE_MAXIMO:
            _cache.popitem(last=False)


def _clave_de_cache(plantilla: models.PlantillaDocumento, valores: dict) -> str:
    """Mismos valores y misma plantilla = mismo PDF. (No sirve usar los bytes del
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


def generar_borrador(db: Session, tramite: models.Tramite, campos: dict) -> bytes:
    """Devuelve el PDF del borrador. Lanza campos_servicio.ErrorCampos si los datos
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
    pdf = _cache_leer(clave)
    if pdf is not None:
        return pdf
    try:
        pdf = docx_a_pdf(docx, espera_maxima=ESPERA_MAXIMA_SEGUNDOS)
    except ServidorOcupado as exc:
        raise VistaPreviaNoDisponible(str(exc), codigo_http=503) from None
    except ErrorConversion as exc:
        log.error("Conversión del borrador fallida (trámite %s): %s", tramite.id_tramite, exc.detalle)
        raise VistaPreviaNoDisponible(
            "No pudimos preparar el borrador. Intenta nuevamente en unos minutos.", codigo_http=502
        ) from None
    _cache_guardar(clave, pdf)
    return pdf