"""
Logica del visor 3D de moleculas (spec 002, docs/specs/002-visor3D/).

Aqui esta todo lo que el visor tiene que decidir sobre un fichero --que
moleculas tiene, como se llaman, cuantos atomos, que campos, si es una
proteina, si se puede dibujar, con que nombre se descarga--, sin nada de HTTP:
app/main.py solo valida, comprueba el acceso y delega (principio 3 de la
constitucion). Por eso las funciones son puras sobre texto y bytes, y las
pocas que abren un fichero son finas y delegan en ellas.
"""
import os
import re
import unicodedata
from datetime import datetime

from app import indice_sdf

# Extension -> formato. Lo que no esta aqui no es un fichero de moleculas para
# el visor (un CSV de ranking, un JSON de resultados...).
_FORMATOS = {
    ".sdf":   "sdf",
    ".mol":   "mol",
    ".mol2":  "mol2",
    ".pdb":   "pdb",
    ".pdbqt": "pdbqt",
    ".xyz":   "xyz",
    ".smi":   "smi",
}


def normalizar(texto: str) -> str:
    """
    El texto como se compara en las busquedas: minusculas, sin tildes y con
    los espacios reducidos a uno. "Cafeína " y "cafeina" tienen que encontrarse
    (RF-3, RF-6): quien busca una molecula no recuerda si su nombre lleva
    tilde o mayusculas.
    """
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(c)
    )
    return " ".join(sin_tildes.lower().split())


def formato_de(nombre: str) -> str:
    """El formato de un fichero por su extension, o "desconocido"."""
    return _FORMATOS.get(os.path.splitext(nombre)[1].lower(), "desconocido")


_ORDEN_GRUPOS = ("molecula", "biblioteca", "resultado")


def _grupo(fila) -> str:
    """
    Molecula, biblioteca o resultado, de la columna `tipo`; en las filas
    anteriores a ella, de la visibilidad (como hace GET /moleculas).
    """
    tipo = fila.tipo.value if fila.tipo else None
    if tipo == "resultado" or fila.visibilidad.value == "resultado":
        return "resultado"
    return "biblioteca" if tipo == "base_de_datos" else "molecula"


def ficheros_para_buscador(filas, consulta: str) -> list:
    """
    La lista del buscador del visor (RF-3) a partir de las filas de
    `archivos` que el usuario puede ver (permisos.archivos_para_visor):
    solo ficheros de moleculas, filtrados por nombre sin mayusculas ni
    tildes, agrupados en moleculas, bibliotecas y resultados, y en cada
    grupo los mas recientes primero.
    """
    q = normalizar(consulta)
    ficheros = [
        {"nombre": f.nombre, "grupo": _grupo(f), "formato": formato_de(f.nombre),
         "num_moleculas": f.num_moleculas, "fecha": f.fecha_creacion}
        for f in filas
        if formato_de(f.nombre) != "desconocido" and q in normalizar(f.nombre)
    ]
    # Dos pasadas estables: primero por fecha (descendente) y despues por
    # grupo, que conserva el orden de fechas dentro de cada uno.
    ficheros.sort(key=lambda f: f["fecha"] or datetime.min, reverse=True)
    ficheros.sort(key=lambda f: _ORDEN_GRUPOS.index(f["grupo"]))
    return ficheros


def nombre_visible(titulo: str, posicion: int) -> str:
    """El nombre de un registro, o "Molécula nº N" si no tiene (RF-6)."""
    return titulo.strip() or "Molécula nº {}".format(posicion)


