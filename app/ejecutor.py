import contextvars
import os
import sys
import subprocess
import tempfile
from contextlib import contextmanager
from app.config import ALGORITMO_TIMEOUT, EXECUTION_MODE

# Variables que un algoritmo SÍ necesita. Todo lo demás se queda fuera.
#
# Antes el hijo heredaba os.environ entero, y el entorno del worker lleva la
# URL de la base de datos con su contraseña, la contraseña del correo y la
# clave con la que se firman los JWT. Cualquier usuario registrado puede subir
# un algoritmo: bastaba con uno que pasara el banco de pruebas --donde no hay
# secretos-- y que en la ejecución real volcara su entorno al JSON de salida
# para fabricarse un token de administrador. Es la misma lista blanca que usa
# el banco (app/banco_pruebas.py), más lo que Windows necesita para arrancar
# un proceso Python en ejecución local fuera de Docker.
_VARIABLES_HEREDABLES = (
    "PATH", "LANG", "LC_ALL", "LANGUAGE", "TZ", "TMPDIR",
    # Sin SYSTEMROOT, Python en Windows no puede ni inicializar su generador
    # de números aleatorios; TEMP/TMP es donde las bibliotecas crean temporales.
    "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT", "COMSPEC",
    # Dónde busca Open Babel sus tablas si no están en la ruta por defecto.
    "BABEL_DATADIR", "BABEL_LIBDIR", "LD_LIBRARY_PATH",
)


def _entorno_algoritmo() -> dict:
    entorno = {k: v for k, v in os.environ.items() if k.upper() in _VARIABLES_HEREDABLES}
    # HOME desechable: varias bibliotecas científicas escriben cachés en él, y
    # el del worker es /root, donde viven las credenciales del clúster.
    entorno["HOME"] = tempfile.gettempdir()
    # Los algoritmos imprimen caracteres no ASCII en sus resúmenes por consola
    # ("→" en filtroLipinski, "Å" en rmsdConformaciones, "✓"/"≤" en
    # dockingSmina). En Windows el hijo usaría la codepage del sistema
    # (cp1252), donde no existen: el print() lanzaba UnicodeEncodeError y el
    # algoritmo fallaba SIEMPRE en local sobre Windows. PYTHONIOENCODING para
    # que el hijo pueda emitirlos, y encoding= en subprocess.run para que el
    # padre los decodifique igual.
    entorno["PYTHONIOENCODING"] = "utf-8"
    return entorno


_ENTORNO_HIJO = _entorno_algoritmo()

# Usuario con el que corre el algoritmo cuando el worker es root (en Docker).
#
# Filtrar el entorno no basta por sí solo: un proceso del mismo usuario puede
# leer /proc/1/environ, que es el entorno completo del worker, y con él todos
# los secretos que se acaban de quitar. Como nobody, el algoritmo no puede leer el entorno
# de un proceso de root, ni entrar en /root, donde está la clave SSH del
# clúster (ver docker-compose.yml). Es el mismo usuario con el que corre el
# contenedor del banco de pruebas.
#
# Fuera de Docker el worker no es root y no puede cambiar de usuario: ahí el
# algoritmo corre como quien lanzó el worker, igual que antes.
_UID_ALGORITMOS = 65534


def _credenciales_hijo() -> dict:
    if os.name != "posix" or os.geteuid() != 0:
        return {}
    return {"user": _UID_ALGORITMOS, "group": _UID_ALGORITMOS, "extra_groups": []}


def ejecutar_algoritmo(ruta_algoritmo: str, *archivos, flags=()) -> dict:
    """
    Ejecuta un algoritmo sobre una o varias moléculas.

    Los archivos se pasan como argumentos posicionales al script Python, y las
    opciones --si las hay-- detrás, en el mismo orden en que se reciben.
    Convención:
        - Algoritmo de 1 entrada:  ejecutar_algoritmo(algo, entrada, salida)
        - Algoritmo de 2 entradas: ejecutar_algoritmo(algo, entrada1, entrada2, salida)
        - Docking:                 ejecutar_algoritmo(algo, ligando, receptor, salida,
                                                      flags=["--scoring", "vinardo"])

    `flags` va aparte de `archivos` y NO es cosmético: en modo slurm cada
    elemento de `archivos` se sube al nodo del clúster y se sustituye por su
    ruta remota. Cuando las opciones viajaban mezcladas con los ficheros,
    "--exhaustiveness" acababa convertido en "/…/job_abc123/--exhaustiveness",
    que ya no empieza por "--": dockingSmina.py las descartaba en silencio y
    corría con sus valores por defecto. Local funcionaba y el clúster no, sin
    un solo error por ninguna parte.

    Enruta según EXECUTION_MODE (app/config.py):
        - "local" (por defecto): ejecuta el script con subprocess en esta misma máquina.
        - "slurm": delega en SlurmExecutor (app/slurm_executor.py), que envía el trabajo
          al clúster bullx (HPCA, Universidad de Almería) vía SSH + sbatch.

    Devuelve un dict con:
        - exito (bool)
        - log   (str): salida estándar del script
        - error (str): mensaje de error si falla
    """
    # El cribado en lote desvia las invocaciones para agruparlas (ver
    # desviar_invocaciones). Si no hay desvio puesto, o el gancho decide no
    # hacerse cargo, se sigue por donde siempre.
    gancho = _desvio.get()
    if gancho is not None:
        resultado = gancho(ruta_algoritmo, archivos, flags)
        if resultado is not None:
            return resultado

    if EXECUTION_MODE == "slurm":
        return _ejecutar_en_slurm(ruta_algoritmo, *archivos, flags=flags)
    return _ejecutar_local(ruta_algoritmo, *archivos, flags=flags)


