"""
Generación del documento de un trámite: toma la plantilla activa del servicio, la rellena con los datos del trámite y la convierte a PDF.

El PDF se guarda en DOCUMENTOS_DIR (volumen de Docker, fuera de Git) con un nombre que fijamos nosotros (tramite_<id>.pdf); en 
la base solo queda la ruta relativa, en `tramite.ruta_documento_generado`. Generar de nuevo reemplaza el PDF anterior, salvo que el 
trámite ya esté firmado o entregado.

Todavía NO cambia el estado del trámite ni envía nada a la firma: eso es el paso siguiente del plan (API de firma).
"""
import hashlib
import logging
import os
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models, plantillas
from app.convertir_pdf import ErrorConversion, ServidorOcupado, docx_a_pdf
from app.marcas_documento import CATALOGO_MARCAS, PlantillaInvalida
from app.rellenar_docx import FaltanDatos, rellenar_docx
from app.valores_documento import valores_para_documento

log = logging.getLogger("easyoffice.documentos")

# Con el documento ya firmado o entregado no se puede volver a generar.
ESTADOS_BLOQUEADOS = {"firmado", "entregado"}


class DocumentoNoGenerable(Exception):
    """No se pudo generar el documento. `mensaje` es apto para mostrar al agente;
    `codigo_http` indica cómo responder; `faltantes` lista los datos que faltan."""

    def __init__(self, mensaje: str, codigo_http: int = 409, faltantes: list[str] | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo_http = codigo_http
        self.faltantes = faltantes or []


def directorio_documentos() -> Path:
    # Se lee en cada uso (no al importar) para que las pruebas puedan cambiarlo.
    return Path(os.getenv("DOCUMENTOS_DIR", "/app/documentos"))


def ruta_del_documento(tramite: models.Tramite) -> Path | None:
    """Ruta real del PDF generado, o None si no existe. Se comprueba que quede
    dentro de DOCUMENTOS_DIR."""
    if not tramite.ruta_documento_generado:
        return None
    base = directorio_documentos().resolve()
    ruta = (base / tramite.ruta_documento_generado).resolve()
    if base not in ruta.parents or not ruta.is_file():
        return None
    return ruta


def nombre_para_descargar(tramite: models.Tramite) -> str:
    return f"{tramite.folio or 'tramite-' + str(tramite.id_tramite)}.pdf"


def _plantilla_activa(db: Session, tramite: models.Tramite) -> models.PlantillaDocumento:
    plantilla = (
        db.query(models.PlantillaDocumento)
        .filter(
            models.PlantillaDocumento.id_servicio == tramite.id_servicio,
            models.PlantillaDocumento.activa.is_(True),
        )
        .first()
    )
    if plantilla is None:
        raise DocumentoNoGenerable(
            f"El servicio «{tramite.servicio.nombre}» no tiene una plantilla activa. "
            "Sube una en la sección Plantillas."
        )
    return plantilla


def armar_docx(db: Session, tramite: models.Tramite, valores: dict | None = None) -> tuple[bytes, models.PlantillaDocumento]:
    """Rellena la plantilla activa del servicio y devuelve (.docx, plantilla).
    `valores` solo se pasa en la vista previa del borrador; si no, se arman con
    los datos guardados del trámite. Lanza DocumentoNoGenerable si algo falla."""
    plantilla = _plantilla_activa(db, tramite)
    try:
        contenido = plantillas.ruta_absoluta(plantilla).read_bytes()
    except (OSError, HTTPException):     # archivo borrado del volumen o ruta no válida
        raise DocumentoNoGenerable(
            "El archivo de la plantilla no está disponible en el servidor. Vuelve a subirlo."
        ) from None

    try:
        docx = rellenar_docx(contenido, valores if valores is not None else valores_para_documento(tramite))
    except FaltanDatos as exc:
        nombres = [CATALOGO_MARCAS.get(m, m) for m in exc.marcas]
        raise DocumentoNoGenerable(
            "Faltan datos para generar el documento: " + "; ".join(nombres) + ".",
            codigo_http=422, faltantes=exc.marcas,
        ) from None
    except PlantillaInvalida as exc:
        raise DocumentoNoGenerable(f"La plantilla activa no se puede usar: {exc}") from None
    return docx, plantilla


def generar(db: Session, tramite: models.Tramite) -> dict:
    """Genera (o regenera) el PDF del trámite. Devuelve sus datos; lanza
    DocumentoNoGenerable si algo impide hacerlo."""
    if tramite.estado_actual in ESTADOS_BLOQUEADOS:
        raise DocumentoNoGenerable("El trámite ya está firmado; su documento no se puede volver a generar.")

    docx, plantilla = armar_docx(db, tramite)

    try:
        pdf = docx_a_pdf(docx)
    except ServidorOcupado as exc:      # cola llena: no es un fallo, basta reintentar
        raise DocumentoNoGenerable(str(exc), codigo_http=503) from None
    except ErrorConversion as exc:
        log.error("Conversión a PDF fallida (trámite %s): %s", tramite.id_tramite, exc.detalle)
        raise DocumentoNoGenerable(str(exc), codigo_http=502) from None

    relativa = f"tramite_{tramite.id_tramite}.pdf"
    destino = directorio_documentos() / relativa
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(f".{uuid.uuid4().hex}.tmp")
    temporal.write_bytes(pdf)
    os.replace(temporal, destino)               # el PDF anterior nunca queda a medias

    tramite.ruta_documento_generado = relativa
    db.commit()
    db.refresh(tramite)
    log.info("Documento generado: trámite %s, plantilla v%s", tramite.id_tramite, plantilla.version)
    return {
        "id_tramite": tramite.id_tramite,
        "folio": tramite.folio,
        "nombre_archivo": nombre_para_descargar(tramite),
        "tamano_bytes": len(pdf),
        "hash_sha256": hashlib.sha256(pdf).hexdigest(),
        "version_plantilla": plantilla.version,
    }