def buscar_en_titulos(titulos: list, consulta: str, offset: int, limite: int) -> dict:
    """
    Una pagina de la lista de moleculas de un SDF (RF-6), a partir de sus
    titulos en el orden del fichero (indice_sdf.obtener_titulos).

    - Sin consulta: todas, por orden.
    - Con texto: las que lo contienen en el nombre, sin mayusculas ni tildes.
    - Con un entero sin signo: primero la molecula de esa posicion y despues
      las que lo llevan en el nombre ("25" -> la nº 25 y CHEMBL25). Si no hay
      esa posicion se marca `fuera_de_rango` y se siguen dando las del
      nombre. Un negativo o un decimal no es una posicion: se busca como
      texto.

    Las posiciones empiezan en 1, como las ve el usuario; el indice interno
    sigue empezando en 0.
    """
    total = len(titulos)
    q = normalizar(consulta)
    fuera_de_rango = False

    if not q:
        candidatas = range(1, total + 1)
    else:
        por_nombre = [i + 1 for i, t in enumerate(titulos) if q in normalizar(t)]
        candidatas = por_nombre
        if q.isdigit():
            n = int(q)
            if 1 <= n <= total:
                candidatas = [n] + [p for p in por_nombre if p != n]
            else:
                fuera_de_rango = True

    pagina = candidatas[offset:offset + limite]
    return {
        "total": total,
        "coincidencias": [
            {"posicion": p, "nombre": nombre_visible(titulos[p - 1], p)} for p in pagina
        ],
        "hay_mas": offset + limite < len(candidatas),
        "fuera_de_rango": fuera_de_rango,
    }


# ---------------------------------------------------------------------------
# Analisis de un registro SDF (RF-10, RF-12)
#
# Se lee como texto y no con RDKit: un registro danado tiene que poder
# listarse y explicarse igual (RF-12), y los campos se devuelven literales,
# sin la interpretacion que RDKit haria de ellos (RNF-2). Ver la decision D4
# del plan.
# ---------------------------------------------------------------------------

# "> <afinidad>" o "> 25 <afinidad> (CHEMBL25)": el nombre es lo que va entre
# los primeros < >.
_CABECERA_CAMPO = re.compile(r"^>.*?<([^>]*)>")
_COUNTS_V3000 = re.compile(r"^M  V30 COUNTS\s+(\d+)")


def _lineas(registro: bytes) -> list:
    return registro.decode("utf-8", errors="replace").splitlines()


def _num_atomos(lineas: list):
    """
    Los atomos que declara el registro (V2000 o V3000), tal como estan
    escritos: los hidrogenos cuentan solo si el fichero los trae (RF-10).
    None si la linea de cuentas no se puede leer.
    """
    if len(lineas) < 4:
        return None
    cuentas = lineas[3]
    if "V3000" in cuentas:
        for linea in lineas[4:]:
            encontrado = _COUNTS_V3000.match(linea)
            if encontrado:
                return int(encontrado.group(1))
        return None
    try:
        return int(cuentas[0:3])
    except ValueError:
        return None


def _campos(lineas: list) -> list:
    """
    Los campos de datos del registro, en el orden del fichero, con su valor
    literal (varias lineas se unen con salto de linea). Solo se buscan tras
    "M  END": antes, una linea que empiece por ">" es parte del molfile.
    """
    try:
        inicio = next(i for i, l in enumerate(lineas) if l.startswith("M  END")) + 1
    except StopIteration:
        return []

    campos, actual = [], None
    for linea in lineas[inicio:]:
        if linea.strip() == "$$$$":
            break
        cabecera = _CABECERA_CAMPO.match(linea)
        if cabecera and actual is None:
            actual = {"nombre": cabecera.group(1), "lineas": []}
        elif actual is not None:
            if linea.strip() == "":
                campos.append(actual)
                actual = None
            else:
                actual["lineas"].append(linea)
    if actual is not None:
        campos.append(actual)
    return [{"nombre": c["nombre"], "valor": "\n".join(c["lineas"])} for c in campos]


# Motivos de que una molecula no se dibuje (RF-12), en lenguaje llano y con lo
# que se puede hacer (principio 7). Sin el error de la herramienta que lo
# detecto: a un biologo "Explicit valence for atom # 0 N, 4" no le dice nada.
MOTIVO_DANADO = ("Esta molécula está dañada en el fichero y no se puede dibujar. "
                 "Si viene de una biblioteca, puedes limpiarla con un workflow de preparación.")
MOTIVO_SIN_ATOMOS = "Este registro no tiene átomos, así que no hay nada que dibujar."


def _coordenadas_z(lineas: list, num_atomos: int) -> list:
    """La z de cada atomo, del bloque de atomos V2000 o V3000."""
    if "V3000" in lineas[3]:
        # "M  V30 <n> <elemento> <x> <y> <z> ...", entre BEGIN ATOM y END ATOM.
        inicio = lineas.index("M  V30 BEGIN ATOM") + 1
        fin = lineas.index("M  V30 END ATOM")
        return [float(l.split()[6]) for l in lineas[inicio:fin]]
    return [float(l[20:30]) for l in lineas[4:4 + num_atomos]]


