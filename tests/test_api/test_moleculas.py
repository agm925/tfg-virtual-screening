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
CONTENIDO_SDF_UNA_MOLECULA = b"mol1\n\n\n  0  0\nM  END\n$$$$\n"


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
    client, usuario_autenticado, otro_usuario_autenticado, mock_celery
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
        data={"nombre": "dummy", "descripcion": "dummy", "tipo": "preprocesado", "es_publico": "true"},
        files={"archivo": ("test_dummy_moleculas_algo.py", script, "text/x-python")},
        headers=otro_usuario_autenticado["headers"],
    ).json()["id"]

    peticion = client.post(
        "/peticiones",
        data={"algoritmo_id": str(algoritmo_id)},
        files={"archivo_mol": ("test_dummy_ajeno.mol2", CONTENIDO_MOL2_DUMMY, "chemical/x-mol2")},
        headers=usuario_autenticado["headers"],
    ).json()

    respuesta = client.delete(
        f"/moleculas/{peticion['ruta_mol_original']}", headers=otro_usuario_autenticado["headers"]
    )
    assert respuesta.status_code == 403


def test_listar_moleculas_respeta_limit_y_expone_total(client, usuario_autenticado):
    respuesta = client.get("/moleculas", params={"limit": 3, "offset": 0}, headers=usuario_autenticado["headers"])
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert len(cuerpo) <= 3
    assert "X-Total-Count" in respuesta.headers
    assert int(respuesta.headers["X-Total-Count"]) >= len(cuerpo)


