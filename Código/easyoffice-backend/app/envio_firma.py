"""
Envio de un tramite a la API de firma (Ley 19.799). Contrato: easyoffice-firma-api/CONTRATO_INTEGRACION.md

Se llama justo despues de que el cliente envia sus datos. Pasos:
  1. Genera el PDF del tramite desde la plantilla activa (app/documentos.py).
  2. Lo manda a la API de firma y guarda el id que devuelve en `tramite.documento_firma_id`.
  3. Registra la aceptacion del cliente con la IP y el navegador desde donde envio sus datos.

Firma el representante legal de la empresa (nombre y RUT de su ficha) con el correo que la empresa registro en el formulario. El FOLIO 
identifica el documento; el codigo de seguimiento nunca sale del CRM.

Los datos del cliente ya estan guardados cuando esto corre, asi que NUNCA lanza: si algo falla lo anota en el log y el tramite 
queda en `procesando_firma`. Se puede volver a llamar: si el documento ya se creo en la API de firma no se crea otro, solo se reintenta 
lo que faltaba.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import documentos, firma_client, models
from app.database import SessionLocal
from app.documentos import DocumentoNoGenerable
from app.firma_client import ErrorFirma

log = logging.getLogger("easyoffice.envio_firma")

ESTADO_PROCESANDO_FIRMA = "procesando_firma"


def correo_del_firmante(tramite: models.Tramite) -> str | None:
    """Correo al que se asocia la firma. Primero el de la empresa; si no tiene, el del cliente, pero solo
    si dijo ser el representante legal al enviar sus datos (si no, ese correo seria de otra persona).
    None si no hay ninguno: el tramite no se puede enviar a firma."""
    empresa = tramite.empresa
    if empresa is not None and empresa.email:
        return empresa.email
    envio = tramite.datos_empresa
    cliente = tramite.cliente
    if envio is not None and envio.solicitante_es_representante and cliente is not None and cliente.email:
        return cliente.email
    return None


def _firmante(tramite: models.Tramite) -> dict | None:
    """Datos del firmante que pide la API, o None si falta alguno."""
    empresa = tramite.empresa
    representante = empresa.representante if empresa else None
    if empresa is None or representante is None:
        return None
    correo = correo_del_firmante(tramite)
    if not (representante.nombre and representante.rut and correo):
        return None
    return {
        "name": representante.nombre,
        "rut": representante.rut,
        "email": correo,
        "represents_name": empresa.razon_social,
        "represents_rut": empresa.rut_empresa,
    }


def enviar_a_firma(db: Session, tramite: models.Tramite, ip: str, user_agent: str) -> bool:
    """Manda el tramite a firmar y registra la aceptacion del cliente.
    Devuelve True si quedo registrada; False si algo fallo (queda anotado en el log)."""
    id_tramite = tramite.id_tramite
    try:
        if tramite.estado_actual != ESTADO_PROCESANDO_FIRMA:
            log.info("Tramite %s no esta en %s; no se envia a firma.", id_tramite, ESTADO_PROCESANDO_FIRMA)
            return False
        if not tramite.folio:
            log.error("Tramite %s sin folio: no se puede enviar a firma.", id_tramite)
            return False
        firmante = _firmante(tramite)
        if firmante is None:
            log.error("Tramite %s: faltan datos del firmante (representante o correo de la empresa).", id_tramite)
            return False

        if not tramite.documento_firma_id:
            documentos.generar(db, tramite)
            ruta = documentos.ruta_del_documento(tramite)
            if ruta is None:
                log.error("Tramite %s: el PDF generado no esta disponible.", id_tramite)
                return False
            creado = firma_client.crear_documento(
                pdf=ruta.read_bytes(),
                titulo=tramite.servicio.nombre,
                folio=tramite.folio,
                firmante=firmante,
            )
            tramite.documento_firma_id = creado["id"]
            db.commit()
            log.info("Tramite %s enviado a la API de firma.", id_tramite)

        firma_client.registrar_aceptacion(tramite.documento_firma_id, tramite.folio, ip, user_agent)
        log.info("Aceptacion del cliente registrada (tramite %s).", id_tramite)
        return True

    except DocumentoNoGenerable as exc:
        db.rollback()
        log.error("Tramite %s: no se pudo generar el documento: %s", id_tramite, exc.mensaje)
    except ErrorFirma as exc:
        db.rollback()
        log.error("Tramite %s: fallo con la API de firma (reintentable=%s): %s", id_tramite, exc.reintentable, exc)
    except Exception:
        db.rollback()
        log.exception("Tramite %s: error inesperado al enviar a firma.", id_tramite)
    return False

def enviar_en_segundo_plano(id_tramite: int, ip: str, user_agent: str) -> None:
    """Lo mismo que `enviar_a_firma`, pero pensado para correr DESPUES de responderle al cliente
    (BackgroundTasks de FastAPI): abre su propia sesion, porque la de la peticion ya esta cerrada,
    y vuelve a cargar el tramite por su id. Nunca lanza."""
    db = SessionLocal()
    try:
        tramite = db.get(models.Tramite, id_tramite)
        if tramite is None:
            log.error("Tramite %s no encontrado al enviarlo a firma en segundo plano.", id_tramite)
            return
        enviar_a_firma(db, tramite, ip, user_agent)
    except Exception:
        log.exception("Tramite %s: error inesperado al enviar a firma en segundo plano.", id_tramite)
    finally:
        db.close()


# ---------- Aviso al agente ----------

MOTIVO_SIN_CORREO = "Falta el correo del firmante."
MOTIVO_NO_COMPLETADO = "El envío a firma no se completó."

# Tiempo que se espera antes de dar por fallido un envío: el normal tarda unos segundos, y el aviso de que
# quedo firmado llega poco despues.
ESPERA_ENVIO_SEGUNDOS = 300


def motivo_envio_pendiente(tramite: models.Tramite, ahora: datetime | None = None) -> str | None:
    """Por que un tramite en `procesando_firma` no avanza, o None si no hay nada que avisar. El panel lo
    muestra para que el agente sepa que debe intervenir (hoy el fallo solo queda en el log).

      - sin correo del firmante: se avisa de inmediato, porque no se va a enviar nunca solo;
      - cualquier otro caso: se avisa si pasaron mas de ESPERA_ENVIO_SEGUNDOS sin que el tramite avance
        (la API de firma caida, un error al generar el PDF, el aviso que no llego...)."""
    if tramite.estado_actual != ESTADO_PROCESANDO_FIRMA:
        return None
    if not tramite.documento_firma_id and _firmante(tramite) is None:
        return MOTIVO_SIN_CORREO
    ahora = ahora or datetime.now(timezone.utc).replace(tzinfo=None)
    if tramite.fecha_actualizacion and (ahora - tramite.fecha_actualizacion).total_seconds() > ESPERA_ENVIO_SEGUNDOS:
        return MOTIVO_NO_COMPLETADO
    return None