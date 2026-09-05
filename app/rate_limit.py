"""
Limitador de intentos de login, respaldado en Redis (ya forma parte del
stack para Celery, asi que no anade una dependencia nueva).

Diseno: por CUENTA (email), no por IP -- una IP puede ser compartida por
varios usuarios legitimos (NAT, red universitaria) y bloquearla penalizaria
a gente que no ha hecho nada, mientras que limitar por cuenta es la defensa
estandar contra fuerza bruta/credential stuffing dirigido a un usuario
concreto. Tras MAX_INTENTOS intentos fallidos consecutivos, la cuenta queda
bloqueada durante VENTANA_BLOQUEO_SEGUNDOS, independientemente de si se
siguen intentando credenciales nuevas durante ese bloqueo.
"""
import redis
from fastapi import HTTPException, status

from app.config import REDIS_URL
from app.logging_config import logger

MAX_INTENTOS_LOGIN = 5
VENTANA_BLOQUEO_SEGUNDOS = 60

_redis = redis.from_url(REDIS_URL, decode_responses=True)


def _clave(email: str) -> str:
    return f"login_intentos:{email.strip().lower()}"


def verificar_no_bloqueado(email: str) -> None:
    """Lanza 429 si la cuenta ha superado MAX_INTENTOS_LOGIN en la ventana actual."""
    intentos = _redis.get(_clave(email))
    if intentos is not None and int(intentos) >= MAX_INTENTOS_LOGIN:
        ttl = _redis.ttl(_clave(email))
        segundos_restantes = max(ttl, 1)
        logger.warning(
            "login_bloqueado_por_rate_limit",
            extra={"email": email, "segundos_restantes": segundos_restantes},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Demasiados intentos de inicio de sesión fallidos. "
                f"Cuenta bloqueada temporalmente, vuelve a intentarlo en "
                f"{segundos_restantes}s."
            ),
            headers={"Retry-After": str(segundos_restantes)},
        )


def registrar_intento_fallido(email: str) -> None:
    """Incrementa el contador de fallos; el primer fallo abre una ventana de
    VENTANA_BLOQUEO_SEGUNDOS durante la que se acumulan los siguientes."""
    clave = _clave(email)
    intentos = _redis.incr(clave)
    if intentos == 1:
        _redis.expire(clave, VENTANA_BLOQUEO_SEGUNDOS)


def limpiar_intentos(email: str) -> None:
    """Se llama tras un login correcto: la cuenta empieza de cero."""
    _redis.delete(_clave(email))
