"""Tests unitarios de algoritmos/filtroObabel.py (filtro --filter de Open Babel)."""
import os

import pytest


@pytest.fixture(autouse=True)
def _requiere_obabel(obabel_disponible):
    if not obabel_disponible:
        pytest.skip("Open Babel no esta disponible en este entorno")


def test_molecula_que_cumple_el_filtro_se_conserva(ejecutar_script, aspirina_mol2):
    salida = str(aspirina_mol2).replace(".mol2", "_filtrado_pasa.mol2")
    resultado = ejecutar_script("filtroObabel", str(aspirina_mol2), salida, "MW>100")
    assert resultado.returncode == 0, resultado.stderr
    assert os.path.exists(salida)
    assert os.path.getsize(salida) > 0


def test_molecula_que_no_cumple_el_filtro_genera_salida_vacia(ejecutar_script, aspirina_mol2):
    salida = str(aspirina_mol2).replace(".mol2", "_filtrado_no_pasa.mol2")
    resultado = ejecutar_script("filtroObabel", str(aspirina_mol2), salida, "MW>10000")
    assert resultado.returncode == 0, resultado.stderr
    assert os.path.exists(salida)
    assert os.path.getsize(salida) == 0
    assert "Ninguna molécula cumple" in resultado.stdout
