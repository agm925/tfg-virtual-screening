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
)
