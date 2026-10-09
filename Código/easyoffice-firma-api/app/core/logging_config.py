"""Logs en JSON y sin datos sensibles.

Antes de escribir cada registro se enmascaran correos, RUTs y valores que
parezcan tokens o API keys. Es una red de seguridad: el código igual debe
evitar loguear esos datos.
"""
import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

# Id de la petición en curso. Lo fija RequestIdMiddleware y se agrega a cada
# log emitido durante esa petición, para poder seguirla de punta a punta.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_PATRONES = [
    # Correos: se deja la primera letra y el dominio.
    (re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})"), r"\1***@\2"),
    # RUT chileno con o sin puntos.
    (re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}-[\dkK]\b"), "[RUT]"),
    # API keys de la plataforma (prefijo fk_) y tokens Bearer.
    (re.compile(r"\bfk_(live|test)_[A-Za-z0-9_-]+"), "fk_[REDACTADO]"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._-]+"), r"\1[REDACTADO]"),
]


def redactar(texto: str) -> str:
    for patron, reemplazo in _PATRONES:
        texto = patron.sub(reemplazo, texto)
    return texto


class JsonRedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        datos = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": redactar(record.getMessage()),
        }
        request_id = getattr(record, "request_id", None) or request_id_var.get()
        if request_id:
            datos["request_id"] = request_id
        if record.exc_info:
            datos["exc"] = redactar(self.formatException(record.exc_info))
        return json.dumps(datos, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonRedactingFormatter())
    raiz = logging.getLogger()
    raiz.handlers[:] = [handler]
    raiz.setLevel(level.upper())