def _es_solo_2d(lineas: list, num_atomos) -> bool:
    """
    Todas las z a 0 (RF-12). Con un solo atomo no hay forma que aplanar, asi
    que no se avisa.
    """
    if not num_atomos or num_atomos < 2:
        return False
    try:
        return all(abs(z) < 1e-4 for z in _coordenadas_z(lineas, num_atomos))
    except (ValueError, IndexError):
        return False


def _rdkit_lo_lee(texto: str) -> bool:
    """
    Si RDKit puede leer y sanear el bloque: el mismo criterio que el
    inventario del cribado, de modo que lo que el cribado dio por ilegible el
    visor tampoco lo dibuja. Sin RDKit (no deberia faltar: esta en
    requirements.txt) no se descarta nada por esta via.
    """
    try:
        from rdkit import Chem, rdBase
    except ImportError:
        return True
    with rdBase.BlockLogs():   # el motivo ya lo da el visor; el error no es para el log
        return Chem.MolFromMolBlock(texto, sanitize=True, removeHs=False) is not None


def analizar_sdf(registro: bytes) -> dict:
    """
    Lo que el visor enseña de un registro SDF o MOL: su nombre (la primera
    linea), cuantos atomos declara, sus campos de datos, si solo tiene
    coordenadas 2D y si se puede dibujar (y si no, por que).
    """
    lineas = _lineas(registro)
    num_atomos = _num_atomos(lineas)

    if num_atomos is None:
        dibujable, motivo = False, MOTIVO_DANADO
    elif num_atomos == 0:
        dibujable, motivo = False, MOTIVO_SIN_ATOMOS
    elif not _rdkit_lo_lee("\n".join(lineas)):
        dibujable, motivo = False, MOTIVO_DANADO
    else:
        dibujable, motivo = True, None

    return {
        "nombre": lineas[0].strip() if lineas else "",
        "num_atomos": num_atomos,
        "campos": _campos(lineas),
        "solo_2d": _es_solo_2d(lineas, num_atomos),
        "dibujable": dibujable,
        "motivo": motivo,
    }


# ---------------------------------------------------------------------------
# PDB y PDBQT (RF-9, RF-10, RF-12)
# ---------------------------------------------------------------------------

# Residuos de aminoacido, incluidos los nombres con que las herramientas de
# preparacion y docking marcan la protonacion (HID/HIE/HIP, CYX...): siguen
# siendo el mismo aminoacido de la cadena.
AMINOACIDOS = frozenset({
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
    "SEC", "PYL", "MSE",
    "HID", "HIE", "HIP", "HSD", "HSE", "HSP", "CYX", "CYM", "ASH", "GLH", "LYN",
})


def _residuos_seqres(lineas: list) -> list:
    # "SEQRES   1 A    2  ALA GLY": los residuos empiezan en la columna 20.
    return [r for l in lineas if l.startswith("SEQRES") for r in l[19:].split()]


def es_proteina_pdb(lineas: list) -> bool:
    """
    Si el fichero declara una cadena de proteina (RF-9, decision D5 del
    plan). Lo que manda es lo que el fichero dice de si mismo, no adivinarlo
    por la forma de los atomos:
      - SEQRES es la secuencia declarada de cada polimero: es proteina si
        alguno de sus residuos es un aminoacido (ADN y ARN declaran otros).
      - Sin SEQRES (los PDBQT nunca lo traen), los registros ATOM, que el
        formato reserva para residuos de polimero; HETATM es para lo demas.
    """
    seqres = _residuos_seqres(lineas)
    if seqres:
        return any(r in AMINOACIDOS for r in seqres)
    return any(l.startswith("ATOM") and l[17:20].strip() in AMINOACIDOS for l in lineas)


# Columnas fijas de x, y, z en una linea ATOM/HETATM.
_COLUMNAS_XYZ_PDB = ((30, 38), (38, 46), (46, 54))