def _texto(salida) -> str:
    """subprocess devuelve str con text=True, pero TimeoutExpired puede traer
    bytes sin decodificar segun la version de Python; normalizamos a str."""
    if isinstance(salida, bytes):
        return salida.decode("utf-8", errors="ignore")
    return salida or ""


def _ejecutar_local(ruta_algoritmo: str, *archivos, flags=()) -> dict:
    try:
        resultado = subprocess.run(
            [sys.executable, ruta_algoritmo, *archivos, *flags],
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
            errors="replace",
            env=_ENTORNO_HIJO,
            **_credenciales_hijo(),
            # Sin timeout, un algoritmo que se cuelga bloquea el worker de
            # Celery para siempre (ver ALGORITMO_TIMEOUT en app/config.py).
            timeout=ALGORITMO_TIMEOUT,
        )
        return {
            "exito": True,
            "log":   resultado.stdout,
            "error": None,
        }
    except subprocess.TimeoutExpired as e:
        # subprocess.run ya ha matado el proceso hijo antes de propagar esta
        # excepcion, asi que el worker queda libre para la siguiente tarea.
        return {
            "exito": False,
            "log":   _texto(e.stdout),
            "error": (
                f"El algoritmo superó el límite de {ALGORITMO_TIMEOUT}s "
                f"y se abortó. Ajusta ALGORITMO_TIMEOUT si el cálculo "
                f"legítimamente necesita más tiempo."
            ),
        }
    except subprocess.CalledProcessError as e:
        return {
            "exito": False,
            "log":   e.stdout,
            "error": e.stderr,
        }


def _ejecutar_en_slurm(ruta_algoritmo: str, *archivos, flags=()) -> dict:
    # Import diferido: paramiko y la dependencia del clúster solo son necesarias
    # cuando EXECUTION_MODE=slurm, así el modo local no requiere tenerlas instaladas.
    from app.slurm_executor import SlurmExecutor

    return SlurmExecutor().ejecutar_algoritmo(ruta_algoritmo, *archivos, flags=flags)


# ---------------------------------------------------------------------------
# Desvio de invocaciones (lo usa el cribado en lote)
# ---------------------------------------------------------------------------

_desvio = contextvars.ContextVar("desvio_invocaciones", default=None)


@contextmanager
def desviar_invocaciones(gancho):
    """
    Mientras dure el bloque, cada ejecutar_algoritmo pasa antes por `gancho`.

    `gancho(ruta_algoritmo, archivos, flags)` devuelve un resultado con el que
    sustituir la ejecucion, o None para dejarla seguir su camino normal.

    Existe por el cribado en lote. El motor de workflows ejecuta el grafo
    molecula a molecula y no sabe nada de SLURM --ni debe--, asi que este es el
    punto por el que BatchWorkflowExecutor puede recoger las N invocaciones,
    mandarlas como UN job array y luego servir cada resultado sin volver a
    tocar el cluster. La alternativa era que el camino en lote se
    reimplementara la logica de cada tipo de nodo: dos sitios donde arreglar
    cada cosa, y uno de los dos siempre se queda atras.
    """
    testigo = _desvio.set(gancho)
    try:
        yield
    finally:
        _desvio.reset(testigo)


def ejecutar_algoritmos_en_lote(invocaciones) -> list:
    """
    N invocaciones independientes de una vez, en el mismo orden.

    Cada invocacion es (ruta_algoritmo, archivos, flags). En modo slurm se
    manda como UN job array --una conexion, un sbatch, una espera-- y en local
    no hay nada que agrupar: se ejecutan en serie, exactamente como antes.
    """
    invocaciones = list(invocaciones)
    if not invocaciones:
        return []

    if EXECUTION_MODE == "slurm":
        from app.slurm_executor import SlurmExecutor
        return SlurmExecutor().ejecutar_lote(invocaciones)

    return [_ejecutar_local(ruta, *archivos, flags=flags)
            for ruta, archivos, flags in invocaciones]
