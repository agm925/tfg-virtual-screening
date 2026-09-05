"""Tests unitarios de algoritmos/rmsdConformaciones.py."""
import json


def test_rmsd_de_la_misma_pose_es_practicamente_cero(ejecutar_script, aspirina_sdf):
    salida = str(aspirina_sdf).replace(".sdf", "_rmsd_self.json")
    resultado = ejecutar_script("rmsdConformaciones", str(aspirina_sdf), str(aspirina_sdf), salida)
    assert resultado.returncode == 0, resultado.stderr

    with open(salida) as f:
        datos = json.load(f)
    assert datos["exito"] is True
    assert datos["rmsd_angstroms"] < 0.01
    assert datos["criterio_redocking_superado"] is True


def test_moleculas_distintas_lanza_error_controlado(ejecutar_script, aspirina_sdf, cafeina_sdf):
    # GetBestRMS exige que ambas moleculas sean la misma estructura con
    # distinta conformacion; aspirina vs cafeina deben fallar de forma
    # controlada (JSON de error), no con un traceback sin capturar.
    salida = str(aspirina_sdf).replace(".sdf", "_rmsd_cruzado.json")
    resultado = ejecutar_script("rmsdConformaciones", str(aspirina_sdf), str(cafeina_sdf), salida)
    assert resultado.returncode == 1
    assert "Traceback" not in resultado.stderr

    with open(salida) as f:
        datos = json.load(f)
    assert datos["exito"] is False
