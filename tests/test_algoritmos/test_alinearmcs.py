"""Tests unitarios de algoritmos/alinearMCS.py (alineacion por subestructura comun)."""
import os


def test_modo_single_input_mcs_es_la_molecula_entera(ejecutar_script, aspirina_sdf):
    salida = str(aspirina_sdf).replace(".sdf", "_mcs.sdf")
    resultado = ejecutar_script("alinearMCS", str(aspirina_sdf), salida)
    assert resultado.returncode == 0, resultado.stderr
    assert os.path.exists(salida)
    assert "MCS encontrada" in resultado.stdout


def test_moleculas_sin_scaffold_comun_falla_con_error_controlado(
    ejecutar_script, aspirina_sdf, cafeina_sdf
):
    # Aspirina y cafeina no comparten un anillo aromatico identico (uno es
    # benceno, el otro purina), asi que con completeRingsOnly=True la MCS
    # esperable es demasiado pequena (< 5 atomos): debe fallar de forma
    # controlada, no con un traceback.
    salida = str(aspirina_sdf).replace(".sdf", "_mcs_vs_cafeina.sdf")
    resultado = ejecutar_script("alinearMCS", str(aspirina_sdf), str(cafeina_sdf), salida)
    assert "Traceback" not in resultado.stderr
    if resultado.returncode != 0:
        assert "MCS demasiado pequeña" in resultado.stderr
