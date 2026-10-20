"""
Tests de integracion de la spec 013: la interfaz que declara el autor al subir
un algoritmo (entradas, salida y opciones), y como la usa el motor.
"""
import json
import os

import pytest

from app import models

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")

with open(os.path.join(FIXTURES, "clean_hidrogens.py"), "rb") as _f:
    CLEAN_HIDROGENS = _f.read()

INTERFAZ_CLEAN = {
    "entradas": [{"nombre": "Molécula", "clase": "molecula"}],
    "opcion_salida": "-o",
    "opciones": [{"opcion": "--all", "nombre": "Quitar todos los hidrógenos"}],
}

SCRIPT_COPIA = b"""import shutil, sys
shutil.copyfile(sys.argv[1], sys.argv[-1])
"""


def _subir(client, headers, contenido, interfaz=None, tipo="preprocesado", fichero="test_interfaz.py"):
    datos = {"nombre": "Algoritmo con interfaz", "descripcion": "spec 013", "tipo": tipo, "es_publico": "true"}
    if interfaz is not None:
        datos["interfaz"] = interfaz if isinstance(interfaz, str) else json.dumps(interfaz)
    return client.post("/algoritmos", data=datos, headers=headers,
                       files={"archivo": (fichero, contenido, "text/x-python")})


# --- R1. La subida guarda la interfaz -----------------------------------------

def test_clean_hidrogens_se_sube_con_su_interfaz(client, usuario_autenticado):
    """CA1."""
    r = _subir(client, usuario_autenticado["headers"], CLEAN_HIDROGENS, INTERFAZ_CLEAN,
               fichero="test_clean_hidrogens.py")

    assert r.status_code == 200, r.text
    assert r.json()["interfaz"] == INTERFAZ_CLEAN
    listado = client.get("/algoritmos", headers=usuario_autenticado["headers"]).json()
    assert next(a for a in listado if a["id"] == r.json()["id"])["interfaz"] == INTERFAZ_CLEAN


def test_clean_hidrogens_sin_interfaz_se_rechaza_explicando_la_llamada(client, usuario_autenticado):
    r = _subir(client, usuario_autenticado["headers"], CLEAN_HIDROGENS, fichero="test_clean_sin.py")

    assert r.status_code == 422
    detalle = r.json()["detail"]
    assert "Se ejecutó así: test_clean_sin.py Molécula salida.sdf" in detalle["motivo"]
    assert "unrecognized arguments" in detalle["detalle"]


def test_la_interfaz_de_siempre_de_su_tipo_se_guarda_como_null(client, db_session, usuario_autenticado):
    """Los nombres pueden cambiar, pero si se llama igual va por el camino de siempre."""
    interfaz = {"entradas": [{"nombre": "Ligando", "clase": "molecula"}]}
    r = _subir(client, usuario_autenticado["headers"], SCRIPT_COPIA, interfaz)

    assert r.status_code == 200, r.text
    assert r.json()["interfaz"] is None
    db_session.expire_all()
    assert db_session.get(models.Algoritmo, r.json()["id"]).interfaz is None


@pytest.mark.parametrize("interfaz", [
    "esto no es json",
    {"entradas": []},
    {"entradas": [{"nombre": "x", "clase": "virus"}]},
    {"entradas": [{"nombre": "x", "clase": "molecula"}], "opcion_salida": "-o; rm"},
])
def test_una_interfaz_invalida_se_rechaza_sin_ejecutar_nada(client, db_session, usuario_autenticado, interfaz):
    """CA3."""
    antes = db_session.query(models.Algoritmo).count()

    r = _subir(client, usuario_autenticado["headers"], SCRIPT_COPIA, interfaz)

    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str)
    assert db_session.query(models.Algoritmo).count() == antes


# --- R5. El motor llama con la interfaz (CA4, CA5) ----------------------------

def _algoritmo(db_session, usuario_id, nombre_fichero, tipo, interfaz, formato="molecula", clave=None):
    """Un algoritmo registrado con su .py en el catalogo (el fixture autouse lo borra)."""
    with open(os.path.join("algoritmos", nombre_fichero), "wb") as f:
        f.write(SCRIPT_COPIA)
    db_session.add(models.Algoritmo(
        nombre=nombre_fichero, descripcion="", tipo=models.TipoAlgoritmo(tipo),
        ruta_archivo=nombre_fichero, es_publico=True, autor_id=usuario_id,
        formato_salida=formato, clave_score=clave, verificado=True, interfaz=interfaz,
    ))
    db_session.commit()
    return nombre_fichero[:-3]


def _molecula(nombre):
    with open(os.path.join("uploads", nombre), "w") as f:
        f.write("mol\n$$$$\n")
    return nombre


def _grafo(tipo, algoritmo, conexiones, marcadas=()):
    """Un nodo de algoritmo y un nodo upload por cada (molecula, puerto)."""
    nodos = [{"id": f"{tipo}_9", "type": tipo,
              "data": {"algoritmo_ruta": algoritmo, "opciones_marcadas": list(marcadas)}}]
    aristas = []
    for i, (fichero, puerto) in enumerate(conexiones):
        nodos.append({"id": f"upload_{i}", "type": "upload", "data": {"nombre_archivo": fichero}})
        aristas.append({"source": f"upload_{i}", "target": f"{tipo}_9", "targetHandle": puerto})
    return {"nodes": nodos, "edges": aristas}


