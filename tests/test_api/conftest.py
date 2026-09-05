"""
Fixtures propias de los tests de integracion de la API.

Los endpoints de app/main.py escriben ficheros directamente en algoritmos/
y uploads/ (rutas relativas hardcodeadas, no inyectables), que son los
MISMOS directorios que usa la plataforma real -- estan montados como
volumenes Docker. Para no dejar basura de tests mezclada con el catalogo
real de algoritmos ni con las moleculas subidas por usuarios reales, un
fixture autouse recuerda que ficheros habia antes de cada test y borra
cualquier fichero nuevo al terminar.
"""
import os
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import models
from app.main import app
from app.tasks import (
    ejecutar_peticion_async,
    ejecutar_workflow_async,
    ejecutar_workflow_batch_async,
)

ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture()
def client():
    return TestClient(app)


def _registrar_y_verificar(client, db_session, rol: str = "biologo") -> dict:
    """
    Registra un usuario nuevo, lo marca como verificado directamente en BD
    (sin pasar por el correo real) y hace login para obtener un JWT.
    Devuelve {"usuario": {...}, "headers": {"Authorization": "Bearer ..."}}.
    """
    email = f"test_{uuid.uuid4().hex[:10]}@example.com"
    password = "clave12345"
    client.post("/registro", json={"email": email, "nombre": "Usuario de Test", "password_hash": password})

    usuario_db = db_session.query(models.Usuario).filter(models.Usuario.email == email).first()
    usuario_db.email_verificado = True
    if rol != "biologo":
        usuario_db.rol = models.RolUsuario(rol)
    db_session.commit()

    respuesta_login = client.post("/login", json={"email": email, "password_hash": password})
    assert respuesta_login.status_code == 200, respuesta_login.text
    cuerpo = respuesta_login.json()

    return {
        "usuario": cuerpo["usuario"],
        "headers": {"Authorization": f"Bearer {cuerpo['access_token']}"},
    }


@pytest.fixture()
def usuario_autenticado(client, db_session):
    """Usuario normal (rol biologo) ya verificado, con cabecera Authorization lista para usar."""
    return _registrar_y_verificar(client, db_session, rol="biologo")


@pytest.fixture()
def desarrollador_autenticado(client, db_session):
    """Usuario con rol 'desarrollador', para probar endpoints restringidos por rol (p. ej. POST /algoritmos)."""
    return _registrar_y_verificar(client, db_session, rol="desarrollador")


@pytest.fixture()
def admin_autenticado(client, db_session):
    """Usuario con rol 'admin', para probar accesos que se permiten a cualquier admin."""
    return _registrar_y_verificar(client, db_session, rol="admin")


@pytest.fixture()
def mock_celery(monkeypatch):
    """
    Sustituye el `.delay(...)` de las tres tareas Celery por un doble que
    no encola nada de verdad. Los tests de integracion de la API deben
    poder correr sin Redis ni un worker real levantado -- lo que se prueba
    aqui es que el endpoint encola correctamente (guarda el
    celery_task_id, deja el estado en PENDIENTE/pendiente), no la
    ejecucion real del algoritmo, que ya cubren los tests de
    tests/test_algoritmos/.
    """
    llamadas = []

    def _fake_delay(*args, **kwargs):
        llamadas.append(args)
        return SimpleNamespace(id=f"fake-task-{len(llamadas)}")

    for tarea in (ejecutar_peticion_async, ejecutar_workflow_async, ejecutar_workflow_batch_async):
        monkeypatch.setattr(tarea, "delay", _fake_delay)

    return llamadas


@pytest.fixture(autouse=True)
def _limpiar_ficheros_generados_por_el_test():
    directorios = [ROOT / "algoritmos", ROOT / "uploads"]
    antes = {d: set(os.listdir(d)) if d.exists() else set() for d in directorios}
    yield
    for d in directorios:
        if not d.exists():
            continue
        for nombre in set(os.listdir(d)) - antes[d]:
            try:
                (d / nombre).unlink()
            except OSError:
                pass
