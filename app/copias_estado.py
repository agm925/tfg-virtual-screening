"""
El estado de las copias de seguridad, para la pagina Sistema (spec 009, R7).

El servicio `copias` (scripts/copias.py) deja estado.json en un volumen que
el backend monta de solo lectura. Aqui solo se interpreta: si nadie mira las
copias, nadie se entera de que han dejado de hacerse, y el frontend no decide
nada (principio 3).
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

RUTA_ESTADO = Path(os.environ.get("COPIAS_ESTADO", "copias_estado/estado.json"))
# Una copia al dia: con mas de 26 horas sin una buena, algo pasa aunque no
# conste ningun fallo (el servicio parado, por ejemplo). Las dos horas de
# margen cubren una copia que tarda.
ATRASO = timedelta(hours=26)


def leer(ruta: Path = None):
    """El contenido de estado.json, o None si no existe o esta a medias."""
    try:
        return json.loads(Path(ruta or RUTA_ESTADO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _fecha(texto):
    try:
        fecha = datetime.fromisoformat(texto)
    except (TypeError, ValueError):
        return None
    # Sin zona se toma como UTC, que es la del backend.
    return fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)


def resumir(estado, ahora: datetime) -> dict:
    """
    ok | fallida | atrasada | sin_copias, con la ultima copia buena y el
    error del ultimo intento si fallo.
    """
    estado = estado or {}
    ultima = estado.get("ultima_buena")
    resumen = {"estado": "ok", "ultima": ultima, "error": None,
               "ultimo_intento": estado.get("ultimo_intento")}
    if estado.get("ok") is False:
        resumen.update(estado="fallida", error=estado.get("error"))
    elif not ultima:
        resumen["estado"] = "sin_copias"
    else:
        fecha = _fecha(ultima.get("fecha"))
        if fecha is None or ahora - fecha > ATRASO:
            resumen["estado"] = "atrasada"
    return resumen


def estado_actual() -> dict:
    return resumir(leer(), datetime.now(timezone.utc))