@pytest.fixture()
def espia(monkeypatch):
    """Sustituye ejecutar_algoritmo: anota la llamada y escribe la salida."""
    from app import workflow_executor
    llamadas = []

    def _falso(ruta, *archivos, flags=()):
        llamadas.append({"ruta": ruta, "archivos": list(archivos), "flags": list(flags)})
        with open(archivos[-1], "w") as f:
            f.write(json.dumps({"puntuacion": 0.75}) if archivos[-1].endswith(".json") else "mol\n$$$$\n")
        return {"exito": True, "log": "", "error": None}

    monkeypatch.setattr(workflow_executor, "ejecutar_algoritmo", _falso)
    return llamadas


def _ejecutar(grafo, usuario_id):
    from app.workflow_executor import WorkflowExecutor
    return WorkflowExecutor(grafo, usuario_id).ejecutar()


INTERFAZ_DOS = {
    "entradas": [{"nombre": "A", "clase": "molecula"}, {"nombre": "B", "clase": "molecula"}],
    "opcion_salida": "-o",
    "opciones": [{"opcion": "--all", "nombre": "Todo"}, {"opcion": "--rapido", "nombre": "Rápido"}],
}


def test_el_motor_llama_con_las_entradas_la_opcion_de_salida_y_las_opciones(
        db_session, usuario_autenticado, espia):
    uid = usuario_autenticado["usuario"]["id"]
    algoritmo = _algoritmo(db_session, uid, "test_interfaz_dos.py", "preprocesado", INTERFAZ_DOS)
    a, b = _molecula("test_interfaz_a.sdf"), _molecula("test_interfaz_b.sdf")
    # --inyectado no esta declarada: el grafo lo manda el cliente y no puede
    # colar argumentos.
    grafo = _grafo("preprocesado", algoritmo, [(b, "entrada_1"), (a, "entrada_0")],
                   marcadas=["--all", "--inyectado"])

    resultado = _ejecutar(grafo, uid)

    assert resultado["errores"] == []
    llamada = espia[0]
    entradas, opcion, salida = llamada["archivos"][:2], llamada["archivos"][2], llamada["archivos"][3]
    assert entradas == [os.path.join("uploads", a), os.path.join("uploads", b)]
    assert opcion == "-o"
    assert salida.endswith(".sdf") and len(llamada["archivos"]) == 4
    assert llamada["flags"] == ["--all"]
    nodo = resultado["resultados"]["preprocesado_9"]
    assert nodo["tipo"] == "preprocesado" and nodo["archivo_salida"] == salida


def test_el_motor_avisa_de_una_entrada_sin_conectar(db_session, usuario_autenticado, espia):
    uid = usuario_autenticado["usuario"]["id"]
    algoritmo = _algoritmo(db_session, uid, "test_interfaz_falta.py", "preprocesado", INTERFAZ_DOS)
    grafo = _grafo("preprocesado", algoritmo, [(_molecula("test_interfaz_sola.sdf"), "entrada_0")])

    resultado = _ejecutar(grafo, uid)

    assert espia == []
    assert any("falta la entrada «B»" in e for e in resultado["errores"])


def test_una_comparacion_con_interfaz_que_puntua_conserva_su_clave(db_session, usuario_autenticado, espia):
    """La salida JSON se lee y se anota con la clave que observo el banco: el cribado la usa."""
    uid = usuario_autenticado["usuario"]["id"]
    interfaz = {"entradas": [{"nombre": "Ligando", "clase": "molecula"},
                             {"nombre": "Ref 1", "clase": "molecula"},
                             {"nombre": "Ref 2", "clase": "molecula"}]}
    algoritmo = _algoritmo(db_session, uid, "test_interfaz_cmp.py", "comparacion", interfaz,
                           formato="json", clave="puntuacion")
    grafo = _grafo("comparacion", algoritmo, [(_molecula(f"test_interfaz_c{i}.sdf"), f"entrada_{i}")
                                              for i in range(3)])

    resultado = _ejecutar(grafo, uid)

    assert resultado["errores"] == []
    assert espia[0]["archivos"][-1].endswith(".json") and len(espia[0]["archivos"]) == 4
    nodo = resultado["resultados"]["comparacion_9"]
    assert nodo["tipo"] == "comparacion"
    assert nodo["clave_score"] == "puntuacion"
    assert nodo["resultado_json"] == {"puntuacion": 0.75}


def test_un_algoritmo_sin_interfaz_se_llama_como_siempre(db_session, usuario_autenticado, espia):
    """CA5: entrada y salida, por los puertos de siempre."""
    uid = usuario_autenticado["usuario"]["id"]
    algoritmo = _algoritmo(db_session, uid, "test_sin_interfaz.py", "preprocesado", None)
    grafo = _grafo("preprocesado", algoritmo, [(_molecula("test_sin_interfaz.sdf"), "input_molecula")])

    resultado = _ejecutar(grafo, uid)

    assert resultado["errores"] == []
    assert len(espia[0]["archivos"]) == 2 and espia[0]["flags"] == []
