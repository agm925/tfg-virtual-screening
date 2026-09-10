"""Tests de integracion: POST/GET /algoritmos (app/main.py), con JWT y rol."""

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


def test_subir_algoritmo_sin_token_devuelve_401(client):
    respuesta = client.post(
        "/algoritmos",
        data={"nombre": "x", "descripcion": "y", "tipo": "preprocesado", "es_publico": "true"},
        files={"archivo": ("test_dummy_sin_token.py", SCRIPT_DUMMY_PREPROCESADO, "text/x-python")},
    )
    assert respuesta.status_code == 401


def test_subir_algoritmo_con_rol_biologo_devuelve_403(client, usuario_autenticado):
    respuesta = client.post(
        "/algoritmos",
        data={"nombre": "x", "descripcion": "y", "tipo": "preprocesado"},
        files={"archivo": ("test_dummy_biologo.py", SCRIPT_DUMMY_PREPROCESADO, "text/x-python")},
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 403


def test_subir_algoritmo_valido_como_desarrollador(client, desarrollador_autenticado):
    respuesta = client.post(
        "/algoritmos",
        data={
            "nombre": "Dummy de test",
            "descripcion": "Algoritmo de prueba para la suite de tests",
            "tipo": "preprocesado",
            "es_publico": "true",
        },
        files={"archivo": ("test_dummy_algoritmo.py", SCRIPT_DUMMY_PREPROCESADO, "text/x-python")},
        headers=desarrollador_autenticado["headers"],
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["tipo"] == "preprocesado"
    assert cuerpo["ruta_archivo"] == "test_dummy_algoritmo.py"
    # El autor se toma del token, no de un campo del formulario (que ya no existe).
    assert cuerpo["autor_id"] == desarrollador_autenticado["usuario"]["id"]


def test_subir_algoritmo_con_tipo_no_coincidente_devuelve_400(client, desarrollador_autenticado):
    respuesta = client.post(
        "/algoritmos",
        data={"nombre": "x", "descripcion": "y", "tipo": "alineacion"},  # el script declara "preprocesado"
        files={"archivo": ("test_dummy_mismatch.py", SCRIPT_DUMMY_PREPROCESADO, "text/x-python")},
        headers=desarrollador_autenticado["headers"],
    )
    assert respuesta.status_code == 400
    assert "no coincide" in respuesta.json()["detail"]


def test_subir_algoritmo_con_extension_no_python_devuelve_400(client, desarrollador_autenticado):
    respuesta = client.post(
        "/algoritmos",
        data={"nombre": "x", "descripcion": "y", "tipo": "preprocesado"},
        files={"archivo": ("test_dummy.txt", b"no soy un script", "text/plain")},
        headers=desarrollador_autenticado["headers"],
    )
    assert respuesta.status_code == 400


def test_listar_algoritmos_es_publico_no_requiere_token(client, desarrollador_autenticado):
    respuesta_subida = client.post(
        "/algoritmos",
        data={"nombre": "Dummy listable", "descripcion": "Para comprobar el listado", "tipo": "preprocesado"},
        files={"archivo": ("test_dummy_listable.py", SCRIPT_DUMMY_PREPROCESADO, "text/x-python")},
        headers=desarrollador_autenticado["headers"],
    )
    id_creado = respuesta_subida.json()["id"]

    respuesta_listado = client.get(
        "/algoritmos", headers=desarrollador_autenticado["headers"]
    )
    assert respuesta_listado.status_code == 200
    ids = [a["id"] for a in respuesta_listado.json()]
    assert id_creado in ids


def test_listar_algoritmos_sin_token_devuelve_401(client):
    """El catalogo expone el nombre de cada script del servidor, asi que la
    lectura dejo de ser publica: solo la consume la interfaz, ya autenticada."""
    assert client.get("/algoritmos").status_code == 401
