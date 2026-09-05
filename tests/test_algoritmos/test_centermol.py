"""Tests unitarios de algoritmos/centerMol.py (alineacion por PCA geometrico)."""
import os

from rdkit import Chem


def test_centra_la_molecula_en_el_origen(ejecutar_script, aspirina_mol2):
    resultado = ejecutar_script("centerMol", str(aspirina_mol2))
    assert resultado.returncode == 0, resultado.stderr

    ruta_salida = str(aspirina_mol2).replace(".mol2", "_aligned.mol2")
    assert os.path.exists(ruta_salida)

    mol = Chem.MolFromMol2File(ruta_salida, removeHs=False)
    assert mol is not None
    conf = mol.GetConformer()
    n = mol.GetNumAtoms()
    centroide = [sum(conf.GetAtomPosition(i)[eje] for i in range(n)) / n for eje in range(3)]
    assert all(abs(c) < 1e-2 for c in centroide), f"Centroide fuera del origen: {centroide}"


def test_fichero_inexistente_no_revienta_sin_traza(ejecutar_script, tmp_path):
    resultado = ejecutar_script("centerMol", str(tmp_path / "no_existe.mol2"))
    # centerMol.py captura ValueError por fichero y sigue con el resto del argv;
    # con un unico fichero invalido no genera salida, pero tampoco debe
    # lanzar una excepcion no controlada (traceback) al proceso.
    assert "Traceback" not in resultado.stderr
