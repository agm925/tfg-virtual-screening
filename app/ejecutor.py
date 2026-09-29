import os
import sys
import subprocess
from app.config import ALGORITMO_TIMEOUT, EXECUTION_MODE

# Los algoritmos imprimen caracteres no ASCII en sus resúmenes por consola
# ("→" en filtroLipinski, "Å" en rmsdConformaciones, "✓"/"≤" en dockingSmina).
# En Windows el proceso hijo hereda la codepage del sistema (cp1252), donde
# esos caracteres no existen: el print() del script lanza UnicodeEncodeError,
# el propio script lo captura como un fallo suyo y escribe {"exito": false}.
# Resultado: esos algoritmos fallaban SIEMPRE en ejecución local sobre Windows,
# mientras que en Docker (Linux/UTF-8) funcionaban. Forzamos UTF-8 en ambos
# lados: PYTHONIOENCODING para que el hijo pueda emitirlos, y encoding= para
# que el padre los decodifique igual.
_ENTORNO_HIJO = {**os.environ, "PYTHONIOENCODING": "utf-8"}


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
