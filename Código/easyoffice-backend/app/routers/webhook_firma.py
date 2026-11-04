"""
Receptor de los avisos (webhook) de la API de firma. Contrato: easyoffice-firma-api/CONTRATO_INTEGRACION.md, seccion 6.

La ruta es publica (la llama la API de firma, no un usuario), asi que lo primero es comprobar la firma del aviso (app/firma_webhook.py). 
Lo que significa cada aviso lo resuelve app/aviso_firma.py.

Respuestas:
  200  aviso aplicado, repetido o ignorado (la API no necesita reintentar)
  400  el cuerpo no es un JSON valido
  401  firma invalida, aviso viejo o faltan las cabeceras
  413  cuerpo demasiado grande
  503  el aviso es autentico pero no se pudo aplicar ahora: la API de firma lo reintenta
"""
import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app import aviso_firma, firma_client, firma_webhook
from app.database import get_db
from app.seguridad import limiter

log = logging.getLogger("easyoffice.webhook_firma")

router = APIRouter(tags=["webhooks"])

# Los avisos reales pesan menos de 1 KB.
MAX_CUERPO_BYTES = 64 * 1024


@router.post("/api/webhooks/firma")
@limiter.limit("120/minute")
async def webhook_firma(
    request: Request,
    x_firma_timestamp: str | None = Header(default=None),
    x_firma_signature: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    cuerpo = await request.body()
    if len(cuerpo) > MAX_CUERPO_BYTES:
        raise HTTPException(status_code=413, detail="Cuerpo demasiado grande.")

    if not firma_webhook.aviso_valido(cuerpo, x_firma_timestamp, x_firma_signature):
        log.warning("Aviso de firma rechazado: firma invalida o vencida.")
        raise HTTPException(status_code=401, detail="Aviso de firma invalido.")

    try:
        evento = json.loads(cuerpo)
    except ValueError:
        raise HTTPException(status_code=400, detail="El cuerpo no es un JSON valido.") from None
    if not isinstance(evento, dict):
        raise HTTPException(status_code=400, detail="El cuerpo no es un JSON valido.")

    try:
        resultado = aviso_firma.procesar_aviso(db, evento)
    except (firma_client.ErrorFirma, aviso_firma.AvisoNoProcesable) as exc:
        db.rollback()
        log.error("No se pudo aplicar el aviso %s: %s", evento.get("event"), exc)
        raise HTTPException(status_code=503, detail="No se pudo aplicar el aviso; reintentar.") from None

    return {"ok": True, "resultado": resultado}