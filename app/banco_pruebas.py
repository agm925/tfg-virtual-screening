"""
Banco de pruebas para algoritmos subidos al catálogo.

Antes de este módulo, subir un algoritmo era un acto de fe: el metadato
`# TIPO_ALGORITMO` lo declaraba el propio autor y no se comprobaba contra
nada, y nadie verificaba que el script llegara siquiera a ejecutarse. Un
algoritmo roto entraba en el catálogo igual que uno correcto, y el fallo
aparecía horas después, dentro de un cribado, como una molécula fallida entre
mil.

La idea es sencilla: el autor DECLARA qué hace su algoritmo --hoy, eligiendo
el tipo en el formulario de subida; el metadato en el script ya no hace
falta, y app/main.py no lo lee-- y la plataforma lo VERIFICA ejecutándolo
contra un par de moléculas de referencia antes de aceptarlo. El tipo
declarado es lo que permite saber cómo invocarlo --una molécula, dos, o
ligando más receptor-- y la ejecución comprueba que esa declaración sea
cierta.

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

DÓNDE SE EJECUTA
----------------
Probar un algoritmo es, por definición, ejecutar código que acaba de llegar y
que todavía no se ha aceptado. Eso obliga a ser muy preciso sobre dónde ocurre.

En la primera versión ocurría dentro del proceso del backend, en la propia
petición HTTP de subida, como root y heredando su entorno completo. Es decir:
un algoritmo subido podía leer `JWT_SECRET_KEY` --y firmarse un token de
administrador--, `DATABASE_URL`, `SMTP_PASSWORD` y las credenciales del
clúster, además de reescribir otros algoritmos del catálogo a través del
volumen montado. La pieza añadida para aumentar la seguridad ampliaba la
superficie de ataque.

Ahora la ejecución se delega en el servicio `banco` (ver `app/banco_servidor.py`
y el `docker-compose.yml`), un contenedor aparte que:

  · no monta `uploads/` ni `algoritmos/`, de modo que no ve ningún fichero de
    ningún usuario --solo las moléculas de referencia, horneadas en la imagen--;
  · no recibe ninguna variable de entorno con secretos;
  · vive en una red `internal`, sin salida a internet ni acceso a la base de
    datos ni a Redis;
  · corre como usuario sin privilegios, con el sistema de ficheros en solo
    lectura salvo un `tmpfs`, sin capacidades y con límites de memoria y de
    número de procesos.

Si ese servicio no está disponible, la subida se RECHAZA en vez de recurrir a
ejecutar el script en el backend: degradar a la ruta insegura en silencio sería
peor que rechazar, porque reintroduciría el problema justo cuando nadie mira.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

from app.config import ALGORITMO_TIMEOUT, BANCO_SOCKET, BANCO_URL
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


# --- Interfaz declarada (spec 013) -------------------------------------------
#
# Hasta la spec 013 la forma de llamar a un algoritmo iba fija por tipo
# (INVOCACIONES). El script con el que se encontro el problema se usa como
# `entrada -o salida --all`, y el banco lo llamaba `entrada salida`: argparse
# rechazaba el segundo posicional y el algoritmo no se podia subir. Ahora el
# autor declara su interfaz: sus entradas de fichero, como recibe la salida y
# sus opciones de si/no. Sin interfaz, la llamada de siempre.
#
# La validacion vive aqui, sin pydantic, para que la usen igual el backend al
# subir y el servicio `banco`, que no se fia de quien le llama.

MAX_ENTRADAS = 6
MAX_OPCIONES = 6
MAX_NOMBRE = 40
CLASES_ENTRADA = ("molecula", "proteina")
# Una opcion de linea de comandos y nada mas: ni espacios ni ;, que en una
# lista de argumentos no harian dano, pero si en un mensaje o en un log.
PATRON_OPCION = re.compile(r"^--?[A-Za-z][A-Za-z0-9_-]{0,30}$")

# Ligandos de referencia por orden de entrada. ligando_a y ligando_b son la
# misma molecula en dos conformaciones, que es lo que necesitan las
# comparaciones tipo RMSD; los demas son moleculas distintas
# (scripts/generar_referencias.py).
LIGANDOS = [os.path.join(REFERENCIA, f"ligando_{letra}.sdf") for letra in "abcdef"]

# Las entradas de hoy de cada tipo, con los nombres que se ensenan al autor.
# Una interfaz igual a esta se guarda como null: se llama como siempre.
ENTRADAS_POR_DEFECTO = {
    "preprocesado": [{"nombre": "Molécula", "clase": "molecula"}],
    "alineacion":   [{"nombre": "Molécula", "clase": "molecula"}],
    "comparacion":  [{"nombre": "Molécula 1", "clase": "molecula"},
                     {"nombre": "Molécula 2", "clase": "molecula"}],
    "docking":      [{"nombre": "Ligando", "clase": "molecula"},
                     {"nombre": "Receptor", "clase": "proteina"}],
}


def _nombre_valido(valor, que: str) -> str:
    if not isinstance(valor, str):
        raise ValueError(f"{que}: falta el nombre.")
    nombre = valor.strip()
    if not nombre:
        raise ValueError(f"{que}: el nombre no puede estar vacío.")
    if len(nombre) > MAX_NOMBRE:
        raise ValueError(f"{que}: el nombre no puede pasar de {MAX_NOMBRE} caracteres.")
    if re.search(r"[\x00-\x1f\x7f]", nombre):
        raise ValueError(f"{que}: el nombre no puede llevar saltos de línea ni caracteres de control.")
    return nombre


def _opcion_valida(valor, que: str) -> str:
    if not isinstance(valor, str) or not PATRON_OPCION.match(valor):
        raise ValueError(f"{que}: «{valor}» no es una opción válida (por ejemplo -o o --all).")
    return valor


def validar_interfaz(interfaz) -> dict:
    """
    Comprueba la interfaz que declara el autor y la devuelve normalizada
    ({entradas, opcion_salida, opciones}). Lanza ValueError con el motivo en
    lenguaje llano.
    """
    if not isinstance(interfaz, dict):
        raise ValueError("La interfaz del algoritmo no tiene el formato esperado.")
    sobrantes = set(interfaz) - {"entradas", "opcion_salida", "opciones"}
    if sobrantes:
        raise ValueError(f"La interfaz lleva campos que no se conocen: {', '.join(sorted(sobrantes))}.")

    entradas = interfaz.get("entradas")
    if not isinstance(entradas, list) or not 1 <= len(entradas) <= MAX_ENTRADAS:
        raise ValueError(f"El algoritmo debe tener entre 1 y {MAX_ENTRADAS} entradas.")
    normalizadas = []
    for i, entrada in enumerate(entradas, start=1):
        if not isinstance(entrada, dict) or entrada.get("clase") not in CLASES_ENTRADA:
            raise ValueError(f"Entrada {i}: la clase debe ser molécula o proteína.")
        normalizadas.append({"nombre": _nombre_valido(entrada.get("nombre"), f"Entrada {i}"),
                             "clase": entrada["clase"]})

    opcion_salida = interfaz.get("opcion_salida")
    if opcion_salida is not None:
        opcion_salida = _opcion_valida(opcion_salida, "Salida")

    opciones = interfaz.get("opciones") or []
    if not isinstance(opciones, list) or len(opciones) > MAX_OPCIONES:
        raise ValueError(f"El algoritmo puede tener como mucho {MAX_OPCIONES} opciones.")
    vistas = {opcion_salida}
    normalizadas_op = []
    for i, opcion in enumerate(opciones, start=1):
        if not isinstance(opcion, dict):
            raise ValueError(f"Opción {i}: no tiene el formato esperado.")
        valor = _opcion_valida(opcion.get("opcion"), f"Opción {i}")
        if valor in vistas:
            raise ValueError(f"Opción {i}: «{valor}» está repetida.")
        vistas.add(valor)
        normalizadas_op.append({"opcion": valor, "nombre": _nombre_valido(opcion.get("nombre"), f"Opción {i}")})

    return {"entradas": normalizadas, "opcion_salida": opcion_salida, "opciones": normalizadas_op}


def es_interfaz_por_defecto(tipo: str, interfaz: dict) -> bool:
    """
    Si se llama igual que hoy a los de su tipo: mismas clases de entrada, la
    salida al final y sin opciones. Entonces se guarda null y se ejecuta por
    el camino de siempre (los nombres solo cambiarian etiquetas).
    """
    por_defecto = ENTRADAS_POR_DEFECTO.get(tipo)
    return (por_defecto is not None
            and [e["clase"] for e in interfaz["entradas"]] == [e["clase"] for e in por_defecto]
            and interfaz["opcion_salida"] is None
            and not interfaz["opciones"])


def llamada_legible(nombre_script: str, nombres_entradas, opcion_salida, nombre_salida, opciones) -> str:
    """La llamada como la vera el autor: con los nombres de sus entradas, no con rutas."""
    partes = [nombre_script, *nombres_entradas]
    if opcion_salida:
        partes.append(opcion_salida)
    partes.append(nombre_salida)
    partes.extend(opciones)
    return " ".join(partes)


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
            "log": self.log,
        }

    @classmethod
    def desde_dict(cls, datos: dict) -> "ResultadoPrueba":
        """Reconstruye el resultado que devuelve el servicio aislado."""
        r = cls()
        r.valido = bool(datos.get("valido"))
        r.motivo = datos.get("motivo")
        r.detalle = datos.get("detalle")
        r.formato_salida = datos.get("formato_salida")
        r.clave_score = datos.get("clave_score")
        r.claves_json = datos.get("claves_json") or []
        r.log = datos.get("log") or ""
        return r


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


# Variables que el subproceso SÍ necesita. Todo lo demás se queda fuera.
#
# El proceso que invoca el banco tiene en su entorno la URL de la base de datos
# con su contraseña, la clave de firma de los JWT, la contraseña del correo y
# las credenciales del clúster. Pasarle `os.environ` entero a un script que
# todavía no se ha aceptado es regalárselas. Se filtra a una lista blanca: PATH
# para que encuentre obabel y smina, y poco más.
_VARIABLES_HEREDABLES = ("PATH", "LANG", "LC_ALL", "LANGUAGE", "TZ", "TMPDIR")


def _entorno_minimo() -> dict:
    entorno = {k: v for k, v in os.environ.items() if k in _VARIABLES_HEREDABLES}
    entorno.setdefault("PATH", "/usr/local/bin:/usr/local/sbin:/usr/bin:/bin")
    # HOME propio y desechable: varias bibliotecas científicas escriben cachés
    # en él, y no deben tocar el del usuario que ejecuta el servicio.
    entorno["HOME"] = tempfile.gettempdir()
    entorno["PYTHONIOENCODING"] = "utf-8"
    # Sin .pyc: el sistema de ficheros del sandbox es de solo lectura.
    entorno["PYTHONDONTWRITEBYTECODE"] = "1"
    return entorno


def probar_algoritmo(ruta_script: str, tipo: str, interfaz: dict = None) -> ResultadoPrueba:
    """
    Comprueba un algoritmo, ejecutándolo donde toque.

    Si hay un servicio de banco configurado (`BANCO_URL`), le delega la
    ejecución: es un contenedor aislado, sin secretos, sin ficheros de usuarios
    y sin red (ver el docstring del módulo). Si no lo hay --tests, desarrollo
    local, uso del módulo como biblioteca-- se ejecuta en este mismo proceso.
    """
    if BANCO_SOCKET or BANCO_URL:
        return _probar_en_servicio_aislado(ruta_script, tipo, interfaz)
    return probar_en_proceso(ruta_script, tipo, interfaz)


def _probar_en_servicio_aislado(ruta_script: str, tipo: str, interfaz: dict = None) -> ResultadoPrueba:
    """Envía el script al contenedor del banco y traduce su respuesta."""
    import httpx

    resultado = ResultadoPrueba()

    # Socket Unix si lo hay: el sandbox no tiene red, así que no hay host al
    # que conectarse. El nombre de la URL es entonces irrelevante --httpx lo
    # exige, pero la conexión la resuelve el transporte-- y se deja "banco"
    # para que los logs sean legibles.
    if BANCO_SOCKET:
        transporte = httpx.HTTPTransport(uds=BANCO_SOCKET)
        url = "http://banco/probar"
    else:
        transporte = None
        url = BANCO_URL.rstrip("/") + "/probar"

    try:
        with open(ruta_script, "rb") as f:
            # Con holgura sobre el límite del propio banco: si el script se
            # cuelga, quien debe cortarlo es el banco, con su mensaje.
            with httpx.Client(transport=transporte, timeout=TIMEOUT_PRUEBA + 60) as cliente:
                respuesta = cliente.post(
                    url,
                    data={"tipo": tipo, **({"interfaz": json.dumps(interfaz)} if interfaz else {})},
                    files={"archivo": (os.path.basename(ruta_script), f, "text/x-python")},
                )
    except Exception as e:  # noqa: BLE001
        # Fallar cerrado: no se recurre a ejecutar el script aquí.
        resultado.motivo = (
            "El servicio de validación de algoritmos no está disponible, así que "
            "no se puede comprobar el algoritmo antes de aceptarlo. Inténtalo de "
            "nuevo en unos minutos."
        )
        resultado.detalle = str(e)[:500]
        return resultado

    if respuesta.status_code != 200:
        resultado.motivo = (
            "El servicio de validación de algoritmos respondió con un error "
            f"({respuesta.status_code})."
        )
        resultado.detalle = respuesta.text[:500]
        return resultado

    return ResultadoPrueba.desde_dict(respuesta.json())


def probar_en_proceso(ruta_script: str, tipo: str, interfaz: dict = None) -> ResultadoPrueba:
    """
    Ejecuta un algoritmo contra las moléculas de referencia y comprueba que
    hace lo que su autor declara.

    ATENCIÓN: ejecuta el script en ESTE proceso. Es lo correcto dentro del
    contenedor del banco, que está aislado a propósito; fuera de él, quien lo
    llame debe saber que está ejecutando código no verificado con sus propios
    privilegios.

    Con `interfaz` (spec 013) se le llama como dice su autor; sin ella, como
    a todos los de su tipo. Si declara opciones se ejecuta dos veces, sin
    ninguna y con todas: un algoritmo que falla con una opción que ofrece
    fallaría igual dentro de un cribado.

    No lanza excepciones: devuelve siempre un ResultadoPrueba, para que quien
    lo llame pueda dar al usuario un mensaje claro.
    """
    resultado = ResultadoPrueba()

    tipo = (tipo or "").lower()
    if tipo not in INVOCACIONES:
        resultado.motivo = f"Tipo de algoritmo desconocido: '{tipo}'."
        return resultado
    if interfaz is not None:
        try:
            interfaz = validar_interfaz(interfaz)
        except ValueError as e:
            resultado.motivo = str(e)
            return resultado

    for referencia in [*LIGANDOS, RECEPTOR]:
        if not os.path.exists(referencia):
            resultado.motivo = (
                "Faltan las moléculas de referencia del banco de pruebas "
                f"({os.path.basename(referencia)}). Es un problema de la "
                "instalación, no de tu algoritmo."
            )
            return resultado

    opciones = [o["opcion"] for o in interfaz["opciones"]] if interfaz else []
    # Primero sin opciones: es la pasada que se observa (formato, puntuación).
    pasadas = [[], opciones] if opciones else [[]]
    for marcadas in pasadas:
        pasada = _una_pasada(ruta_script, tipo, interfaz, marcadas)
        if not pasada.valido:
            if marcadas:
                pasada.motivo = f"Con las opciones {' '.join(marcadas)} marcadas: {pasada.motivo}"
            return pasada
        if not marcadas:
            resultado = pasada
    return resultado


def _una_pasada(ruta_script: str, tipo: str, interfaz, opciones_marcadas) -> ResultadoPrueba:
    """Una ejecución del algoritmo, con las opciones dadas, y lo que se observa de ella."""
    resultado = ResultadoPrueba()

    with tempfile.TemporaryDirectory(prefix="banco_") as tmp:
        salida = os.path.join(tmp, "salida" + EXTENSION_PRUEBA[tipo])
        if interfaz:
            # Las entradas en un subdirectorio: la salida se busca entre los
            # ficheros del temporal, y una copia del receptor no puede pasar
            # por lo que escribió el algoritmo.
            dir_entradas = os.path.join(tmp, "entradas")
            os.mkdir(dir_entradas)
            archivos, ligandos = [], iter(LIGANDOS)
            for i, entrada in enumerate(interfaz["entradas"], start=1):
                if entrada["clase"] == "molecula":
                    archivos.append(next(ligandos))
                else:
                    # Cada proteína con su propio fichero: dos entradas no
                    # reciben la misma ruta.
                    copia = os.path.join(dir_entradas, f"receptor_{i}.pdbqt")
                    shutil.copyfile(RECEPTOR, copia)
                    archivos.append(copia)
            nombres = [e["nombre"] for e in interfaz["entradas"]]
            opcion_salida = interfaz["opcion_salida"]
        else:
            archivos = list(INVOCACIONES[tipo])
            nombres = [e["nombre"] for e in ENTRADAS_POR_DEFECTO[tipo]]
            opcion_salida = None
        argumentos = [*archivos, *([opcion_salida] if opcion_salida else []), salida, *opciones_marcadas]
        llamada = llamada_legible(os.path.basename(ruta_script), nombres, opcion_salida,
                                  os.path.basename(salida), opciones_marcadas)

        try:
            proceso = subprocess.run(
                [sys.executable, ruta_script, *argumentos],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                env=_entorno_minimo(),
                # cwd en el temporal: un script que escriba rutas relativas
                # ensucia su propio directorio de usar y tirar, no el del
                # servicio ni el catálogo de algoritmos.
                cwd=tmp,
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
            # La llamada que se hizo, con los nombres de las entradas: si no
            # coincide con la que espera el script (otro número de entradas,
            # la salida con -o...), es lo primero que el autor tiene que ver.
            resultado.motivo = (
                "El algoritmo terminó con error al ejecutarlo sobre las "
                f"moléculas de referencia. Se ejecutó así: {llamada}"
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
                "fichero de salida. Comprueba que escribe la salida en la ruta "
                f"que recibe. Se ejecutó así: {llamada}"
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
