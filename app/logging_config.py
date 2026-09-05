"""
Logging estructurado (JSON) para la plataforma.

Por defecto, el logging de Python escribe texto libre en una linea; eso es
comodo de leer a mano pero dificil de indexar o filtrar en un sistema real
(ELK, Loki, CloudWatch...). Este modulo define un formatter que serializa
cada mensaje como una linea JSON con timestamp, nivel, nombre del logger,
evento y los campos adicionales que cada llamada pase via
`logger.info(evento, extra={...})` -- por ejemplo el email en un intento de
login, o el id de una peticion -- sin tener que parsear texto libre despues.
"""
import json
import logging
import sys
from datetime import datetime, timezone

# Atributos que ya trae cualquier LogRecord por defecto; todo lo que un
# logger.info(..., extra={...}) anada por encima de estos se trata como
# campo estructurado propio del evento.
_CAMPOS_ESTANDAR = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys())


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for clave, valor in record.__dict__.items():
            if clave not in _CAMPOS_ESTANDAR and clave not in payload:
                payload[clave] = valor
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configurar_logging(nivel: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    raiz = logging.getLogger("virtual_screening")
    raiz.setLevel(nivel)
    raiz.handlers = [handler]
    raiz.propagate = False


# Logger compartido por todo el backend (app/main.py, app/tasks.py, ...).
logger = logging.getLogger("virtual_screening")
