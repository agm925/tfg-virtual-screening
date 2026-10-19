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
from redis.exceptions import RedisError
from fastapi import HTTPException, status

from app.config import REDIS_URL
from app.logging_config import logger

MAX_INTENTOS_LOGIN = 5
VENTANA_BLOQUEO_SEGUNDOS = 60

# «¿Has olvidado tu contraseña?» (spec 011). Aqui no se cuentan fallos sino
# solicitudes: cada una manda un correo, y sin limite cualquiera podria
# llenarle el buzon a otro pidiendo enlaces en bucle.
MAX_SOLICITUDES_RESTABLECER = 3
VENTANA_RESTABLECER_SEGUNDOS = 15 * 60

_redis = redis.from_url(REDIS_URL, decode_responses=True)


def _clave(email: str, prefijo: str = "login_intentos") -> str:
    return f"{prefijo}:{email.strip().lower()}"


def _leer_intentos(email: str, prefijo: str = "login_intentos"):
    """
    Devuelve (intentos, segundos_restantes), o None si Redis no responde.

    El limitador tiene que fallar EN ABIERTO. Antes estas llamadas a Redis
    estaban sin proteger, asi que una caida de Redis convertia /login en un
    500 y nadie podia entrar aunque la base de datos estuviera perfecta: un
    componente accesorio (contar intentos fallidos) tumbaba la autenticacion
    entera. Se veia tambien en la suite de tests, donde los 42 tests de la API
    daban error por ConnectionError si no habia un Redis levantado en local.
    Perder temporalmente el limitador es mucho menos grave que perder el login.
    """
    try:
        clave = _clave(email, prefijo)
        intentos = _redis.get(clave)
        if intentos is None:
            return 0, 0
        return int(intentos), max(_redis.ttl(clave), 1)
    except RedisError as e:
        logger.warning("rate_limit_indisponible", extra={"error": str(e)})
        return None


def _sumar_intento(email: str, prefijo: str, ventana_segundos: int) -> None:
    """El primer intento abre una ventana durante la que se acumulan los
    siguientes. Si Redis no responde, no se contabiliza (ver _leer_intentos)."""
    try:
        clave = _clave(email, prefijo)
        intentos = _redis.incr(clave)
        if intentos == 1:
            _redis.expire(clave, ventana_segundos)
    except RedisError as e:
        logger.warning("rate_limit_indisponible", extra={"error": str(e)})


def verificar_no_bloqueado(email: str) -> None:
    """Lanza 429 si la cuenta ha superado MAX_INTENTOS_LOGIN en la ventana actual."""
    estado = _leer_intentos(email)
    if estado is None:
        return  # Redis caido: se deja pasar en vez de tumbar el login
    intentos, segundos_restantes = estado
    if intentos >= MAX_INTENTOS_LOGIN:
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
    """Incrementa el contador de fallos de login."""
    _sumar_intento(email, "login_intentos", VENTANA_BLOQUEO_SEGUNDOS)


def limpiar_intentos(email: str) -> None:
    """Se llama tras un login correcto: la cuenta empieza de cero."""
    try:
        _redis.delete(_clave(email))
    except RedisError as e:
        logger.warning("rate_limit_indisponible", extra={"error": str(e)})


def contar_solicitud_restablecer(email: str) -> None:
    """
    Lanza 429 si ese correo ya ha pedido MAX_SOLICITUDES_RESTABLECER enlaces
    en la ventana actual; si no, cuenta esta. Se cuenta tambien cuando el
    correo no tiene cuenta: si no, el limite no frenaria a quien prueba
    correos para ver cuales existen.
    """
    estado = _leer_intentos(email, "restablecer")
    if estado is not None:
        solicitudes, segundos_restantes = estado
        if solicitudes >= MAX_SOLICITUDES_RESTABLECER:
            logger.warning("restablecer_bloqueado_por_rate_limit", extra={"email": email})
            minutos = -(-segundos_restantes // 60)  # hacia arriba: nunca «0 minutos»
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Has pedido demasiados enlaces para este correo. "
                    f"Vuelve a intentarlo dentro de {minutos} min."
                ),
                headers={"Retry-After": str(segundos_restantes)},
            )
    _sumar_intento(email, "restablecer", VENTANA_RESTABLECER_SEGUNDOS)
