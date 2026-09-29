"""
Convención de formatos de salida de los algoritmos del catálogo.

Un algoritmo escribe su resultado en la ruta que se le pasa por línea de
comandos, así que quien lo invoca tiene que decidir de antemano la extensión
de esa ruta. El problema es que no todos producen lo mismo: unos devuelven una
molécula (alineación, preparación, docking) y otros un documento JSON de
métricas (Lipinski, Tanimoto, RMSD).

Esa decisión estaba tomada en cuatro sitios distintos de
app/workflow_executor.py, cada uno con su propia condición, y NO estaba tomada
en app/tasks.py, que construía el nombre de salida asumiendo siempre .mol2:

    nombre_salida = peticion.ruta_mol_original.replace(".mol2", "_resultado.mol2")

El efecto era que el resultado de una petición con filtroLipinski --un JSON--
acababa en un fichero llamado ".mol2". La biblioteca lo ofrecía como molécula,
el visor 3D lo cargaba y no mostraba nada. En el entorno de desarrollo llegaron
a acumularse 1.995 ficheros así, el 57 % de todo uploads/.

Este módulo centraliza la convención en un único sitio y añade una red de
seguridad para los algoritmos que suba el usuario, cuyo comportamiento no se
puede predecir por el nombre.
"""
import json
import os

from app.config import TAMANO_TROZO_SUBIDA

# Extensiones que la plataforma considera "una molécula".
EXTENSIONES_MOLECULA = (".mol2", ".sdf", ".mol", ".pdb", ".pdbqt", ".smi", ".xyz")

# Lo que los algoritmos del catálogo saben LEER como entrada.
#
# Es un subconjunto de EXTENSIONES_MOLECULA a propósito: la biblioteca acepta
# más formatos --un .pdbqt de receptor, por ejemplo, es una molécula válida que
# guardar-- pero `cargar_moleculas` de los scripts solo distingue .mol2, .sdf y
# .mol, y con cualquier otra cosa levanta "Formato no soportado: {ext}".
#
# Sirve para rechazar en el endpoint, con un mensaje claro, lo que de todas
# formas iba a fallar dentro del worker media hora después.
EXTENSIONES_ENTRADA_ALGORITMO = (".mol2", ".sdf", ".mol")


def contar_moleculas_sdf(ruta: str) -> int:
    """Cuenta los separadores de registro de un SDF leyendo por trozos.

    Vive aquí y no en app/main.py porque scripts/migrate.py también lo
    necesita (para el `tipo` de los ficheros .sdf ya registrados antes de que
    existiera esa columna) y no puede importar app.main sin arrastrar la
    aplicación FastAPI entera como efecto secundario de un simple import.

    Se relee el fichero en lugar de contar durante la escritura porque el
    separador ($$$$) puede quedar partido entre dos trozos; aquí se arrastra
    el solapamiento explícitamente.
    """
    separador = b"$$$$"
    total = 0
    sobrante = b""
    with open(ruta, "rb") as f:
        while True:
            trozo = f.read(TAMANO_TROZO_SUBIDA)
            if not trozo:
                break
            datos = sobrante + trozo
            total += datos.count(separador)
            # Conservar los últimos bytes por si el separador cruza la frontera.
            sobrante = datos[-(len(separador) - 1):]
    return total

# Algoritmos del catálogo base cuyo resultado principal es un JSON de métricas.
#
# dockingSmina NO está aquí a propósito: su salida principal son las poses en
# .sdf, y el JSON de energías es un fichero acompañante que el propio script
# escribe aparte, con el mismo nombre y sufijo "_energias.json".
_ALGORITMOS_JSON = {
    "filtrolipinski",
    "rmsdconformaciones",
    "similaridadtanimoto",
}

# Para algoritmos subidos por el usuario que no están en el catálogo base pero
# siguen la convención de nombres habitual.
_FRAGMENTOS_JSON = ("lipinski", "rmsd", "tanimoto", "similarid")

# Los algoritmos de alineación fuerzan .sdf internamente, aunque la entrada sea
# .mol2 (ver alinear3D.alinear_o3a y alinearMCS.alinear_mcs): anticiparlo evita
# que el motor apunte a un fichero con una extensión que nunca se escribió.
_FRAGMENTOS_SDF = ("alinear", "align", "docking", "smina")


def _base(nombre_algoritmo: str) -> str:
    """Nombre del script en minúsculas, sin ruta ni extensión."""
    base = os.path.basename(nombre_algoritmo or "")
    if base.endswith(".py"):
        base = base[:-3]
    return base.lower()


def produce_json(nombre_algoritmo: str, tipo: str = None) -> bool:
    """Si el resultado principal de este algoritmo es un documento JSON."""
    base = _base(nombre_algoritmo)
    if base in _ALGORITMOS_JSON:
        return True
    if any(f in base for f in _FRAGMENTOS_SDF):
        return False
    if any(f in base for f in _FRAGMENTOS_JSON):
        return True
    # Un algoritmo de comparación que no alinea produce una métrica, no una
    # molécula: es la convención que ya seguía el motor de flujos.
    return (tipo or "").lower() == "comparacion"


def extension_salida(nombre_algoritmo: str, tipo: str = None,
                     ext_entrada: str = None) -> str:
    """
    Extensión que debe llevar el fichero de salida de este algoritmo.

    `ext_entrada` solo se usa para los que devuelven una molécula, que
    conservan el formato de entrada cuando es uno que saben escribir.
    """
    if produce_json(nombre_algoritmo, tipo):
        return ".json"

    base = _base(nombre_algoritmo)
    if any(f in base for f in _FRAGMENTOS_SDF):
        return ".sdf"

    ext = (ext_entrada or "").lower()
    return ext if ext in (".mol2", ".sdf") else ".sdf"


def parece_json(ruta: str) -> bool:
    """Si el fichero contiene un documento JSON, mirando solo su comienzo."""
    try:
        with open(ruta, "rb") as f:
            inicio = f.read(2048).lstrip()
        if not inicio[:1] in (b"{", b"["):
            return False
        with open(ruta, "r", encoding="utf-8", errors="ignore") as f:
            json.load(f)
        return True
    except Exception:
        return False


def corregir_extension(ruta: str) -> str:
    """
    Red de seguridad: si un fichero con extensión de molécula contiene en
    realidad un JSON, lo renombra a .json y devuelve la ruta nueva.

    La convención de `extension_salida` acierta con el catálogo base, pero un
    algoritmo subido por el usuario puede producir cualquier cosa. Comprobar el
    contenido después de ejecutarlo es lo único que garantiza que un JSON no
    acabe presentándose como una molécula en la biblioteca.
    """
    if not ruta or not os.path.exists(ruta):
        return ruta
    if os.path.splitext(ruta)[1].lower() not in EXTENSIONES_MOLECULA:
        return ruta
    if not parece_json(ruta):
        return ruta

    destino = os.path.splitext(ruta)[0] + ".json"
    if os.path.exists(destino):
        os.remove(destino)
    os.replace(ruta, destino)
    return destino
