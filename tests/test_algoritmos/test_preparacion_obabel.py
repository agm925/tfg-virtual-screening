"""Tests unitarios de algoritmos/preparacionObabel.py."""
import os

import pytest
from rdkit import Chem


@pytest.fixture(autouse=True)
def _requiere_obabel(obabel_disponible):
    if not obabel_disponible:
        pytest.skip("Open Babel no esta disponible en este entorno")


def test_preparacion_completa_anade_hidrogenos_explicitos(ejecutar_script, aspirina_mol2):
    salida = str(aspirina_mol2).replace(".mol2", "_preparada.mol2")
    resultado = ejecutar_script("preparacionObabel", str(aspirina_mol2), salida)
    assert resultado.returncode == 0, resultado.stderr
    assert os.path.exists(salida)

    original = Chem.MolFromMol2File(str(aspirina_mol2), removeHs=False)
    preparada = Chem.MolFromMol2File(salida, removeHs=False)
    assert preparada is not None
    # La entrada ya tiene H explicitos (se genero con Chem.AddHs), asi que
    # el numero de atomos no deberia disminuir tras -h --gen3d --center.
    assert preparada.GetNumAtoms() >= original.GetNumAtoms()


def test_conversion_pura_sin_flags_no_falla(ejecutar_script, aspirina_mol2):
    salida = str(aspirina_mol2).replace(".mol2", "_convertida.sdf")
    resultado = ejecutar_script(
        "preparacionObabel", str(aspirina_mol2), salida, "--sin-h", "--sin-3d", "--sin-center"
    )
    assert resultado.returncode == 0, resultado.stderr
    assert os.path.exists(salida)
