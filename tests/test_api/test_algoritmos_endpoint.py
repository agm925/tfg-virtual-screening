"""Tests de integracion: POST/GET /algoritmos (app/main.py), con JWT."""

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


def test_subir_algoritmo_valido_como_biologo(client, usuario_autenticado):
    """
    El rol por defecto (biologo) puede subir al catalogo: la subida ya no
    esta restringida por rol, solo por el banco de pruebas.
    """
    respuesta = client.post(
        "/algoritmos",
        data={
            "nombre": "Dummy de test",
            "descripcion": "Algoritmo de prueba para la suite de tests",
            "tipo": "preprocesado",
            "es_publico": "true",
        },
        files={"archivo": ("test_dummy_algoritmo.py", SCRIPT_DUMMY_PREPROCESADO, "text/x-python")},
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["tipo"] == "preprocesado"
    assert cuerpo["ruta_archivo"] == "test_dummy_algoritmo.py"
    # El autor se toma del token, no de un campo del formulario (que ya no existe).
    assert cuerpo["autor_id"] == usuario_autenticado["usuario"]["id"]


def test_subir_algoritmo_sin_metadato_tipo_algoritmo_funciona(client, usuario_autenticado):
    """
    El tipo lo declara el formulario, no un comentario en el script: ya no
    hace falta `# TIPO_ALGORITMO` en el fichero, y su ausencia no rechaza la
    subida (antes sí: era exactamente el motivo del 400 "no se encontró el
    metadato").
    """
    script_sin_metadato = b"""import shutil
import sys

entrada, salida = sys.argv[1], sys.argv[-1]
shutil.copyfile(entrada, salida)
print("dummy: sin metadato TIPO_ALGORITMO")
"""
    respuesta = client.post(
        "/algoritmos",
        data={"nombre": "x", "descripcion": "y", "tipo": "preprocesado"},
        files={"archivo": ("test_dummy_sin_metadato.py", script_sin_metadato, "text/x-python")},
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["tipo"] == "preprocesado"


def test_subir_algoritmo_ignora_un_metadato_tipo_algoritmo_distinto(client, usuario_autenticado):
    """
    El comentario `# TIPO_ALGORITMO` del script ya no se lee: manda el tipo
    del formulario, aunque el script diga otra cosa (p. ej. un resto de una
    versión anterior del algoritmo, o simple copia y pega de otro script).
    "preprocesado" y "alineacion" invocan el script igual --una sola
    molécula-- así que el mismo doble sirve para demostrarlo sin más cambios.
    """
    respuesta = client.post(
        "/algoritmos",
        # SCRIPT_DUMMY_PREPROCESADO declara "# TIPO_ALGORITMO: preprocesado"
        # en su primera línea; el formulario pide "alineacion".
        data={"nombre": "x", "descripcion": "y", "tipo": "alineacion"},
        files={"archivo": ("test_dummy_metadato_distinto.py", SCRIPT_DUMMY_PREPROCESADO, "text/x-python")},
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["tipo"] == "alineacion"


def test_subir_algoritmo_con_extension_no_python_devuelve_400(client, usuario_autenticado):
    respuesta = client.post(
        "/algoritmos",
        data={"nombre": "x", "descripcion": "y", "tipo": "preprocesado"},
        files={"archivo": ("test_dummy.txt", b"no soy un script", "text/plain")},
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 400


def test_listar_algoritmos_es_publico_no_requiere_token(client, usuario_autenticado):
    respuesta_subida = client.post(
        "/algoritmos",
        data={"nombre": "Dummy listable", "descripcion": "Para comprobar el listado", "tipo": "preprocesado"},
        files={"archivo": ("test_dummy_listable.py", SCRIPT_DUMMY_PREPROCESADO, "text/x-python")},
        headers=usuario_autenticado["headers"],
    )
    id_creado = respuesta_subida.json()["id"]

    respuesta_listado = client.get(
        "/algoritmos", headers=usuario_autenticado["headers"]
    )
    assert respuesta_listado.status_code == 200
    ids = [a["id"] for a in respuesta_listado.json()]
    assert id_creado in ids


def test_listar_algoritmos_sin_token_devuelve_401(client):
    """El catalogo expone el nombre de cada script del servidor, asi que la
    lectura dejo de ser publica: solo la consume la interfaz, ya autenticada."""
    assert client.get("/algoritmos").status_code == 401


# ---------------------------------------------------------------------------
# es_publico: la columna existia y no la leia NADIE.
#
# El catalogo entero se servia a cualquier usuario autenticado, se podia
# ejecutar el algoritmo privado de otro indicando su id en el formulario, y el
# boton "Hacer privado" del panel de administracion no tenia ningun efecto.
# El frontend siempre sube con es_publico=true (Algoritmos.jsx), asi que en la
# practica esto solo afecta a lo que se marca privado a proposito.
# ---------------------------------------------------------------------------

def _subir(client, headers, nombre_fichero, es_publico):
    respuesta = client.post(
        "/algoritmos",
        data={"nombre": f"Privacidad {nombre_fichero}", "descripcion": "test",
              "tipo": "preprocesado", "es_publico": "true" if es_publico else "false"},
        files={"archivo": (nombre_fichero, SCRIPT_DUMMY_PREPROCESADO, "text/x-python")},
        headers=headers,
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["id"]


def test_el_catalogo_no_muestra_los_algoritmos_privados_de_otro(
    client, usuario_autenticado, otro_usuario_autenticado
):
    privado = _subir(client, otro_usuario_autenticado["headers"],
                     "test_dummy_privado_ajeno.py", es_publico=False)
    publico = _subir(client, otro_usuario_autenticado["headers"],
                     "test_dummy_publico_ajeno.py", es_publico=True)

    ids = [a["id"] for a in client.get(
        "/algoritmos?limit=500", headers=usuario_autenticado["headers"]).json()]
    assert publico in ids, "un algoritmo publico debe verse"
    assert privado not in ids, "el privado de otro usuario NO debe aparecer"


def test_el_autor_si_ve_su_propio_algoritmo_privado(client, usuario_autenticado):
    privado = _subir(client, usuario_autenticado["headers"],
                     "test_dummy_privado_propio.py", es_publico=False)
    ids = [a["id"] for a in client.get(
        "/algoritmos?limit=500", headers=usuario_autenticado["headers"]).json()]
    assert privado in ids


def test_el_admin_ve_tambien_los_privados_ajenos(
    client, admin_autenticado, otro_usuario_autenticado
):
    """El panel de administracion tiene que poder administrarlos."""
    privado = _subir(client, otro_usuario_autenticado["headers"],
                     "test_dummy_privado_para_admin.py", es_publico=False)
    ids = [a["id"] for a in client.get(
        "/algoritmos?limit=500", headers=admin_autenticado["headers"]).json()]
    assert privado in ids


def test_no_se_puede_lanzar_una_peticion_con_un_algoritmo_privado_ajeno(
    client, mock_celery, usuario_autenticado, otro_usuario_autenticado
):
    """
    El id va en el formulario, asi que ocultarlo del desplegable no basta:
    hay que rechazarlo tambien al ejecutar.
    """
    privado = _subir(client, otro_usuario_autenticado["headers"],
                     "test_dummy_privado_peticion.py", es_publico=False)

    respuesta = client.post(
        "/peticiones",
        data={"algoritmo_id": str(privado)},
        files={"archivo_mol": ("test_dummy_privado_entrada.mol2",
                               b"@<TRIPOS>MOLECULE\ndummy\n1 0 0 0 0\nSMALL\nNO_CHARGES\n",
                               "chemical/x-mol2")},
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 403
    assert len(mock_celery) == 0


def test_subir_un_algoritmo_con_nombre_ocupado_no_pisa_el_del_otro(
    client, usuario_autenticado, otro_usuario_autenticado
):
    """
    Dos algoritmos con el mismo nombre de fichero: el segundo se renombra.

    Antes `shutil.move` sobreescribia el .py sin preguntar. El efecto no era
    solo un catalogo con duplicados --de ahi salia el filtroLipinski.py
    repetido-- sino que la PRIMERA entrada pasaba a ejecutar el codigo de la
    segunda: un script validado por el banco de pruebas acababa corriendo otro
    que ese banco nunca vio, y cualquiera podia reemplazar el algoritmo de
    otro usuario subiendo uno con su mismo nombre.
    """
    original = b"import shutil, sys\nshutil.copyfile(sys.argv[1], sys.argv[-1])\nprint('ORIGINAL')\n"
    segundo = b"import shutil, sys\nshutil.copyfile(sys.argv[1], sys.argv[-1])\nprint('SEGUNDO')\n"

    primera = client.post(
        "/algoritmos",
        data={"nombre": "Colision A", "descripcion": "test", "tipo": "preprocesado",
              "es_publico": "true"},
        files={"archivo": ("test_dummy_colision.py", original, "text/x-python")},
        headers=usuario_autenticado["headers"],
    )
    assert primera.status_code == 200, primera.text
    ruta_primera = primera.json()["ruta_archivo"]

    segunda = client.post(
        "/algoritmos",
        data={"nombre": "Colision B", "descripcion": "test", "tipo": "preprocesado",
              "es_publico": "true"},
        files={"archivo": ("test_dummy_colision.py", segundo, "text/x-python")},
        headers=otro_usuario_autenticado["headers"],
    )
    assert segunda.status_code == 200, segunda.text
    ruta_segunda = segunda.json()["ruta_archivo"]

    assert ruta_primera != ruta_segunda, "el segundo debe renombrarse, no reutilizar el nombre"

    # Y sobre todo: el script del primero sigue siendo el suyo.
    import os
    with open(os.path.join("algoritmos", ruta_primera), "rb") as f:
        assert b"ORIGINAL" in f.read(), "el segundo usuario ha sobreescrito el algoritmo del primero"
