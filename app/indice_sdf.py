"""
Indice de posiciones de los registros de un SDF.

Guarda, para cada registro, en que byte empieza. Con eso, sacar las moleculas
de un bloque es saltar a su posicion y leer, en vez de recorrer el fichero
desde el principio con RDKit hasta encontrarlas.

Por que hace falta: el cribado reparte la biblioteca en bloques, y cada bloque
tiene que sacar sus moleculas del SDF. Recorriendolo, el bloque k lee todo lo
que hay antes de el, asi que el coste total crece con el cuadrado del tamano:
con una biblioteca de un millon en bloques de mil son del orden de quinientos
millones de registros leidos para cribar un millon. Con el indice cada bloque
lee solo lo suyo.

Se construye al subir la biblioteca --en ese momento el fichero ya se esta
leyendo entero para contar sus moleculas-- y, para las que se subieron antes
de que existiera, la primera vez que se usan. Vive en uploads/.indices/, fuera
de lo que se lista y se sirve.

NUMERACION. Un registro es lo que hay entre dos lineas "$$$$", y el indice los
numera en ese orden. Es a proposito la misma numeracion para todo el camino
del cribado --el inventario, la extraccion por bloques y el trozo que va al
cluster--, porque la que da RDKit al iterar no es fiable: ante un registro
corrupto se salta separadores y a partir de ahi los numeros ya no se
corresponden con las posiciones del fichero. Mezclar las dos numeraciones
mandaria al cluster moleculas que no son las del bloque.
"""
import json
import os
import sys
from array import array

SEPARADOR = b"$$$$"
VERSION = 1
_BUFFER = 1 << 20


def ruta_indice(ruta_sdf: str) -> str:
    return os.path.join(os.path.dirname(ruta_sdf) or ".", ".indices",
                        os.path.basename(ruta_sdf) + ".idx")


def construir(ruta_sdf: str) -> array:
    """
    Los limites de cada registro: el byte donde empieza cada uno y, al final,
    el tamano del fichero. El registro i ocupa [limites[i], limites[i + 1]).

    Un ultimo registro sin su "$$$$" cuenta si tiene contenido, igual que lo
    lee RDKit: los molfiles de ChEMBL, por ejemplo, llegan sin separador. Lo
    que haya en blanco tras el ultimo separador no es un registro.
    """
    inicios = array("Q")
    posicion = 0
    inicio_actual = 0
    con_contenido = False

    with open(ruta_sdf, "rb", buffering=_BUFFER) as f:
        for linea in f:
            if linea.rstrip() == SEPARADOR:
                inicios.append(inicio_actual)
                posicion += len(linea)
                inicio_actual = posicion
                con_contenido = False
                continue
            if linea.strip():
                con_contenido = True
            posicion += len(linea)

    if con_contenido:
        inicios.append(inicio_actual)
    inicios.append(posicion)
    return inicios


def _cabecera(ruta_sdf: str, registros: int) -> dict:
    estado = os.stat(ruta_sdf)
    return {
        "version":   VERSION,
        "tamano":    estado.st_size,
        "mtime_ns":  estado.st_mtime_ns,
        "orden":     sys.byteorder,
        "registros": registros,
    }


def guardar(ruta_sdf: str, limites: array) -> None:
    ruta = ruta_indice(ruta_sdf)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)

    # Se escribe aparte y se renombra: varios bloques pueden estar
    # construyendolo a la vez la primera vez que se usa la biblioteca, y el
    # renombrado atomico evita que uno lea el que otro esta a medio escribir.
    temporal = "{}.{}.tmp".format(ruta, os.getpid())
    with open(temporal, "wb") as f:
        f.write((json.dumps(_cabecera(ruta_sdf, len(limites) - 1)) + "\n").encode("utf-8"))
        limites.tofile(f)
    os.replace(temporal, ruta)


def cargar(ruta_sdf: str):
    """
    Los limites guardados, o None si no hay indice o ya no corresponde al
    fichero. Se da por caducado si el SDF ha cambiado de tamano o de fecha: un
    indice de otro fichero no falla, simplemente lee moleculas equivocadas.
    """
    try:
        with open(ruta_indice(ruta_sdf), "rb") as f:
            guardada = json.loads(f.readline())
            actual = _cabecera(ruta_sdf, guardada.get("registros"))
            if guardada != actual:
                return None
            limites = array("Q")
            limites.fromfile(f, guardada["registros"] + 1)
            return limites
    except (OSError, ValueError, EOFError, KeyError, TypeError):
        return None


def obtener(ruta_sdf: str) -> array:
    """El indice del fichero, construyendolo si no existe o esta caducado."""
    limites = cargar(ruta_sdf)
    if limites is None:
        limites = construir(ruta_sdf)
        guardar(ruta_sdf, limites)
    return limites


def borrar(ruta_sdf: str) -> None:
    try:
        os.remove(ruta_indice(ruta_sdf))
    except OSError:
        pass


def leer_registro(fichero, limites: array, i: int) -> bytes:
    """Los bytes del registro i, tal cual estan en el fichero."""
    fichero.seek(limites[i])
    return fichero.read(limites[i + 1] - limites[i])


def titulo(registro: bytes) -> str:
    """
    La primera linea del registro: su nombre. Es lo mismo que RDKit guarda como
    _Name, y puede estar en blanco.
    """
    return registro.split(b"\n", 1)[0].decode("utf-8", errors="replace").strip()


def con_titulo(registro: bytes, nuevo: str) -> bytes:
    """El registro con otra primera linea, respetando su fin de linea."""
    primera, _, resto = registro.partition(b"\n")
    fin = b"\r" if primera.endswith(b"\r") else b""
    return nuevo.encode("utf-8") + fin + b"\n" + resto


def terminado(registro: bytes) -> bytes:
    """
    El registro con su "$$$$" al final. El ultimo de un fichero puede no
    traerlo, y al concatenar registros sin separador RDKit leeria varios
    como uno solo roto.
    """
    if registro.rstrip().endswith(SEPARADOR):
        return registro if registro.endswith(b"\n") else registro + b"\n"
    if registro and not registro.endswith(b"\n"):
        registro += b"\n"
    return registro + SEPARADOR + b"\n"