def test_listar_moleculas_de_otro_usuario_sin_ser_admin_devuelve_403(client, usuario_autenticado, otro_usuario_autenticado):
    respuesta = client.get(
        "/moleculas",
        params={"usuario_id": usuario_autenticado["usuario"]["id"]},
        headers=otro_usuario_autenticado["headers"],
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


# ---------------------------------------------------------------------------
# archivos.tipo: verificado contra el contenido, no copiado del formulario.
#
# Antes /moleculas/subir aceptaba cualquier `tipo` sin validarlo mas que para
# exigir .sdf en "base_de_datos", y lo que se guardaba (de hecho, lo que no se
# guardaba en absoluto: la columna no existia) era literalmente lo que decia
# el formulario. El icono de la interfaz salia entonces de `visibilidad`, asi
# que un fichero PRIVADO (el resultado de una peticion) se mostraba como
# "base de datos" aunque fuera una molecula corriente. Ver app/models.py
# (TipoArchivo) y /moleculas/subir en app/main.py.
# ---------------------------------------------------------------------------

def test_subir_sdf_de_una_molecula_se_guarda_como_molecula_aunque_se_declare_base_de_datos(
    client, usuario_autenticado
):
    respuesta = client.post(
        "/moleculas/subir",
        data={"tipo": "base_de_datos"},
        files={"archivo": ("test_dummy_bd_de_una.sdf", CONTENIDO_SDF_UNA_MOLECULA, "chemical/x-mdl-sdfile")},
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["tipo"] == "molecula"
    assert cuerpo["num_moleculas"] == 1


def test_subir_sdf_de_varias_moleculas_se_guarda_como_base_de_datos_aunque_se_declare_molecula(
    client, usuario_autenticado
):
    respuesta = client.post(
        "/moleculas/subir",
        data={"tipo": "molecula"},
        files={"archivo": ("test_dummy_mol_multiple.sdf", CONTENIDO_SDF_DOS_MOLECULAS, "chemical/x-mdl-sdfile")},
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["tipo"] == "base_de_datos"
    assert cuerpo["num_moleculas"] == 2


def test_subir_molecula_con_tipo_invalido_devuelve_400(client, usuario_autenticado):
    respuesta = client.post(
        "/moleculas/subir",
        data={"tipo": "no_es_un_tipo_valido"},
        files={"archivo": ("test_dummy_tipo_invalido.mol2", CONTENIDO_MOL2_DUMMY, "chemical/x-mol2")},
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 400


def test_listar_moleculas_devuelve_tipo_y_num_moleculas(client, usuario_autenticado):
    subida = client.post(
        "/moleculas/subir",
        data={"tipo": "base_de_datos"},
        files={"archivo": ("test_dummy_listado_tipo.sdf", CONTENIDO_SDF_DOS_MOLECULAS, "chemical/x-mdl-sdfile")},
        headers=usuario_autenticado["headers"],
    )
    nombre = subida.json()["nombre"]

    listado = client.get("/moleculas?limit=500", headers=usuario_autenticado["headers"])
    assert listado.status_code == 200
    fila = next(m for m in listado.json() if m["nombre"] == nombre)
    assert fila["tipo"] == "base_de_datos"
    assert fila["num_moleculas"] == 2


def test_molecula_de_peticion_se_registra_como_molecula_no_como_resultado(
    client, mock_celery, usuario_autenticado
):
    """
    La molecula de entrada de una peticion es privada (visibilidad=resultado)
    pero su CONTENIDO sigue siendo una molecula corriente, no algo que haya
    calculado la plataforma. Antes de existir la columna `tipo`, el unico eje
    era `visibilidad`, y este fichero se mostraba en la interfaz con el
    mismo icono que un resultado de docking o un ranking de cribado.
    """
    import uuid

    script_preprocesado = (
        b"# TIPO_ALGORITMO: preprocesado\n"
        b"import shutil, sys\n"
        b"entrada, salida = sys.argv[1], sys.argv[-1]\n"
        b"shutil.copyfile(entrada, salida)\n"
    )
    subida_algoritmo = client.post(
        "/algoritmos",
        data={"nombre": "Dummy tipo peticion", "descripcion": "test", "tipo": "preprocesado", "es_publico": "true"},
        files={"archivo": (f"test_dummy_{uuid.uuid4().hex[:8]}.py", script_preprocesado, "text/x-python")},
        headers=usuario_autenticado["headers"],
    )
    assert subida_algoritmo.status_code == 200, subida_algoritmo.text
    algoritmo_id = subida_algoritmo.json()["id"]

    peticion = client.post(
        "/peticiones",
        data={"algoritmo_id": algoritmo_id},
        files={"archivo_mol": ("test_dummy_entrada_peticion.mol2", CONTENIDO_MOL2_DUMMY, "chemical/x-mol2")},
        headers=usuario_autenticado["headers"],
    )
    assert peticion.status_code == 200, peticion.text

    listado = client.get("/moleculas?limit=500", headers=usuario_autenticado["headers"])
    fila = next(m for m in listado.json() if m["nombre"] == "test_dummy_entrada_peticion.mol2")
    assert fila["tipo"] == "molecula"


def test_registrar_resultados_marca_tipo_resultado(client, db_session, usuario_autenticado):
    """
    Lo que produce la propia plataforma --la salida de un algoritmo, no lo
    que sube un usuario-- se registra con tipo=resultado. A diferencia de la
    molecula de entrada de una peticion (test anterior), aqui SI es correcto
    que tipo coincida con visibilidad=resultado: es justo lo que ese tipo
    significa.
    """
    import os

    from app.tasks import _registrar_resultados

    nombre = "test_dummy_salida_algoritmo.sdf"
    with open(os.path.join("uploads", nombre), "wb") as f:
        f.write(CONTENIDO_SDF_UNA_MOLECULA)

    _registrar_resultados(db_session, [nombre], usuario_autenticado["usuario"]["id"])

    from app import models
    archivo = db_session.query(models.Archivo).filter(models.Archivo.nombre == nombre).first()
    assert archivo is not None
    assert archivo.tipo == models.TipoArchivo.resultado
    assert archivo.visibilidad == models.VisibilidadArchivo.resultado



def test_subir_una_biblioteca_deja_su_indice_y_borrarla_lo_quita(client, usuario_autenticado):
    """
    El indice de posiciones se construye al subir (ver app/indice_sdf.py), que
    es cuando el fichero ya se esta leyendo entero para contar sus moleculas.
    Y se va con el fichero: un indice huerfano no hace dano, pero es basura en
    uploads/.indices/.
    """
    import os

    from app import indice_sdf

    respuesta = client.post(
        "/moleculas/subir",
        data={"tipo": "base_de_datos"},
        files={"archivo": ("test_indice_bd.sdf", CONTENIDO_SDF_DOS_MOLECULAS, "chemical/x-mdl-sdfile")},
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 200, respuesta.text
    nombre = respuesta.json()["nombre"]
    ruta = os.path.join("uploads", nombre)

    assert os.path.exists(indice_sdf.ruta_indice(ruta))
    assert len(indice_sdf.cargar(ruta)) - 1 == 2

    borrado = client.delete(f"/moleculas/{nombre}", headers=usuario_autenticado["headers"])
    assert borrado.status_code == 200, borrado.text
    assert not os.path.exists(indice_sdf.ruta_indice(ruta))
