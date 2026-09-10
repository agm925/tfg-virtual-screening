"""Tests de integracion: /peticiones* (app/main.py), con JWT y Celery simulado."""

# Algoritmo ficticio que SI cumple el contrato del catalogo: lee su entrada,
# escribe en el ultimo argumento y termina con codigo 0. Hace falta porque la
# subida ejecuta el script sobre las moleculas de referencia antes de
# aceptarlo (ver app/banco_pruebas.py): un doble que no escribe nada seria
# rechazado, igual que lo seria un algoritmo real roto.
SCRIPT_DUMMY_PREPROCESADO = b"""# TIPO_ALGORITMO: preprocesado
import shutil
import sys

entrada, salida = sys.argv[1], sys.argv[-1]
shutil.copyfile(entrada, salida)
print("dummy: copiada la entrada a la salida")
"""
CONTENIDO_MOL2_DUMMY = b"@<TRIPOS>MOLECULE\ndummy\n1 0 0 0 0\nSMALL\nNO_CHARGES\n"


def _crear_algoritmo(client, desarrollador_autenticado) -> int:
    import uuid

    respuesta = client.post(
        "/algoritmos",
        data={"nombre": "Dummy peticiones", "descripcion": "Para tests de /peticiones", "tipo": "preprocesado"},
        files={"archivo": (f"test_dummy_{uuid.uuid4().hex[:8]}.py", SCRIPT_DUMMY_PREPROCESADO, "text/x-python")},
        headers=desarrollador_autenticado["headers"],
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["id"]


def test_crear_peticion_sin_token_devuelve_401(client, mock_celery):
    respuesta = client.post(
        "/peticiones",
        data={"algoritmo_id": "1"},
        files={"archivo_mol": ("test_dummy_sin_token.mol2", CONTENIDO_MOL2_DUMMY, "chemical/x-mol2")},
    )
    assert respuesta.status_code == 401
    assert len(mock_celery) == 0


def test_crear_peticion_encola_tarea_celery_y_asigna_propietario_del_token(
    client, mock_celery, usuario_autenticado, desarrollador_autenticado
):
    algoritmo_id = _crear_algoritmo(client, desarrollador_autenticado)

    respuesta = client.post(
        "/peticiones",
        data={"algoritmo_id": str(algoritmo_id)},
        files={"archivo_mol": ("test_dummy_peticion.mol2", CONTENIDO_MOL2_DUMMY, "chemical/x-mol2")},
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "PENDIENTE"
    assert cuerpo["usuario_id"] == usuario_autenticado["usuario"]["id"]
    assert len(mock_celery) == 1


def test_crear_peticion_con_extension_no_mol2_devuelve_400(client, mock_celery, usuario_autenticado, desarrollador_autenticado):
    algoritmo_id = _crear_algoritmo(client, desarrollador_autenticado)

    respuesta = client.post(
        "/peticiones",
        data={"algoritmo_id": str(algoritmo_id)},
        files={"archivo_mol": ("test_dummy.sdf", b"contenido irrelevante", "chemical/x-mdl-sdfile")},
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 400
    assert len(mock_celery) == 0


def test_estado_peticion_solo_visible_para_el_propietario(
    client, mock_celery, usuario_autenticado, desarrollador_autenticado
):
    algoritmo_id = _crear_algoritmo(client, desarrollador_autenticado)
    respuesta_creacion = client.post(
        "/peticiones",
        data={"algoritmo_id": str(algoritmo_id)},
        files={"archivo_mol": ("test_dummy_ownership.mol2", CONTENIDO_MOL2_DUMMY, "chemical/x-mol2")},
        headers=usuario_autenticado["headers"],
    )
    peticion_id = respuesta_creacion.json()["id"]

    respuesta_propietario = client.get(f"/peticiones/{peticion_id}/estado", headers=usuario_autenticado["headers"])
    assert respuesta_propietario.status_code == 200
    assert respuesta_propietario.json()["estado"] == "PENDIENTE"

    # otro usuario autenticado, pero no el propietario ni admin
    respuesta_intruso = client.get(f"/peticiones/{peticion_id}/estado", headers=desarrollador_autenticado["headers"])
    assert respuesta_intruso.status_code == 403

    respuesta_sin_token = client.get(f"/peticiones/{peticion_id}/estado")
    assert respuesta_sin_token.status_code == 401


def test_admin_puede_ver_el_estado_de_cualquier_peticion(
    client, mock_celery, usuario_autenticado, desarrollador_autenticado, admin_autenticado
):
    algoritmo_id = _crear_algoritmo(client, desarrollador_autenticado)
    respuesta_creacion = client.post(
        "/peticiones",
        data={"algoritmo_id": str(algoritmo_id)},
        files={"archivo_mol": ("test_dummy_admin.mol2", CONTENIDO_MOL2_DUMMY, "chemical/x-mol2")},
        headers=usuario_autenticado["headers"],
    )
    peticion_id = respuesta_creacion.json()["id"]

    respuesta_admin = client.get(f"/peticiones/{peticion_id}/estado", headers=admin_autenticado["headers"])
    assert respuesta_admin.status_code == 200


def test_borrar_peticion_ajena_devuelve_403(
    client, mock_celery, usuario_autenticado, desarrollador_autenticado
):
    algoritmo_id = _crear_algoritmo(client, desarrollador_autenticado)
    respuesta_creacion = client.post(
        "/peticiones",
        data={"algoritmo_id": str(algoritmo_id)},
        files={"archivo_mol": ("test_dummy_borrar_pet.mol2", CONTENIDO_MOL2_DUMMY, "chemical/x-mol2")},
        headers=usuario_autenticado["headers"],
    )
    peticion_id = respuesta_creacion.json()["id"]

    respuesta_borrado_ajeno = client.delete(f"/peticiones/{peticion_id}", headers=desarrollador_autenticado["headers"])
    assert respuesta_borrado_ajeno.status_code == 403

    respuesta_borrado_propio = client.delete(f"/peticiones/{peticion_id}", headers=usuario_autenticado["headers"])
    assert respuesta_borrado_propio.status_code == 200
