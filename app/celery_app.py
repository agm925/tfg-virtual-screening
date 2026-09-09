from celery import Celery
from app.config import REDIS_URL, WORKER_CONCURRENCY

celery_app = Celery(
    "tfg_virtual_screening",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Madrid",
    enable_utc=True,
    # Controlado por WORKER_CONCURRENCY (app/config.py). Por defecto 1 para no saturar
    # el PC local; en producción/HPC se sube vía variable de entorno.
    worker_concurrency=WORKER_CONCURRENCY,

    # --- Ajustes necesarios para que escalar workers sirva de algo ---

    # Un worker reserva por adelantado tantas tareas como
    # prefetch_multiplier x concurrency. El valor por defecto (4) esta pensado
    # para tareas de milisegundos; aqui una sola puede durar minutos, asi que
    # un worker acaparaba cuatro trabajos que no podia procesar mientras otros
    # workers estaban ociosos, anulando el reparto. Con 1 cada worker coge
    # solo lo que va a ejecutar de inmediato.
    worker_prefetch_multiplier=1,

    # Por defecto Celery confirma la tarea al ENTREGARLA, no al terminarla: si
    # el worker muere a mitad --OOM, reinicio del contenedor, nodo caido-- la
    # tarea se da por hecha y se pierde en silencio. Con acks_late se confirma
    # al terminar, de modo que un trabajo interrumpido vuelve a la cola.
    task_acks_late=True,

    # Contrapartida obligatoria de acks_late: si el worker desaparece sin
    # avisar, hay que devolver sus tareas a la cola en vez de esperar a un
    # reconocimiento que no llegara nunca.
    task_reject_on_worker_lost=True,

    # Cinturon de seguridad frente a una tarea que no termina nunca. El limite
    # blando lanza una excepcion dentro de la tarea (permite limpiar); el duro
    # mata el proceso. Se dimensionan por encima de ALGORITMO_TIMEOUT, que es
    # el limite por algoritmo individual: una tarea de workflow encadena
    # varios, asi que necesita mas margen que cada uno de ellos.
    task_soft_time_limit=6 * 60 * 60,
    task_time_limit=6 * 60 * 60 + 300,
)