def _atomos_pdb(lineas: list) -> list:
    """Las lineas de atomos del primer modelo (un PDB de RMN trae varios)."""
    atomos = []
    for linea in lineas:
        if linea.startswith("ENDMDL"):
            break
        if linea.startswith(("ATOM", "HETATM")):
            atomos.append(linea)
    return atomos


def analizar_pdb(texto: str) -> dict:
    """
    Lo que el visor enseña de un PDB o PDBQT: cuantos atomos tiene (los del
    primer modelo, tal como vienen), si declara una proteina y si se puede
    dibujar.
    """
    lineas = texto.splitlines()
    atomos = _atomos_pdb(lineas)

    try:
        for linea in atomos:
            for inicio, fin in _COLUMNAS_XYZ_PDB:
                float(linea[inicio:fin])
        dibujable, motivo = (True, None) if atomos else (False, MOTIVO_SIN_ATOMOS)
    except ValueError:
        dibujable, motivo = False, MOTIVO_DANADO

    return {
        "num_atomos": len(atomos),
        "es_proteina": es_proteina_pdb(lineas),
        "dibujable": dibujable,
        "motivo": motivo,
    }


# ---------------------------------------------------------------------------
# MOL2 (RF-9, RF-10, RF-12)
# ---------------------------------------------------------------------------

def _seccion_mol2(lineas: list, nombre: str) -> list:
    """Las lineas de una seccion @<TRIPOS>... de la primera molecula."""
    try:
        inicio = lineas.index("@<TRIPOS>" + nombre) + 1
    except ValueError:
        return []
    fin = next((i for i in range(inicio, len(lineas)) if lineas[i].startswith("@<TRIPOS>")), len(lineas))
    return [l for l in lineas[inicio:fin] if l.strip()]


def _residuo_mol2(linea_atomo: str) -> str:
    # "1 N 0.000 0.000 0.000 N.3 1 ALA1 0.0000": el residuo es la
    # subestructura (octava columna) sin su numero.
    partes = linea_atomo.split()
    return partes[7].rstrip("0123456789") if len(partes) > 7 else ""


def analizar_mol2(texto: str) -> dict:
    """
    Lo que el visor enseña de un MOL2 (su primera molecula: los MOL2 con
    varias no se recorren en esta version): nombre, atomos, si declara una
    proteina y si se puede dibujar.

    La proteina la declara la cabecera (decision D5 del plan): PROTEIN lo es
    siempre; BIOPOLYMER vale tambien para acidos nucleicos, asi que lo es si
    sus residuos son aminoacidos, como el SEQRES de un PDB.
    """
    lineas = [l.rstrip() for l in texto.splitlines()]
    molecula = _seccion_mol2(lineas, "MOLECULE")
    if len(molecula) < 2:
        return {"nombre": "", "num_atomos": None, "es_proteina": False,
                "dibujable": False, "motivo": MOTIVO_DANADO}

    nombre = molecula[0].strip()
    tipo = molecula[2].strip().upper() if len(molecula) > 2 else ""
    atomos = _seccion_mol2(lineas, "ATOM")

    if tipo == "PROTEIN":
        es_proteina = True
    elif tipo == "BIOPOLYMER":
        es_proteina = any(_residuo_mol2(a) in AMINOACIDOS for a in atomos)
    else:
        es_proteina = False

    try:
        for atomo in atomos:
            for coordenada in atomo.split()[2:5]:
                float(coordenada)
        dibujable, motivo = (True, None) if atomos else (False, MOTIVO_SIN_ATOMOS)
    except ValueError:
        dibujable, motivo = False, MOTIVO_DANADO

    return {
        "nombre": nombre,
        "num_atomos": len(atomos),
        "es_proteina": es_proteina,
        "dibujable": dibujable,
        "motivo": motivo,
    }


# ---------------------------------------------------------------------------
# XYZ y SMILES (RF-12)
# ---------------------------------------------------------------------------

MOTIVO_SIN_COORDENADAS = (
    "Este fichero describe la molécula sin coordenadas 3D (formato SMILES), así que no se puede "
    "dibujar. Puedes generar su 3D con un workflow de preparación y abrir el resultado aquí.")


