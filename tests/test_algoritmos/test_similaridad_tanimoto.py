"""Tests unitarios de algoritmos/similaridadTanimoto.py."""
import json
import os


def test_similitud_de_una_molecula_consigo_misma_es_uno(ejecutar_script, aspirina_sdf):
    salida = str(aspirina_sdf).replace(".sdf", "_tanimoto_self.json")
    resultado = ejecutar_script("similaridadTanimoto", str(aspirina_sdf), str(aspirina_sdf), salida)
    assert resultado.returncode == 0, resultado.stderr

    with open(salida) as f:
        datos = json.load(f)
    assert datos["exito"] is True
    assert datos["similitud"] == 1.0


def test_similitud_entre_moleculas_distintas_es_menor_que_uno(
    ejecutar_script, aspirina_sdf, cafeina_sdf
):
    salida = str(aspirina_sdf).replace(".sdf", "_tanimoto_cruzado.json")
    resultado = ejecutar_script("similaridadTanimoto", str(aspirina_sdf), str(cafeina_sdf), salida)
    assert resultado.returncode == 0, resultado.stderr

    with open(salida) as f:
        datos = json.load(f)
    assert datos["exito"] is True
    assert 0.0 <= datos["similitud"] < 1.0


def test_argumentos_insuficientes_devuelve_error_json(ejecutar_script, aspirina_sdf):
    resultado = ejecutar_script("similaridadTanimoto", str(aspirina_sdf))
    assert resultado.returncode == 1
    salida_json = json.loads(resultado.stdout)
    assert salida_json["exito"] is False
