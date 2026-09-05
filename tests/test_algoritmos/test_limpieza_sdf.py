"""Tests unitarios de algoritmos/limpiezaSDF.py."""
from rdkit import Chem


def test_descarta_solo_la_entrada_no_saneable(ejecutar_script, sdf_biblioteca_mixta, tmp_path):
    salida = tmp_path / "biblioteca_limpia.sdf"
    resultado = ejecutar_script("limpiezaSDF", str(sdf_biblioteca_mixta), str(salida))
    assert resultado.returncode == 0, resultado.stderr

    assert "Moléculas leídas: 3" in resultado.stdout
    assert "Moléculas escritas: 2" in resultado.stdout
    assert "Descartadas por RDKit" in resultado.stdout

    supplier = Chem.SDMolSupplier(str(salida))
    mols = [m for m in supplier if m is not None]
    assert len(mols) == 2


def test_biblioteca_totalmente_valida_no_descarta_nada(ejecutar_script, aspirina_sdf, tmp_path):
    salida = tmp_path / "aspirina_limpia.sdf"
    resultado = ejecutar_script("limpiezaSDF", str(aspirina_sdf), str(salida))
    assert resultado.returncode == 0, resultado.stderr
    assert "Moléculas leídas: 1" in resultado.stdout
    assert "Moléculas escritas: 1" in resultado.stdout
    assert "Descartadas" not in resultado.stdout
