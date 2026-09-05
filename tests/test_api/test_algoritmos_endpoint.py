"""Tests de integracion: POST/GET /algoritmos (app/main.py), con JWT y rol."""

SCRIPT_DUMMY_PREPROCESADO = b"""# TIPO_ALGORITMO: preprocesado
print("dummy")
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

    respuesta_listado = client.get("/algoritmos")  # sin headers: la lectura del catalogo es publica
    assert respuesta_listado.status_code == 200
    ids = [a["id"] for a in respuesta_listado.json()]
    assert id_creado in ids
