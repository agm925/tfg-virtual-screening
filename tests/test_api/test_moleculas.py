"""Tests de integracion: /moleculas* (app/main.py).

Los tres endpoints exigen autenticacion. POST /moleculas/subir era anonimo
--"deposito libre de archivos"--, lo que permitia a cualquiera sin cuenta
escribir ficheros en el servidor sin limite de tamano ni de cantidad: basta
para llenar el disco. GET /moleculas y DELETE /moleculas/{nombre} ya lo
exigian desde el security-review anterior. Sigue siendo un deposito
COMPARTIDO entre usuarios autenticados, que es lo que permite reutilizar
una base de datos subida por un companero.
"""

CONTENIDO_MOL2_DUMMY = b"@<TRIPOS>MOLECULE\ndummy\n1 0 0 0 0\nSMALL\nNO_CHARGES\n"
CONTENIDO_SDF_DOS_MOLECULAS = b"mol1\n\n\n  0  0\nM  END\n$$$$\nmol2\n\n\n  0  0\nM  END\n$$$$\n"


def test_subir_molecula_individual(client, usuario_autenticado):
    respuesta = client.post(
        "/moleculas/subir",
        data={"tipo": "molecula"},
        files={"archivo": ("test_dummy_mol.mol2", CONTENIDO_MOL2_DUMMY, "chemical/x-mol2")},
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["nombre"] == "test_dummy_mol.mol2"
    assert cuerpo["tipo"] == "molecula"
    assert cuerpo["num_moleculas"] is None


def test_subir_base_de_datos_sdf_cuenta_moleculas(client, usuario_autenticado):
    respuesta = client.post(
        "/moleculas/subir",
        data={"tipo": "base_de_datos"},
        files={"archivo": ("test_dummy_bd.sdf", CONTENIDO_SDF_DOS_MOLECULAS, "chemical/x-mdl-sdfile")},
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["num_moleculas"] == 2


def test_subir_base_de_datos_no_sdf_devuelve_400(client, usuario_autenticado):
    respuesta = client.post(
        "/moleculas/subir",
        data={"tipo": "base_de_datos"},
        files={"archivo": ("test_dummy_bd.mol2", CONTENIDO_MOL2_DUMMY, "chemical/x-mol2")},
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 400


def test_subir_extension_no_soportada_devuelve_400(client, usuario_autenticado):
    respuesta = client.post(
        "/moleculas/subir",
        data={"tipo": "molecula"},
        files={"archivo": ("test_dummy.docx", b"contenido irrelevante", "application/octet-stream")},
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 400


def test_listar_moleculas_sin_token_devuelve_401(client):
    assert client.get("/moleculas").status_code == 401


def test_borrar_molecula_sin_token_devuelve_401(client):
    assert client.delete("/moleculas/test_dummy.mol2").status_code == 401


def test_borrar_molecula_del_deposito_publico(client, usuario_autenticado):
    headers = usuario_autenticado["headers"]
    client.post(
        "/moleculas/subir",
        data={"tipo": "molecula"},
        files={"archivo": ("test_dummy_borrar.mol2", CONTENIDO_MOL2_DUMMY, "chemical/x-mol2")},
        headers=usuario_autenticado["headers"],
    )
    respuesta_borrado = client.delete("/moleculas/test_dummy_borrar.mol2", headers=headers)
    assert respuesta_borrado.status_code == 200

    respuesta_doble_borrado = client.delete("/moleculas/test_dummy_borrar.mol2", headers=headers)
    assert respuesta_doble_borrado.status_code == 404


def test_borrar_molecula_de_peticion_ajena_devuelve_403(
    client, usuario_autenticado, desarrollador_autenticado, mock_celery
):
    # Crea una peticion real (propietario = usuario_autenticado) y comprueba
    # que otro usuario autenticado no puede borrar su fichero de entrada.
    # El doble debe escribir en el ultimo argumento: la subida ejecuta el
    # script contra las moleculas de referencia antes de aceptarlo, asi que
    # uno que no escribe nada seria rechazado igual que un algoritmo roto.
    script = (b"# TIPO_ALGORITMO: preprocesado\n"
              b"import shutil, sys\n"
              b"shutil.copyfile(sys.argv[1], sys.argv[-1])\n")
    algoritmo_id = client.post(
        "/algoritmos",
        data={"nombre": "dummy", "descripcion": "dummy", "tipo": "preprocesado"},
        files={"archivo": ("test_dummy_moleculas_algo.py", script, "text/x-python")},
        headers=desarrollador_autenticado["headers"],
    ).json()["id"]

    peticion = client.post(
        "/peticiones",
        data={"algoritmo_id": str(algoritmo_id)},
        files={"archivo_mol": ("test_dummy_ajeno.mol2", CONTENIDO_MOL2_DUMMY, "chemical/x-mol2")},
        headers=usuario_autenticado["headers"],
    ).json()

    respuesta = client.delete(
        f"/moleculas/{peticion['ruta_mol_original']}", headers=desarrollador_autenticado["headers"]
    )
    assert respuesta.status_code == 403


def test_listar_moleculas_respeta_limit_y_expone_total(client, usuario_autenticado):
    respuesta = client.get("/moleculas", params={"limit": 3, "offset": 0}, headers=usuario_autenticado["headers"])
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert len(cuerpo) <= 3
    assert "X-Total-Count" in respuesta.headers
    assert int(respuesta.headers["X-Total-Count"]) >= len(cuerpo)


def test_listar_moleculas_de_otro_usuario_sin_ser_admin_devuelve_403(client, usuario_autenticado, desarrollador_autenticado):
    respuesta = client.get(
        "/moleculas",
        params={"usuario_id": usuario_autenticado["usuario"]["id"]},
        headers=desarrollador_autenticado["headers"],
    )
    assert respuesta.status_code == 403


def test_subir_molecula_sin_token_devuelve_401(client):
    """El deposito dejo de ser anonimo: sin credenciales no se escribe nada."""
    respuesta = client.post(
        "/moleculas/subir",
        data={"tipo": "molecula"},
        files={"archivo": ("test_dummy_sin_token.mol2", CONTENIDO_MOL2_DUMMY, "chemical/x-mol2")},
    )
    assert respuesta.status_code == 401


def test_subida_que_excede_el_limite_devuelve_413(client, usuario_autenticado, monkeypatch):
    """
    El tope de tamano se aplica MIENTRAS se escribe, no despues: comprobarlo
    tras un read() completo no evitaria el consumo de memoria que pretende
    evitar. Se baja el limite a 1 KB para no mover megabytes en el test.
    """
    import app.main as main

    monkeypatch.setattr(main, "MAX_SUBIDA_BYTES", 1024)

    respuesta = client.post(
        "/moleculas/subir",
        data={"tipo": "molecula"},
        files={"archivo": ("test_dummy_gordo.mol2", b"x" * 5000, "chemical/x-mol2")},
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 413

    # Y no debe quedar un fichero a medio escribir en uploads/, que se
    # confundiria con una molecula valida.
    import os
    assert not os.path.exists(os.path.join("uploads", "test_dummy_gordo.mol2"))
