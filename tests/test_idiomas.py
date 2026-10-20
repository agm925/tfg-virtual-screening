"""
Spec 014, R7: los errores de la API en el idioma de la interfaz.

El frontend manda `Accept-Language: en` cuando la interfaz está en inglés, y
un único manejador de HTTPException traduce el `detail` con el catálogo de
app/idiomas.py. Lo que más fácil se rompe es que alguien añada un mensaje
nuevo y no lo ponga en el catálogo: la prueba de cobertura recorre el código
con `ast` y falla con la lista de los que faltan.
"""
import ast
import os

import pytest

from app import idiomas
from app.idiomas import traducir, idioma_de

RAIZ_APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")


# ---------------------------------------------------------------------------
# traducir() e idioma_de()
# ---------------------------------------------------------------------------

def test_un_texto_fijo_se_traduce():
    assert traducir("Credenciales incorrectas", "en") == "Incorrect credentials"


def test_en_espanol_no_cambia_nada():
    assert traducir("Credenciales incorrectas", "es") == "Credenciales incorrectas"


def test_los_huecos_se_conservan():
    assert (traducir("Rol no válido. Debe ser uno de: admin, biologo.", "en")
            == "Invalid role. It must be one of: admin, biologo.")


def test_un_mensaje_compuesto_se_traduce_por_partes():
    texto = ("Con las opciones --all marcadas: El algoritmo devolvió un resultado de "
             "error sobre las moléculas de referencia.")
    assert traducir(texto, "en") == (
        "With the options --all ticked: The algorithm returned an error result on the "
        "reference molecules.")


def test_un_texto_desconocido_se_deja_tal_cual():
    assert traducir("Algo que nadie ha traducido", "en") == "Algo que nadie ha traducido"
    assert traducir("", "en") == ""
    assert traducir(None, "en") is None


@pytest.mark.parametrize("cabecera, esperado", [
    ("en", "en"), ("en-GB,en;q=0.9", "en"), ("EN-us", "en"),
    ("es", "es"), ("es-ES,es;q=0.9,en;q=0.8", "es"), ("fr", "es"), ("", "es"), (None, "es"),
])
def test_idioma_de_la_cabecera(cabecera, esperado):
    assert idioma_de(cabecera) == esperado


# ---------------------------------------------------------------------------
# Cobertura: todo mensaje que llega al usuario tiene su plantilla
# ---------------------------------------------------------------------------

def _texto_de(nodo):
    """El texto de una constante o f-string, con los huecos como «X»; None si no lo es."""
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return nodo.value
    if isinstance(nodo, ast.JoinedStr):
        partes = []
        for valor in nodo.values:
            if isinstance(valor, ast.Constant):
                partes.append(valor.value)
            else:
                partes.append("X")
        return "".join(partes)
    return None


def _mensajes():
    """(fichero, línea, texto) de cada mensaje que puede llegar a la interfaz."""
    encontrados = []

    def anotar(fichero, nodo, valor):
        texto = _texto_de(valor)
        if texto and texto.strip():
            encontrados.append((fichero, nodo.lineno, texto))

    for fichero in ("main.py", "auth.py", "rate_limit.py", "banco_servidor.py",
                    "permisos.py", "banco_pruebas.py", "visor.py"):
        with open(os.path.join(RAIZ_APP, fichero), encoding="utf-8") as f:
            arbol = ast.parse(f.read())
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Call):
                nombre = getattr(nodo.func, "id", getattr(nodo.func, "attr", ""))
                if nombre == "HTTPException":
                    for kw in nodo.keywords:
                        if kw.arg != "detail":
                            continue
                        if isinstance(kw.value, ast.Dict):
                            for clave, valor in zip(kw.value.keys, kw.value.values):
                                if getattr(clave, "value", None) in ("mensaje", "ayuda"):
                                    anotar(fichero, nodo, valor)
                        else:
                            anotar(fichero, nodo, kw.value)
                elif nombre == "AccesoDenegado" and nodo.args:
                    anotar(fichero, nodo, nodo.args[0])
                elif nombre == "ValueError" and fichero == "banco_pruebas.py" and nodo.args:
                    anotar(fichero, nodo, nodo.args[0])
            elif isinstance(nodo, ast.Assign) and len(nodo.targets) == 1:
                destino = nodo.targets[0]
                if fichero == "banco_pruebas.py" and getattr(destino, "attr", "") == "motivo":
                    anotar(fichero, nodo, nodo.value)
                elif fichero in ("visor.py", "main.py") and (
                        getattr(destino, "id", "").startswith(("MOTIVO_", "NO_DISPONIBLE"))):
                    anotar(fichero, nodo, nodo.value)
    return encontrados


def test_hay_mensajes_que_revisar():
    # Si el recorrido dejara de encontrarlos, la prueba siguiente pasaría sin mirar nada.
    assert len(_mensajes()) > 80


def test_cada_mensaje_tiene_su_plantilla_en_ingles():
    faltan = [f"{fichero}:{linea}: {texto}" for fichero, linea, texto in _mensajes()
              if idiomas.plantilla_de(texto) is None]
    assert not faltan, "Mensajes sin traducción en app/idiomas.py:\n" + "\n".join(faltan)


def test_el_catalogo_no_tiene_plantillas_repetidas_ni_huecos_distintos():
    vistos = set()
    for es, en in idiomas.CATALOGO:
        assert es not in vistos, es
        vistos.add(es)
        assert idiomas.huecos(es) == idiomas.huecos(en), es


# ---------------------------------------------------------------------------
# Errores de ejecución que cita el tutorial (spec 014, revisión del 20/10)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("es, en", [
    ("Error en nodo UPLOAD upload_1: Nodo upload_1: no se ha subido ninguna molécula",
     "Error in node UPLOAD upload_1: Node upload_1: no molecule has been uploaded"),
    ("Error en nodo PREPROCESADO preprocesado_2: Nodo preprocesado_2: sin entrada de molécula",
     "Error in node PREPROCESADO preprocesado_2: Node preprocesado_2: no molecule input"),
    ("Error en nodo COMPARACION comparacion_3: Nodo comparacion_3: faltan las dos moléculas de entrada",
     "Error in node COMPARACION comparacion_3: Node comparacion_3: both input molecules are missing"),
    ("Error en nodo DOCKING docking_4: Nodo docking_4: se necesitan ligando y receptor",
     "Error in node DOCKING docking_4: Node docking_4: a ligand and a receptor are needed"),
    ("Error en nodo SELECTMOL selectMol_5: Elegir molécula: no se ha elegido ninguna molécula. "
     "Abre el nodo y elige una de la lista.",
     "Error in node SELECTMOL selectMol_5: Choose molecule: no molecule has been chosen. "
     "Open the node and choose one from the list."),
    ("El nodo «Elegir biblioteca» no tiene ninguna biblioteca elegida.",
     "The «Choose library» node has no library chosen."),
    ("Nodo selectDB_1: no se ha elegido ninguna biblioteca", "Node selectDB_1: no library has been chosen"),
])
def test_los_errores_de_ejecucion_que_cita_el_tutorial(es, en):
    assert traducir(es, "en") == en
