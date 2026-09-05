"""
Fixtures compartidas para toda la suite de tests.

IMPORTANTE: DATABASE_URL se fija a un fichero SQLite de test *antes* de
importar cualquier modulo de app/, porque app/config.py lee la variable de
entorno en el momento de la importacion (no es perezoso). Asi los tests no
tocan la base de datos PostgreSQL real de docker-compose ni la base de
datos de desarrollo local.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TEST_DB_PATH = ROOT / "tests" / "_test_tfg.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402

# Se importan DESPUES de fijar DATABASE_URL para que app/config.py lea la
# variable de entorno correcta.
from app.database import engine, SessionLocal  # noqa: E402
from app import models  # noqa: E402

ALGORITMOS_DIR = ROOT / "algoritmos"

# Bloque SDF con valencia imposible (N con 4 enlaces simples, sin carga),
# verificado contra RDKit: MolFromMolBlock(..., sanitize=True) devuelve
# None para este bloque. Sirve para probar limpiezaSDF.py y las bibliotecas
# con entradas invalidas, reproduciendo el mismo tipo de fallo
# ("Explicit valence...") observado con moleculas reales de ChEMBL en el
# benchmark (Seccion de evaluacion de rendimiento de la memoria).
MOLBLOCK_INVALIDO = """molecula_rota
     RDKit          2D

  5  4  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0
    1.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    2.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000    1.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000   -1.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  1  3  1  0
  1  4  1  0
  1  5  1  0
M  END
"""


@pytest.fixture()
def db_session():
    """
    Sesion SQLAlchemy directa sobre la BD de test, para que los tests de la
    API puedan inspeccionar o preparar datos (p. ej. leer el token de
    verificacion generado por POST /registro) sin pasar por un endpoint.
    Independiente de la sesion que abre cada endpoint via get_db().
    """
    sesion = SessionLocal()
    try:
        yield sesion
    finally:
        sesion.close()


@pytest.fixture(scope="session", autouse=True)
def _base_datos_de_test():
    """
    Crea las tablas en la BD SQLite de test antes de la sesion y la borra
    al terminar.

    engine.dispose() se llama ANTES de borrar el fichero porque
    app/main.py ya ejecuta create_all(bind=engine) al importarse (linea 25),
    y ese import ocurre durante la fase de "collection" de pytest --antes
    de que este fixture se ejecute-- en cuanto algun test_api/conftest.py
    hace `from app.main import app`. Sin el dispose(), el pool de SQLAlchemy
    conserva una conexion abierta sobre el fichero que estamos a punto de
    borrar, y las conexiones nuevas que abre esa misma engine despues
    quedan en un estado inconsistente (fallaba con
    "attempt to write a readonly database" en los tests de la API).
    """
    engine.dispose()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    models.Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


@pytest.fixture(scope="session")
def ejecutar_script():
    """
    Fixture-factoria: devuelve una funcion que invoca un algoritmo del
    catalogo exactamente como lo hace app/ejecutor.py::_ejecutar_local --
    mismo interprete, argumentos posicionales, sin shell -- para que los
    tests validen el mismo camino que recorre una peticion real.
    """
    def _ejecutar(nombre_script: str, *args) -> subprocess.CompletedProcess:
        ruta = ALGORITMOS_DIR / f"{nombre_script}.py"
        return subprocess.run(
            [sys.executable, str(ruta), *[str(a) for a in args]],
            capture_output=True, text=True,
        )
    return _ejecutar


@pytest.fixture(scope="session")
def importar_algoritmo():
    """
    Fixture-factoria: devuelve una funcion que importa un script de
    algoritmos/ como modulo Python, para poder probar directamente sus
    funciones puras (p. ej. el parseo del log de Smina) sin pasar por
    subprocess. algoritmos/ no es un paquete (los scripts se invocan
    siempre por CLI, nunca se importan desde el resto de la app), asi que
    se carga por ruta con importlib en lugar de un import normal.
    """
    def _importar(nombre_script: str):
        ruta = ALGORITMOS_DIR / f"{nombre_script}.py"
        spec = importlib.util.spec_from_file_location(nombre_script, ruta)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo
    return _importar


@pytest.fixture(scope="session")
def obabel_disponible() -> bool:
    return shutil.which("obabel") is not None


@pytest.fixture(scope="session")
def smina_disponible() -> bool:
    return shutil.which("smina") is not None


def _generar_sdf_3d(ruta: Path, moleculas: dict) -> None:
    """moleculas: {nombre: smiles}. Escribe un SDF con coordenadas 3D reales
    (ETKDGv3 + MMFF94s), el mismo motor que usa gen3dRDKit.py."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    writer = Chem.SDWriter(str(ruta))
    for nombre, smiles in moleculas.items():
        mol = Chem.MolFromSmiles(smiles)
        mol = Chem.AddHs(mol)
        params = AllChem.ETKDGv3()
        params.randomSeed = 42
        AllChem.EmbedMolecule(mol, params)
        AllChem.MMFFOptimizeMolecule(mol, mmffVariant="MMFF94s")
        mol.SetProp("_Name", nombre)
        writer.write(mol)
    writer.close()