def analizar_xyz(texto: str) -> dict:
    """
    Un XYZ: numero de atomos en la primera linea, un comentario (que se toma
    como nombre) y una linea "elemento x y z" por atomo. No trae enlaces: el
    visor los deduce por distancia y se avisa de que pueden no ser exactos.
    """
    lineas = texto.splitlines()
    nombre = lineas[1].strip() if len(lineas) > 1 else ""
    try:
        declarados = int(lineas[0].strip())
        atomos = [l.split() for l in lineas[2:2 + declarados] if l.strip()]
        if len(atomos) != declarados:
            raise ValueError("faltan atomos")
        for atomo in atomos:
            if len(atomo) < 4:
                raise ValueError("atomo incompleto")
            for coordenada in atomo[1:4]:
                float(coordenada)
    except (ValueError, IndexError):
        return {"nombre": nombre, "num_atomos": None, "sin_enlaces": True,
                "dibujable": False, "motivo": MOTIVO_DANADO}

    dibujable, motivo = (True, None) if declarados else (False, MOTIVO_SIN_ATOMOS)
    return {"nombre": nombre, "num_atomos": declarados, "sin_enlaces": True,
            "dibujable": dibujable, "motivo": motivo}


def analizar_smi(texto: str) -> dict:
    """
    Un SMILES ("<cadena> <nombre>") no tiene coordenadas: el visor lo ofrece
    pero explica que no se puede dibujar. Generar el 3D al vuelo queda fuera
    de esta version (spec 002, seccion 7).
    """
    partes = texto.strip().split(None, 1)
    return {"nombre": partes[1].strip() if len(partes) > 1 else "", "num_atomos": None,
            "dibujable": False, "motivo": MOTIVO_SIN_COORDENADAS}


# ---------------------------------------------------------------------------
# Nombre de la descarga (RF-11)
# ---------------------------------------------------------------------------

_LONGITUD_MAXIMA = 100
_LONGITUD_MAXIMA_BIBLIOTECA = 40
_NO_PERMITIDO = re.compile(r"[^A-Za-z0-9_-]+")


def _parte_segura(texto: str) -> str:
    """
    Solo letras ASCII, cifras, "-" y "_". Las tildes se quitan (Cafeína ->
    Cafeina) para que el nombre se descargue igual en cualquier navegador; lo
    demas --barras, puntos, controles, espacios-- pasa a "_".
    """
    ascii_ = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"_+", "_", _NO_PERMITIDO.sub("_", ascii_)).strip("_-")


def nombre_descarga(nombre_molecula: str, posicion: int, nombre_biblioteca: str) -> str:
    """
    El nombre del SDF de una molecula sacada de una biblioteca:
    "<biblioteca>_<molecula>_n<posicion>.sdf", o "<biblioteca>_molecula_<N>.sdf"
    si no tiene nombre. La posicion va siempre, porque una biblioteca puede
    tener varias moleculas con el mismo nombre y no deben pisarse al
    descargarlas.

    El nombre de la molecula lo escribe quien sube el SDF, asi que se trata
    como no fiable (principio 5): sin separadores ni "..", sin controles, y
    con una longitud maxima.
    """
    biblioteca = os.path.basename(nombre_biblioteca.replace("\\", "/"))
    biblioteca = _parte_segura(os.path.splitext(biblioteca)[0])[:_LONGITUD_MAXIMA_BIBLIOTECA] or "biblioteca"
    molecula = _parte_segura(nombre_molecula)
    sufijo = "_n{}".format(posicion) if molecula else ""
    molecula = molecula or "molecula_{}".format(posicion)

    hueco = _LONGITUD_MAXIMA - len(".sdf") - len(biblioteca) - 1 - len(sufijo)
    return "{}_{}{}.sdf".format(biblioteca, molecula[:hueco].rstrip("_-"), sufijo)


# ---------------------------------------------------------------------------
# Leer del fichero (RF-5, RF-6, RF-10): las unicas funciones que abren algo.
# Son finas: sacan los bytes que tocan y delegan en las de arriba.
# ---------------------------------------------------------------------------

class PosicionInexistente(LookupError):
    """La biblioteca no tiene un registro en esa posicion."""


class FaltaPosicion(ValueError):
    """
    Se ha pedido entero un SDF con varias moleculas. Se rechaza en vez de
    leerlo: se mandaria la biblioteca completa para ver una molecula (RNF-1).
    """


