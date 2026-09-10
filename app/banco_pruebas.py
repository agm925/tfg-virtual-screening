"""
Banco de pruebas para algoritmos subidos al catálogo.

Antes de este módulo, subir un algoritmo era un acto de fe: el metadato
`# TIPO_ALGORITMO` lo declaraba el propio autor y no se comprobaba contra
nada, y nadie verificaba que el script llegara siquiera a ejecutarse. Un
algoritmo roto entraba en el catálogo igual que uno correcto, y el fallo
aparecía horas después, dentro de un cribado, como una molécula fallida entre
mil.

La idea es sencilla: el autor DECLARA qué hace su algoritmo, y la plataforma
lo VERIFICA ejecutándolo contra un par de moléculas de referencia antes de
aceptarlo. El tipo declarado es lo que permite saber cómo invocarlo --una
molécula, dos, o ligando más receptor-- y la ejecución comprueba que esa
declaración sea cierta.

Además de aceptar o rechazar, la prueba OBSERVA el resultado y anota dos cosas
que hasta ahora estaban cableadas en el código del motor:

  · el formato de salida (molécula o JSON), que evita que el resultado de un
    algoritmo de métricas acabe en un fichero con extensión de molécula;
  · la clave del JSON que contiene la puntuación, que es lo que el cribado por
    lotes necesita para ordenar el ranking.

Esa segunda anotación elimina de raíz una familia de fallos que se ha repetido
cuatro veces en este proyecto: el motor buscaba `rmsd` y el algoritmo escribía
`rmsd_angstroms`; buscaba `MW` en la raíz y estaba anidado; no contemplaba que
`mejor_afinidad` pudiera ser nulo. Todos eran el mismo problema: un contrato
acordado de palabra entre dos ficheros que nadie comprobaba.
"""
import json
import os
import subprocess
import sys
import tempfile

from app.config import ALGORITMO_TIMEOUT
from app.formatos import EXTENSIONES_MOLECULA, parece_json

# Directorio con las moléculas de referencia, en la raíz del proyecto.
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFERENCIA = os.path.join(RAIZ, "referencia")

LIGANDO_A = os.path.join(REFERENCIA, "ligando_a.sdf")
LIGANDO_B = os.path.join(REFERENCIA, "ligando_b.sdf")
RECEPTOR = os.path.join(REFERENCIA, "receptor.pdbqt")

# Tiempo máximo de la prueba. Mucho más corto que ALGORITMO_TIMEOUT porque
# aquí el usuario está esperando delante del formulario: un algoritmo que
# tarda minutos sobre una molécula pequeña ya es sospechoso de por sí.
TIMEOUT_PRUEBA = int(os.getenv("BANCO_TIMEOUT", "120"))

# Cómo se invoca cada tipo de algoritmo. La entrada la marca el tipo que
# declara el autor; la salida siempre va en último lugar, que es la convención
# del catálogo (ver el apéndice de la memoria sobre añadir algoritmos).
INVOCACIONES = {
    "preprocesado": [LIGANDO_A],
    "alineacion":   [LIGANDO_A],
    "comparacion":  [LIGANDO_A, LIGANDO_B],
    "docking":      [LIGANDO_A, RECEPTOR],
}

# Extensión con la que se le pide la salida en la prueba. Se acepta que el
# algoritmo escriba otra cosa --se detecta después-- pero hay que darle una.
EXTENSION_PRUEBA = {
    "preprocesado": ".sdf",
    "alineacion":   ".sdf",
    "comparacion":  ".json",
    "docking":      ".sdf",
}


class ResultadoPrueba:
    """Lo que el banco de pruebas averigua sobre un algoritmo."""

    def __init__(self):
        self.valido = False
        self.motivo = None          # por qué se rechaza, en lenguaje llano
        self.detalle = None         # stderr o traza, para el que sepa leerla
        self.formato_salida = None  # "molecula" | "json"
        self.clave_score = None     # clave del JSON con la puntuación
        self.claves_json = []       # todas las claves numéricas encontradas
        self.log = ""

    def como_dict(self):
        return {
            "valido": self.valido,
            "motivo": self.motivo,
            "detalle": self.detalle,
            "formato_salida": self.formato_salida,
            "clave_score": self.clave_score,
            "claves_json": self.claves_json,
        }


def _claves_numericas(datos, prefijo=""):
    """
    Recorre un JSON y devuelve las rutas de sus valores numéricos.

    Entra un nivel en las listas de objetos porque varios algoritmos del
    catálogo envuelven sus resultados así --filtroLipinski devuelve
    {"moleculas": [{"MW": ...}]}-- y la puntuación vive dentro.
    """
    encontradas = []
    if isinstance(datos, dict):
        for clave, valor in datos.items():
            ruta = f"{prefijo}{clave}"
            if isinstance(valor, bool):
                continue          # "exito": true no es una puntuación
            if isinstance(valor, (int, float)):
                encontradas.append(ruta)
            elif isinstance(valor, (dict, list)) and prefijo.count(".") < 2:
                encontradas.extend(_claves_numericas(valor, ruta + "."))
    elif isinstance(datos, list) and datos:
        encontradas.extend(_claves_numericas(datos[0], prefijo))
    return encontradas


# Claves que, si aparecen, son con casi total seguridad LA puntuación. El
# orden importa: se elige la primera que exista.
_PREFERIDAS = (
    "similitud", "similarity", "tanimoto",
    "rmsd_angstroms", "rmsd",
    "mejor_afinidad", "afinidad", "score", "puntuacion",
    "mw", "peso_molecular",
)