@pytest.fixture(scope="session")
def aspirina_sdf(tmp_path_factory) -> Path:
    """Acido acetilsalicilico con coordenadas 3D reales, generado con RDKit."""
    ruta = tmp_path_factory.mktemp("moleculas") / "aspirina.sdf"
    _generar_sdf_3d(ruta, {"aspirina_test": "CC(=O)OC1=CC=CC=C1C(=O)O"})
    return ruta


@pytest.fixture(scope="session")
def cafeina_sdf(tmp_path_factory) -> Path:
    """Cafeina con coordenadas 3D reales -- comparte el anillo de purina con
    otras xantinas, util como segunda molecula 'distinta' en tests de
    comparacion/similitud."""
    ruta = tmp_path_factory.mktemp("moleculas") / "cafeina.sdf"
    _generar_sdf_3d(ruta, {"cafeina_test": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"})
    return ruta


@pytest.fixture(scope="session")
def aspirina_mol2(aspirina_sdf, obabel_disponible) -> Path:
    """Convierte la aspirina de prueba a .mol2 con Open Babel."""
    if not obabel_disponible:
        pytest.skip("Open Babel no esta disponible en este entorno")
    ruta = aspirina_sdf.with_suffix(".mol2")
    resultado = subprocess.run(
        ["obabel", "-isdf", str(aspirina_sdf), "-omol2", "-O", str(ruta)],
        capture_output=True, text=True,
    )
    if not ruta.exists():
        pytest.fail(f"obabel no genero el .mol2 de prueba: {resultado.stderr}")
    return ruta


@pytest.fixture(scope="session")
def sdf_biblioteca_mixta(tmp_path_factory) -> Path:
    """
    SDF con dos moleculas validas (aspirina, cafeina) y un bloque con
    valencia imposible que RDKit no puede sanear (MOLBLOCK_INVALIDO,
    verificado por separado). Sirve para probar limpiezaSDF.py y el filtro
    de Lipinski sobre una biblioteca de varias entradas, incluida una que
    debe descartarse.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    ruta = tmp_path_factory.mktemp("bibliotecas") / "biblioteca_mixta.sdf"
    writer = Chem.SDWriter(str(ruta))
    for nombre, smiles in {
        "aspirina": "CC(=O)OC1=CC=CC=C1C(=O)O",
        "cafeina": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
    }.items():
        mol = Chem.MolFromSmiles(smiles)
        mol = Chem.AddHs(mol)
        params = AllChem.ETKDGv3()
        params.randomSeed = 42
        AllChem.EmbedMolecule(mol, params)
        mol.SetProp("_Name", nombre)
        writer.write(mol)
    writer.close()

    with open(ruta, "a", encoding="utf-8") as f:
        f.write(MOLBLOCK_INVALIDO)
        f.write("$$$$\n")

    return ruta
