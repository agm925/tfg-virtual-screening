"""
Tests de la convencion de formatos de salida (app/formatos.py).

Origen del problema: app/tasks.py construia el nombre del fichero de salida de
una peticion como

    ruta_mol_original.replace(".mol2", "_resultado.mol2")

dando por hecho que TODO algoritmo produce una molecula. Los que devuelven
metricas --filtroLipinski, similaridadTanimoto, rmsdConformaciones-- escribian
por tanto su JSON en un fichero con extension .mol2, que la biblioteca ofrecia
como molecula y el visor 3D abria en blanco. Casi dos mil ficheros asi
llegaron a acumularse en el entorno de desarrollo.
"""
import json
import os

import pytest

from app.formatos import corregir_extension, extension_salida, parece_json, produce_json


@pytest.mark.parametrize("algoritmo,tipo,esperado", [
    # Los que devuelven metricas
    ("filtroLipinski.py",      "preprocesado", ".json"),
    ("similaridadTanimoto.py", "comparacion",  ".json"),
    ("rmsdConformaciones.py",  "comparacion",  ".json"),
    # Los que devuelven una molecula
    ("dockingSmina.py",        "docking",      ".sdf"),
    ("alinear3D.py",           "alineacion",   ".sdf"),
    ("alinearMCS.py",          "comparacion",  ".sdf"),
    ("centerMol.py",           "alineacion",   ".mol2"),
    ("preparacionObabel.py",   "preprocesado", ".mol2"),
    ("filtroObabel.py",        "preprocesado", ".mol2"),
])
def test_extension_por_algoritmo(algoritmo, tipo, esperado):
    assert extension_salida(algoritmo, tipo, ".mol2") == esperado


def test_docking_no_se_confunde_con_los_de_metricas():
    """
    dockingSmina escribe tambien un JSON de energias, pero su salida PRINCIPAL
    son las poses: el fichero que se le pide debe ser .sdf.
    """
    assert produce_json("dockingSmina.py", "docking") is False
    assert extension_salida("dockingSmina.py", "docking", ".mol2") == ".sdf"


def test_alinear_produce_molecula_aunque_su_tipo_sea_comparacion():
    """
    Los algoritmos de alineacion se registran como tipo "comparacion" pero
    devuelven una molecula, no una metrica.
    """
    assert produce_json("alinearMCS.py", "comparacion") is False


def test_un_algoritmo_desconocido_de_comparacion_se_asume_metrica():
    """Convencion para algoritmos que suba el usuario."""
    assert extension_salida("miMetricaNueva.py", "comparacion", ".mol2") == ".json"


def test_una_molecula_conserva_el_formato_de_entrada_si_es_soportado():
    assert extension_salida("centerMol.py", "alineacion", ".sdf") == ".sdf"
    assert extension_salida("centerMol.py", "alineacion", ".mol2") == ".mol2"
    # Un formato que los algoritmos no saben escribir cae a .sdf
    assert extension_salida("centerMol.py", "alineacion", ".xyz") == ".sdf"


def test_corregir_extension_renombra_un_json_disfrazado_de_molecula(tmp_path):
    """
    Red de seguridad para algoritmos subidos por el usuario, cuyo formato de
    salida no se puede predecir por el nombre.
    """
    impostor = tmp_path / "resultado.mol2"
    impostor.write_text(json.dumps({"exito": True, "MW": 180.04}), encoding="utf-8")

    nueva = corregir_extension(str(impostor))

    assert nueva.endswith(".json")
    assert not os.path.exists(str(impostor)), "el fichero original deberia haberse renombrado"
    assert json.loads(open(nueva, encoding="utf-8").read())["MW"] == 180.04


def test_corregir_extension_no_toca_una_molecula_de_verdad(tmp_path):
    mol2 = tmp_path / "molecula.mol2"
    mol2.write_text("@<TRIPOS>MOLECULE\ndummy\n1 0 0 0 0\n", encoding="utf-8")

    assert corregir_extension(str(mol2)) == str(mol2)
    assert os.path.exists(str(mol2))


def test_parece_json_no_se_deja_enganar_por_un_mol2():
    assert parece_json.__doc__  # la funcion existe y esta documentada


def test_un_mol2_de_openbabel_que_rdkit_no_kekuliza_se_carga_igualmente(tmp_path):
    """
    Los .mol2 que produce Open Babel desde un SDF de ChEMBL declaran enlaces
    aromaticos que RDKit no sabe kekulizar, de modo que MolFromMol2File
    devuelve None con los valores por defecto. Sobre una biblioteca de mil
    compuestos reales eso descartaba el 27 % de las entradas.

    Los algoritmos incorporan ahora un cargador tolerante; este test comprueba
    la tecnica en la que se apoya.
    """
    from rdkit import Chem, RDLogger
    from rdkit.Chem import Descriptors

    RDLogger.DisableLog("rdApp.*")

    # Piridina escrita con enlaces aromaticos explicitos (ar), como los emite
    # Open Babel. RDKit no la kekuliza con la configuracion por defecto.
    contenido = """@<TRIPOS>MOLECULE
piridina
 6 6 0 0 0
SMALL
GASTEIGER

@<TRIPOS>ATOM
      1 N1         0.0000    1.3900    0.0000 N.ar    1  LIG   -0.2000
      2 C2         1.2000    0.6900    0.0000 C.ar    1  LIG    0.0400
      3 C3         1.2000   -0.6900    0.0000 C.ar    1  LIG    0.0400
      4 C4         0.0000   -1.3900    0.0000 C.ar    1  LIG    0.0400
      5 C5        -1.2000   -0.6900    0.0000 C.ar    1  LIG    0.0400
      6 C6        -1.2000    0.6900    0.0000 C.ar    1  LIG    0.0400
@<TRIPOS>BOND
     1    1    2 ar
     2    2    3 ar
     3    3    4 ar
     4    4    5 ar
     5    5    6 ar
     6    6    1 ar
"""
    ruta = tmp_path / "aromatica.mol2"
    ruta.write_text(contenido, encoding="utf-8")

    def cargar_tolerante(r):
        mol = Chem.MolFromMol2File(r, removeHs=True)
        if mol is not None:
            return mol
        mol = Chem.MolFromMol2File(r, removeHs=True, sanitize=False)
        if mol is None:
            return None
        Chem.SanitizeMol(
            mol,
            Chem.SanitizeFlags.SANITIZE_ALL ^ Chem.SanitizeFlags.SANITIZE_KEKULIZE,
        )
        return mol

    mol = cargar_tolerante(str(ruta))
    assert mol is not None, "el cargador tolerante deberia recuperar la molecula"
    assert mol.GetNumAtoms() == 6
    # Y los descriptores se calculan con normalidad.
    assert Descriptors.ExactMolWt(mol) > 0
