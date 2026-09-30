"""
Un algoritmo lo puede subir cualquier usuario registrado, así que lo que ve al
ejecutarse no puede incluir los secretos del worker.
"""
import json
import os
import shutil
import tempfile
import time

import pytest

from app import ejecutor

# Hace lo mismo que haría un algoritmo malicioso: volcar a su salida todo lo
# que parezca un secreto, tanto de su entorno como del entorno del proceso 1
# (el worker, en Docker), que es la vía para saltarse un entorno filtrado.
SONDA = r'''
import json, os, sys
claves = ("JWT", "SECRET", "PASSWORD", "DATABASE", "SMTP", "SLURM")
propio = sorted(k for k in os.environ if any(c in k.upper() for c in claves))
try:
    proc1 = open("/proc/1/environ", "rb").read().decode(errors="ignore")
    del_worker = sorted(c for c in claves if c in proc1)
except OSError:
    del_worker = []
json.dump({"propio": propio, "del_worker": del_worker}, open(sys.argv[-1], "w"))
'''


@pytest.fixture
def carpeta():
    """Carpeta a la que puede entrar el usuario sin privilegios. La de
    tmp_path no vale: cuelga de /tmp/pytest-of-root, que es 700."""
    ruta = tempfile.mkdtemp(prefix="ejecutor_")
    os.chmod(ruta, 0o777)
    yield ruta
    shutil.rmtree(ruta, ignore_errors=True)


@pytest.fixture
def secretos(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "clave-de-prueba")
    monkeypatch.setenv("SMTP_PASSWORD", "correo-de-prueba")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db/x")
    # El entorno del hijo se calcula al importar: se recalcula con los secretos.
    monkeypatch.setattr(ejecutor, "_ENTORNO_HIJO", ejecutor._entorno_algoritmo())


def _lanzar_sonda(carpeta):
    sonda = os.path.join(carpeta, "sonda.py")
    with open(sonda, "w", encoding="utf-8") as f:
        f.write(SONDA)
    salida = os.path.join(carpeta, "salida.json")

    resultado = ejecutor._ejecutar_local(sonda, salida)

    assert resultado["exito"], resultado["error"]
    with open(salida, encoding="utf-8") as f:
        return json.load(f)


def test_el_algoritmo_no_hereda_los_secretos(secretos, carpeta):
    assert _lanzar_sonda(carpeta)["propio"] == []


def test_el_algoritmo_sigue_teniendo_lo_que_necesita(secretos):
    entorno = ejecutor._ENTORNO_HIJO
    assert entorno.get("PATH")
    assert entorno["PYTHONIOENCODING"] == "utf-8"
    assert entorno["HOME"]


@pytest.mark.skipif(os.name != "posix" or os.geteuid() != 0,
                    reason="solo se cambia de usuario cuando el worker es root (Docker)")
def test_como_root_el_algoritmo_no_lee_el_entorno_del_worker(carpeta):
    assert _lanzar_sonda(carpeta)["del_worker"] == []


# Algoritmos reales del catálogo por el mismo camino que una petición: que el
# entorno recortado y el cambio de usuario no les quiten nada que necesiten.
# Los tests de test_algoritmos/ no sirven para esto, porque lanzan el script
# directamente con subprocess.

def test_algoritmo_con_rdkit(carpeta, aspirina_sdf):
    entrada = shutil.copy(aspirina_sdf, carpeta)
    salida = os.path.join(carpeta, "lipinski.json")

    resultado = ejecutor._ejecutar_local(
        os.path.join("algoritmos", "filtroLipinski.py"), entrada, salida)

    assert resultado["exito"], resultado["error"]
    assert os.path.getsize(salida) > 0


def test_algoritmo_con_open_babel(carpeta, aspirina_mol2):
    entrada = shutil.copy(aspirina_mol2, carpeta)
    salida = os.path.join(carpeta, "preparada.mol2")

    resultado = ejecutor._ejecutar_local(
        os.path.join("algoritmos", "preparacionObabel.py"), entrada, salida)

    assert resultado["exito"], resultado["error"]
    assert os.path.getsize(salida) > 0


# ---------------------------------------------------------------------------
# Cancelacion: el worker se libera sin esperar a que acabe el algoritmo
# ---------------------------------------------------------------------------

def _script_lento(carpeta):
    ruta = os.path.join(carpeta, "lento.py")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("import time\ntime.sleep(60)\n")
    return ruta


def test_cancelar_mata_el_algoritmo_sin_esperar_a_que_acabe(carpeta):
    """
    Antes subprocess.run no volvia hasta que el algoritmo terminaba: un
    cribado cancelado seguia ocupando el worker, y la peticion siguiente se
    quedaba en cola detras.
    """
    inicio = time.monotonic()
    cancelar_en = inicio + 1.0

    with ejecutor.vigilar_cancelacion(lambda: time.monotonic() >= cancelar_en):
        resultado = ejecutor._ejecutar_local(
            _script_lento(carpeta), os.path.join(carpeta, "salida.json"))

    assert not resultado["exito"]
    assert "cancelada" in resultado["error"]
    assert time.monotonic() - inicio < 10


def test_el_limite_de_tiempo_se_sigue_aplicando(carpeta, monkeypatch):
    monkeypatch.setattr(ejecutor, "ALGORITMO_TIMEOUT", 1)

    resultado = ejecutor._ejecutar_local(
        _script_lento(carpeta), os.path.join(carpeta, "salida.json"))

    assert not resultado["exito"]
    assert "límite de 1s" in resultado["error"]


def test_un_algoritmo_que_falla_devuelve_su_stderr(carpeta):
    ruta = os.path.join(carpeta, "roto.py")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("import sys\nsys.exit('fallo a proposito')\n")

    resultado = ejecutor._ejecutar_local(ruta, os.path.join(carpeta, "salida.json"))

    assert not resultado["exito"]
    assert "fallo a proposito" in resultado["error"]


def test_un_lote_cancelado_no_lanza_lo_que_queda(monkeypatch):
    monkeypatch.setattr(ejecutor, "EXECUTION_MODE", "local")
    monkeypatch.setattr(ejecutor, "_ejecutar_local",
                        lambda *a, **k: pytest.fail("no deberia ejecutarse nada"))

    with ejecutor.vigilar_cancelacion(lambda: True):
        resultados = ejecutor.ejecutar_algoritmos_en_lote(
            [("algo.py", ["a.sdf", "a.json"], []), ("algo.py", ["b.sdf", "b.json"], [])])

    assert [r["exito"] for r in resultados] == [False, False]