def elegir_clave_score(claves):
    """De todas las claves numéricas, cuál parece ser la puntuación."""
    if not claves:
        return None
    minusculas = {c.lower(): c for c in claves}
    for preferida in _PREFERIDAS:
        for clave_min, original in minusculas.items():
            # Coincide la clave completa o el último tramo de la ruta.
            if clave_min == preferida or clave_min.split(".")[-1] == preferida:
                return original
    # Ninguna reconocida: se queda la primera, que el autor podrá corregir.
    return claves[0]


def probar_algoritmo(ruta_script: str, tipo: str) -> ResultadoPrueba:
    """
    Ejecuta un algoritmo contra las moléculas de referencia y comprueba que
    hace lo que su autor declara.

    No lanza excepciones: devuelve siempre un ResultadoPrueba, para que quien
    lo llame pueda dar al usuario un mensaje claro.
    """
    resultado = ResultadoPrueba()

    tipo = (tipo or "").lower()
    if tipo not in INVOCACIONES:
        resultado.motivo = f"Tipo de algoritmo desconocido: '{tipo}'."
        return resultado

    for referencia in INVOCACIONES[tipo]:
        if not os.path.exists(referencia):
            resultado.motivo = (
                "Faltan las moléculas de referencia del banco de pruebas "
                f"({os.path.basename(referencia)}). Es un problema de la "
                "instalación, no de tu algoritmo."
            )
            return resultado

    with tempfile.TemporaryDirectory(prefix="banco_") as tmp:
        salida = os.path.join(tmp, "salida" + EXTENSION_PRUEBA[tipo])
        argumentos = list(INVOCACIONES[tipo]) + [salida]

        try:
            proceso = subprocess.run(
                [sys.executable, ruta_script, *argumentos],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                timeout=TIMEOUT_PRUEBA,
            )
        except subprocess.TimeoutExpired:
            resultado.motivo = (
                f"El algoritmo no terminó en {TIMEOUT_PRUEBA} segundos sobre una "
                "molécula pequeña de referencia. Revisa si entra en un bucle "
                "infinito o espera una entrada por teclado."
            )
            return resultado
        except OSError as e:
            resultado.motivo = f"No se pudo ejecutar el script: {e}"
            return resultado

        resultado.log = (proceso.stdout or "")[:4000]

        if proceso.returncode != 0:
            resultado.motivo = (
                "El algoritmo terminó con error al ejecutarlo sobre las "
                "moléculas de referencia."
            )
            resultado.detalle = (proceso.stderr or proceso.stdout or "")[-2000:]
            return resultado

        # ¿Escribió algo? El script puede haber corregido la extensión por su
        # cuenta, así que se busca cualquier fichero en el directorio temporal.
        producidos = [os.path.join(tmp, n) for n in os.listdir(tmp)]
        producidos = [p for p in producidos if os.path.isfile(p) and os.path.getsize(p) > 0]
        if not producidos:
            resultado.motivo = (
                "El algoritmo terminó correctamente pero no escribió ningún "
                "fichero de salida. Comprueba que usa el último argumento de "
                "la línea de comandos como ruta de salida."
            )
            return resultado

        # El principal es el que coincide con la ruta pedida; si no, el mayor.
        principal = salida if os.path.exists(salida) and os.path.getsize(salida) > 0 else None
        if principal is None:
            principal = max(producidos, key=os.path.getsize)

        if parece_json(principal):
            resultado.formato_salida = "json"
            with open(principal, "r", encoding="utf-8", errors="ignore") as f:
                datos = json.load(f)
            # Un JSON que declara su propio fallo no es una salida válida.
            if isinstance(datos, dict) and datos.get("exito") is False:
                resultado.motivo = (
                    "El algoritmo devolvió un resultado de error sobre las "
                    "moléculas de referencia."
                )
                resultado.detalle = str(datos.get("error"))[:2000]
                return resultado
            resultado.claves_json = _claves_numericas(datos)
            resultado.clave_score = elegir_clave_score(resultado.claves_json)
            if not resultado.claves_json:
                resultado.motivo = (
                    "El algoritmo devolvió un JSON sin ningún valor numérico. "
                    "El cribado por lotes necesita una puntuación para poder "
                    "ordenar el ranking."
                )
                return resultado
        elif os.path.splitext(principal)[1].lower() in EXTENSIONES_MOLECULA:
            resultado.formato_salida = "molecula"
            if not _es_molecula_valida(principal):
                resultado.motivo = (
                    "El fichero de salida tiene extensión de molécula pero no "
                    "contiene ninguna que se pueda leer."
                )
                return resultado
        else:
            resultado.formato_salida = "molecula"

        resultado.valido = True
        return resultado


def _es_molecula_valida(ruta: str) -> bool:
    """Comprueba que un fichero de molécula tenga al menos un átomo."""
    try:
        from rdkit import Chem, RDLogger

        RDLogger.DisableLog("rdApp.*")
        ext = os.path.splitext(ruta)[1].lower()
        if ext == ".mol2":
            mol = Chem.MolFromMol2File(ruta, sanitize=False)
        elif ext in (".sdf", ".mol"):
            mol = next((m for m in Chem.SDMolSupplier(ruta, sanitize=False) if m), None)
        elif ext in (".pdb", ".pdbqt"):
            mol = Chem.MolFromPDBFile(ruta, sanitize=False)
        else:
            return True   # formato que RDKit no lee; se acepta sin comprobar
        return mol is not None and mol.GetNumAtoms() > 0
    except Exception:
        return False
