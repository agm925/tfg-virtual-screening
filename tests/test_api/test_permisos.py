"""
Tests de app/permisos.py: las reglas de acceso a uploads/ y el barrido del
grafo que aplican tanto el endpoint que encola como el worker.

Los tests de test_workflows.py cubren el camino HTTP (403 al lanzar). Estos
cubren la capa que corre DENTRO del worker, que es la que de verdad abre el
fichero y la que los tests de endpoint no ejecutan, porque mock_celery
sustituye el .delay().
"""
from app import models, permisos
from app.tasks import _grafo_usa_archivo_ajeno


def _registrar(db_session, nombre, propietario_id, visibilidad):
    db_session.add(models.Archivo(
        nombre=nombre,
        visibilidad=models.VisibilidadArchivo(visibilidad),
        propietario_id=propietario_id,
        tamano_bytes=10,
    ))
    db_session.commit()


def _grafo(*nombres):
    return {
        "nodes": [
            {"id": f"n{i}", "type": "selectMol", "data": {"nombre_archivo": n}}
            for i, n in enumerate(nombres)
        ],
        "edges": [],
    }


# --- Extraccion de nombres del grafo -----------------------------------------

def test_nombres_del_grafo_recoge_los_tres_tipos_de_nodo_de_entrada():
    grafo = {
        "nodes": [
            {"id": "a", "type": "upload",    "data": {"nombre_archivo": "subida.mol2"}},
            {"id": "b", "type": "selectMol", "data": {"nombre_archivo": "molecula.sdf"}},
            {"id": "c", "type": "selectDB",  "data": {"nombre_archivo": "base.sdf"}},
        ],
        "edges": [],
    }
    assert permisos.nombres_de_archivo_del_grafo(grafo) == ["base.sdf", "molecula.sdf", "subida.mol2"]


def test_nombres_del_grafo_ignora_nodos_sin_archivo_y_deduplica():
    grafo = {
        "nodes": [
            {"id": "a", "type": "selectMol", "data": {"nombre_archivo": "x.sdf"}},
            {"id": "b", "type": "selectMol", "data": {"nombre_archivo": "x.sdf"}},
            {"id": "c", "type": "docking",   "data": {"exhaustiveness": 8}},
            {"id": "d", "type": "selectMol", "data": {"nombre_archivo": ""}},
            {"id": "e", "type": "selectMol"},
            "no soy un nodo",
        ],
        "edges": [],
    }
    assert permisos.nombres_de_archivo_del_grafo(grafo) == ["x.sdf"]


def test_nombres_del_grafo_tolera_un_grafo_vacio_o_nulo():
    assert permisos.nombres_de_archivo_del_grafo({}) == []
    assert permisos.nombres_de_archivo_del_grafo(None) == []


# --- La comprobacion que corre en el worker ----------------------------------

def test_worker_rechaza_el_resultado_de_otro(db_session, usuario_autenticado, otro_usuario_autenticado):
    nombre = "docking_n1_e88888.sdf"
    _registrar(db_session, nombre, otro_usuario_autenticado["usuario"]["id"], "resultado")

    motivo = _grafo_usa_archivo_ajeno(
        db_session, _grafo(nombre), usuario_autenticado["usuario"]["id"])

    assert motivo is not None
    assert nombre in motivo


def test_worker_acepta_la_biblioteca_de_otro(db_session, usuario_autenticado, otro_usuario_autenticado):
    nombre = "biblioteca_worker_test.sdf"
    _registrar(db_session, nombre, otro_usuario_autenticado["usuario"]["id"], "biblioteca")

    motivo = _grafo_usa_archivo_ajeno(
        db_session, _grafo(nombre), usuario_autenticado["usuario"]["id"])

    assert motivo is None


def test_worker_acepta_el_resultado_propio(db_session, usuario_autenticado):
    nombre = "resultado_worker_propio_e88887.sdf"
    _registrar(db_session, nombre, usuario_autenticado["usuario"]["id"], "resultado")

    motivo = _grafo_usa_archivo_ajeno(
        db_session, _grafo(nombre), usuario_autenticado["usuario"]["id"])

    assert motivo is None


def test_worker_acepta_un_fichero_sin_registrar(db_session, usuario_autenticado):
    """
    Los ficheros anteriores al registro de propiedad no tienen fila en
    `archivos`. Se tratan como biblioteca compartida, que es como se
    comportaban antes; scripts/migrate.py los da de alta al arrancar.
    """
    motivo = _grafo_usa_archivo_ajeno(
        db_session, _grafo("heredado_sin_registro.mol2"), usuario_autenticado["usuario"]["id"])

    assert motivo is None


