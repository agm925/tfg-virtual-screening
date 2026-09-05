"""Tests unitarios de algoritmos/alinear3D.py (Open3DAlign)."""
import os


def test_modo_single_input_autoalineacion(ejecutar_script, aspirina_sdf):
    salida = str(aspirina_sdf).replace(".sdf", "_o3a.sdf")
    resultado = ejecutar_script("alinear3D", str(aspirina_sdf), salida)
    assert resultado.returncode == 0, resultado.stderr
    assert os.path.exists(salida)
    assert "RMSD O3A" in resultado.stdout


def test_alineacion_con_referencia_distinta(ejecutar_script, aspirina_sdf, cafeina_sdf):
    salida = str(aspirina_sdf).replace(".sdf", "_o3a_vs_cafeina.sdf")
    resultado = ejecutar_script("alinear3D", str(aspirina_sdf), str(cafeina_sdf), salida)
    assert resultado.returncode == 0, resultado.stderr
    assert os.path.exists(salida)


def test_fichero_de_entrada_inexistente_devuelve_error_controlado(ejecutar_script, tmp_path):
    resultado = ejecutar_script(
        "alinear3D", str(tmp_path / "no_existe.sdf"), str(tmp_path / "salida.sdf")
    )
    assert resultado.returncode != 0
    assert "Error" in resultado.stderr
    assert "Traceback" not in resultado.stderr
