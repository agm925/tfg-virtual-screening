"""Tests unitarios de algoritmos/gen3dRDKit.py (ETKDGv3 + MMFF94s)."""
from rdkit import Chem


def test_genera_coordenadas_3d_desde_smiles(ejecutar_script, tmp_path):
    entrada = tmp_path / "entrada.smi"
    entrada.write_text("CC(=O)OC1=CC=CC=C1C(=O)O aspirina\n")
    salida = tmp_path / "salida.sdf"

    resultado = ejecutar_script("gen3dRDKit", str(entrada), str(salida))
    assert resultado.returncode == 0, resultado.stderr
    assert salida.exists()

    supplier = Chem.SDMolSupplier(str(salida))
    mols = [m for m in supplier if m is not None]
    assert len(mols) == 1
    conf = mols[0].GetConformer()
    # Si la conformacion fuese plana (2D), todas las Z serian 0; con 3D real
    # al menos algun atomo debe salirse del plano.
    zetas = [conf.GetAtomPosition(i).z for i in range(mols[0].GetNumAtoms())]
    assert any(abs(z) > 0.05 for z in zetas)


def test_smiles_invalido_falla_con_error_controlado(ejecutar_script, tmp_path):
    entrada = tmp_path / "invalido.smi"
    entrada.write_text("esto_no_es_un_smiles_valido(((\n")
    salida = tmp_path / "salida.sdf"

    resultado = ejecutar_script("gen3dRDKit", str(entrada), str(salida))
    assert resultado.returncode == 1
    assert "Traceback" not in resultado.stderr