def test_worker_deja_pasar_al_admin(db_session, admin_autenticado, usuario_autenticado):
    nombre = "docking_n1_e88886.sdf"
    _registrar(db_session, nombre, usuario_autenticado["usuario"]["id"], "resultado")

    motivo = _grafo_usa_archivo_ajeno(
        db_session, _grafo(nombre), admin_autenticado["usuario"]["id"])

    assert motivo is None


def test_worker_senala_el_primer_archivo_problematico_de_varios(
    db_session, usuario_autenticado, otro_usuario_autenticado
):
    """Un flujo con varias entradas se rechaza entero, no a medias."""
    propio = "entrada_propia_e88885.sdf"
    ajeno = "aaa_ajeno_e88884.sdf"
    _registrar(db_session, propio, usuario_autenticado["usuario"]["id"], "resultado")
    _registrar(db_session, ajeno, otro_usuario_autenticado["usuario"]["id"], "resultado")

    motivo = _grafo_usa_archivo_ajeno(
        db_session, _grafo(propio, ajeno), usuario_autenticado["usuario"]["id"])

    assert motivo is not None
    assert ajeno in motivo


# ---------------------------------------------------------------------------
# Visibilidad de algoritmos en el motor de workflows.
#
# El grafo lo manda el cliente y referencia el algoritmo por el NOMBRE de su
# .py, no por su id, asi que ocultarlo del catalogo no impide nombrarlo. Es el
# mismo razonamiento que con los ficheros de uploads/: filtrar el listado no
# es control de acceso. La comprobacion vive en resolver_algoritmo
# (app/workflow_executor.py), que es por donde pasan los cuatro tipos de nodo
# que ejecutan un script.
# ---------------------------------------------------------------------------

def _registrar_algoritmo(db_session, nombre_fichero, autor_id, es_publico, activo=True):
    from app import models
    import os

    ruta = os.path.join("algoritmos", nombre_fichero)
    with open(ruta, "wb") as f:
        f.write(b"import shutil, sys\nshutil.copyfile(sys.argv[1], sys.argv[-1])\n")
    alg = models.Algoritmo(
        nombre=f"Test {nombre_fichero}", descripcion="test",
        tipo=models.TipoAlgoritmo.preprocesado, ruta_archivo=nombre_fichero,
        es_publico=es_publico, activo=activo, autor_id=autor_id,
    )
    db_session.add(alg)
    db_session.commit()
    return alg


def test_el_motor_rechaza_un_algoritmo_privado_de_otro_usuario(
    db_session, usuario_autenticado, otro_usuario_autenticado
):
    import pytest

    from app.workflow_executor import resolver_algoritmo

    _registrar_algoritmo(db_session, "test_dummy_wf_privado.py",
                         autor_id=otro_usuario_autenticado["usuario"]["id"], es_publico=False)

    with pytest.raises(ValueError, match="privado"):
        resolver_algoritmo("test_dummy_wf_privado", usuario_autenticado["usuario"]["id"])


def test_el_motor_deja_al_autor_usar_su_propio_algoritmo_privado(
    db_session, usuario_autenticado
):
    from app.workflow_executor import resolver_algoritmo

    _registrar_algoritmo(db_session, "test_dummy_wf_propio.py",
                         autor_id=usuario_autenticado["usuario"]["id"], es_publico=False)

    assert resolver_algoritmo("test_dummy_wf_propio",
                              usuario_autenticado["usuario"]["id"]).endswith(".py")


def test_el_motor_deja_pasar_los_algoritmos_publicos(
    db_session, usuario_autenticado, otro_usuario_autenticado
):
    from app.workflow_executor import resolver_algoritmo

    _registrar_algoritmo(db_session, "test_dummy_wf_publico.py",
                         autor_id=otro_usuario_autenticado["usuario"]["id"], es_publico=True)

    assert resolver_algoritmo("test_dummy_wf_publico",
                              usuario_autenticado["usuario"]["id"]).endswith(".py")


def test_el_motor_sigue_aceptando_un_script_sin_fila_en_la_base(db_session, usuario_autenticado):
    """
    Los .py que vienen con el repositorio no tienen fila en `algoritmos`. Aqui
    se aplica una privacidad explicita, no se exige estar registrado.
    """
    import os

    from app.workflow_executor import resolver_algoritmo

    ruta = os.path.join("algoritmos", "test_dummy_wf_sin_registro.py")
    with open(ruta, "wb") as f:
        f.write(b"import shutil, sys\nshutil.copyfile(sys.argv[1], sys.argv[-1])\n")

    assert resolver_algoritmo("test_dummy_wf_sin_registro",
                              usuario_autenticado["usuario"]["id"]).endswith(".py")
