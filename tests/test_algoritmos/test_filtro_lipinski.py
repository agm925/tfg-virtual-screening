"""Tests unitarios de algoritmos/filtroLipinski.py (Regla de los 5)."""
import json


def test_aspirina_pasa_el_filtro_de_lipinski(ejecutar_script, aspirina_sdf):
    salida = str(aspirina_sdf).replace(".sdf", "_lipinski.json")
    resultado = ejecutar_script("filtroLipinski", str(aspirina_sdf), salida)
    assert resultado.returncode == 0, resultado.stderr

    with open(salida) as f:
        datos = json.load(f)
    assert datos["exito"] is True
    assert datos["total"] == 1
    assert datos["pass"] == 1
    propiedades = datos["moleculas"][0]
    # Peso molecular real del acido acetilsalicilico: 180.16 Da
    assert 175 < propiedades["MW"] < 185
    assert propiedades["estado"] == "PASS"


def test_el_peso_molecular_es_el_promedio_no_la_masa_exacta(ejecutar_script, aspirina_sdf):
    """
    La regla de Lipinski se enuncia sobre el peso molecular PROMEDIO, que es
    tambien el que publican ChEMBL y PubChem. Antes se usaba ExactMolWt (masa
    monoisotopica), que para la aspirina da 180,04 en vez de 180,16: siempre
    por debajo, asi que en el umbral de 500 Da el filtro era mas permisivo que
    la regla. Ademas dejaba el catalogo incoherente consigo mismo, porque
    similaridadTanimoto.py ya informaba del peso promedio.
    """
    salida = str(aspirina_sdf).replace(".sdf", "_lipinski_mw.json")
    ejecutar_script("filtroLipinski", str(aspirina_sdf), salida)

    with open(salida) as f:
        mw = json.load(f)["moleculas"][0]["MW"]

    # 180,16 es el valor de ChEMBL (CHEMBL25); la masa exacta es 180,04.
    assert abs(mw - 180.16) < 0.05, f"MW={mw}: parece la masa exacta, no el promedio"


def test_biblioteca_con_entrada_invalida_procesa_solo_las_validas(
    ejecutar_script, sdf_biblioteca_mixta
):
    salida = str(sdf_biblioteca_mixta).replace(".sdf", "_lipinski.json")
    resultado = ejecutar_script("filtroLipinski", str(sdf_biblioteca_mixta), salida)
    assert resultado.returncode == 0, resultado.stderr

    with open(salida) as f:
        datos = json.load(f)
    # El SDMolSupplier salta silenciosamente la entrada con valencia
    # invalida (comportamiento documentado en cargar_moleculas): de las 3
    # entradas del fichero, solo se procesan las 2 validas.
    assert datos["total"] == 2


def test_fichero_sin_moleculas_validas_falla_con_error_json(ejecutar_script, tmp_path):
    sdf_vacio = tmp_path / "vacio.sdf"
    sdf_vacio.write_text("")
    salida = tmp_path / "salida.json"

    resultado = ejecutar_script("filtroLipinski", str(sdf_vacio), str(salida))
    assert resultado.returncode == 1

    with open(salida) as f:
        datos = json.load(f)
    assert datos["exito"] is False