MOTIVO_NO_ES_MOLECULA = "Este fichero no contiene moléculas que se puedan dibujar."

# Lo que devuelve leer_molecula para cualquier formato, para que la interfaz
# no tenga que distinguir casos: lo que un formato no sabe, va con su valor
# por defecto.
_POR_DEFECTO = {
    "nombre": "", "num_atomos": None, "campos": [], "es_proteina": False,
    "solo_2d": False, "sin_enlaces": False, "dibujable": False, "motivo": None,
}

_ANALIZADORES_DE_TEXTO = {
    "pdb":   analizar_pdb,
    "pdbqt": analizar_pdb,
    "mol2":  analizar_mol2,
    "xyz":   analizar_xyz,
    "smi":   analizar_smi,
}


def _registro(ruta_sdf: str, posicion) -> bytes:
    """
    Los bytes del registro `posicion` (desde 1) de un SDF o MOL, saltando a
    el con el mapa. Sin posicion, el unico registro del fichero: con varios
    hay que elegir (FaltaPosicion), porque se leeria la biblioteca entera.
    """
    limites = indice_sdf.obtener(ruta_sdf)
    registros = len(limites) - 1
    if posicion is None:
        if registros > 1:
            raise FaltaPosicion(os.path.basename(ruta_sdf))
        indice = 0
    elif 1 <= posicion <= registros:
        indice = posicion - 1
    else:
        raise PosicionInexistente(posicion)
    if not registros:
        return b""
    with open(ruta_sdf, "rb") as f:
        return indice_sdf.leer_registro(f, limites, indice)


def preparar_descarga(ruta: str, posicion):
    """
    Que se entrega al descargar desde el visor (RF-11):
      - con `posicion`, (registro como SDF con todos sus campos, nombre seguro);
      - sin ella, (None, nombre del fichero): se entrega el original tal cual.
    Siempre en el formato de origen, sin conversiones.
    """
    origen = os.path.basename(ruta)
    if posicion is None:
        if formato_de(ruta) in ("sdf", "mol"):
            _registro(ruta, None)        # solo para rechazar una biblioteca entera
        return None, origen
    if formato_de(ruta) not in ("sdf", "mol"):
        raise PosicionInexistente(posicion)
    registro = indice_sdf.terminado(_registro(ruta, posicion))
    return registro, nombre_descarga(indice_sdf.titulo(registro), posicion, origen)


def pagina_de_moleculas(ruta_sdf: str, consulta: str, offset: int, limite: int) -> dict:
    """Una pagina de la lista de un SDF, desde su mapa de titulos (RF-6)."""
    return buscar_en_titulos(indice_sdf.obtener_titulos(ruta_sdf), consulta, offset, limite)


def leer_molecula(ruta: str, posicion: int = None) -> dict:
    """
    La molecula que el visor dibuja y describe:
      - con `posicion` (desde 1), ese registro de un SDF, leido con el mapa y
        sin pasar por el resto del fichero;
      - sin ella, el fichero entero, que tiene que tener una sola molecula.

    Devuelve siempre las mismas claves (ver _POR_DEFECTO), mas `contenido`
    (el texto que se dibuja), `formato`, `origen` y `posicion`.
    """
    formato = formato_de(ruta)
    origen = os.path.basename(ruta)

    if formato in ("sdf", "mol"):
        registro = _registro(ruta, posicion)
        datos = analizar_sdf(registro)
        if posicion is not None:
            datos["nombre"] = nombre_visible(datos["nombre"], posicion)
        contenido = registro.decode("utf-8", errors="replace")

    else:
        if posicion is not None:
            # Solo un SDF se recorre por posiciones (spec 002).
            raise PosicionInexistente(posicion)
        with open(ruta, "rb") as f:
            contenido = f.read().decode("utf-8", errors="replace")
        analizar = _ANALIZADORES_DE_TEXTO.get(formato)
        datos = analizar(contenido) if analizar else {"motivo": MOTIVO_NO_ES_MOLECULA}
        # Un PDB no se nombra a si mismo: el usuario lo reconoce por el fichero.
        datos["nombre"] = datos.get("nombre") or os.path.splitext(origen)[0]

    return {**_POR_DEFECTO, **datos,
            "contenido": contenido, "formato": formato, "origen": origen, "posicion": posicion}
