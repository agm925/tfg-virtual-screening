"""
Tests del banco de pruebas con la interfaz que declara el autor (spec 013):
sus entradas, como recibe la salida y sus opciones de si/no.

El caso real es tests/fixtures/clean_hidrogens.py, el script con el que el
tutor se encontro el problema: se usa como `entrada -o salida --all`, y el
banco lo llamaba siempre `entrada salida`.
"""
import json
import os

import pytest
from fastapi.testclient import TestClient

from app.banco_pruebas import probar_en_proceso, validar_interfaz

CLEAN_HIDROGENS = os.path.join(os.path.dirname(__file__), "fixtures", "clean_hidrogens.py")

INTERFAZ_CLEAN = {
    "entradas": [{"nombre": "Molécula", "clase": "molecula"}],
    "opcion_salida": "-o",
    "opciones": [{"opcion": "--all", "nombre": "Quitar todos los hidrógenos"}],
}


def _escribir(tmp_path, nombre, codigo):
    ruta = tmp_path / nombre
    ruta.write_text(codigo, encoding="utf-8")
    return str(ruta)


def _entradas(*clases):
    return [{"nombre": f"Entrada {i + 1}", "clase": c} for i, c in enumerate(clases)]


# --- CA1. El script del tutor ------------------------------------------------

def test_clean_hidrogens_pasa_con_su_interfaz():
    r = probar_en_proceso(CLEAN_HIDROGENS, "preprocesado", INTERFAZ_CLEAN)
    assert r.valido, (r.motivo, r.detalle)
    assert r.formato_salida == "molecula"


def test_clean_hidrogens_sin_interfaz_falla_y_dice_por_que():
    r = probar_en_proceso(CLEAN_HIDROGENS, "preprocesado")
    assert not r.valido
    # La llamada, con los nombres de las entradas y no con rutas del banco.
    assert "clean_hidrogens.py Molécula salida.sdf" in r.motivo
    # Y lo que dijo argparse, que es lo que el autor necesita leer.
    assert "unrecognized arguments" in r.detalle


# --- CA2. Varias entradas, y la clase de cada una -----------------------------

SCRIPT_CUATRO = """
import shutil, sys
entradas, salida = sys.argv[1:-1], sys.argv[-1]
assert len(entradas) == 4, f"esperaba 4 entradas y llegaron {len(entradas)}"
# Ficheros distintos. Las dos primeras son la misma molecula en dos
# conformaciones (ligando_a y ligando_b), como necesitan las comparaciones tipo
# RMSD; las demas, moleculas distintas.
contenidos = {open(e, "rb").read() for e in entradas}
assert len(contenidos) == 4, "cada entrada debe recibir un fichero distinto"
shutil.copy(entradas[0], salida)
"""


def test_un_script_de_cuatro_moleculas_pasa_declarando_cuatro(tmp_path):
    ruta = _escribir(tmp_path, "cuatro.py", SCRIPT_CUATRO)
    interfaz = {"entradas": _entradas("molecula", "molecula", "molecula", "molecula")}

    r = probar_en_proceso(ruta, "preprocesado", interfaz)

    assert r.valido, (r.motivo, r.detalle)


def test_el_mismo_script_sin_declararlas_falla(tmp_path):
    ruta = _escribir(tmp_path, "cuatro.py", SCRIPT_CUATRO)
    r = probar_en_proceso(ruta, "preprocesado")
    assert not r.valido
    assert "esperaba 4 entradas" in r.detalle


def test_las_entradas_de_proteina_reciben_un_receptor_cada_una(tmp_path):
    ruta = _escribir(tmp_path, "proteinas.py", """
import shutil, sys
mol, prot_a, prot_b, salida = sys.argv[1:]
assert mol.endswith(".sdf"), mol
assert prot_a.endswith(".pdbqt") and prot_b.endswith(".pdbqt"), (prot_a, prot_b)
assert prot_a != prot_b, "cada entrada debe tener su propio fichero"
shutil.copy(mol, salida)
""")
    interfaz = {"entradas": _entradas("molecula", "proteina", "proteina")}

    r = probar_en_proceso(ruta, "preprocesado", interfaz)

    assert r.valido, (r.motivo, r.detalle)


def test_con_opciones_se_prueba_tambien_con_todas_marcadas(tmp_path):
    """Dos pasadas: sin opciones y con todas. Un fallo en la segunda rechaza el algoritmo."""
    ruta = _escribir(tmp_path, "opcion_rota.py", """
import shutil, sys
if "--rapido" in sys.argv:
    sys.exit("con --rapido no funciono")
shutil.copy(sys.argv[1], sys.argv[2])
""")
    interfaz = {"entradas": _entradas("molecula"),
                "opciones": [{"opcion": "--rapido", "nombre": "Modo rápido"}]}

    r = probar_en_proceso(ruta, "preprocesado", interfaz)

    assert not r.valido
    assert "--rapido" in r.motivo
    assert "con --rapido no funciono" in r.detalle


# --- CA3. Interfaces que no valen ---------------------------------------------

@pytest.mark.parametrize("interfaz", [
    {"entradas": []},
    {"entradas": _entradas(*["molecula"] * 7)},
    {"entradas": [{"nombre": "X", "clase": "virus"}]},
    {"entradas": [{"nombre": "", "clase": "molecula"}]},
    {"entradas": [{"nombre": "dos\nlineas", "clase": "molecula"}]},
    {"entradas": [{"nombre": "x" * 41, "clase": "molecula"}]},
    {"entradas": _entradas("molecula"), "opcion_salida": "-o salida"},
    {"entradas": _entradas("molecula"), "opciones": [{"opcion": "--a;rm", "nombre": "x"}]},
    {"entradas": _entradas("molecula"), "opciones": [{"opcion": "--a", "nombre": "x"},
                                                     {"opcion": "--a", "nombre": "y"}]},
    {"entradas": _entradas("molecula"), "opcion_salida": "-o",
     "opciones": [{"opcion": "-o", "nombre": "x"}]},
    {"entradas": _entradas("molecula"), "opciones": [{"opcion": f"--o{i}", "nombre": "x"} for i in range(7)]},
    {"entradas": _entradas("molecula"), "sobra": 1},
])
def test_interfaces_invalidas(interfaz):
    with pytest.raises(ValueError):
        validar_interfaz(interfaz)


def test_una_interfaz_valida_se_normaliza():
    assert validar_interfaz({"entradas": [{"nombre": "  Ligando ", "clase": "molecula"}]}) == {
        "entradas": [{"nombre": "Ligando", "clase": "molecula"}],
        "opcion_salida": None,
        "opciones": [],
    }


def test_el_servicio_del_banco_vuelve_a_validar_la_interfaz(tmp_path):
    """No se fia de quien le llama: una interfaz invalida no llega a ejecutar nada."""
    from app.banco_servidor import app

    cliente = TestClient(app)
    r = cliente.post(
        "/probar",
        data={"tipo": "preprocesado", "interfaz": json.dumps({"entradas": []})},
        files={"archivo": ("x.py", b"raise SystemExit('no deberia ejecutarse')", "text/x-python")},
    )
    assert r.status_code == 400
