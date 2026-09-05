import sys
import subprocess
from app.config import EXECUTION_MODE


def ejecutar_algoritmo(ruta_algoritmo: str, *archivos) -> dict:
    """
    Ejecuta un algoritmo sobre una o varias moléculas.

    Los archivos se pasan directamente como argumentos posicionales al script Python.
    Convención:
        - Algoritmo de 1 entrada:  ejecutar_algoritmo(algo, entrada, salida)
        - Algoritmo de 2 entradas: ejecutar_algoritmo(algo, entrada1, entrada2, salida)
        - Docking:                 ejecutar_algoritmo(algo, ligando, receptor, salida)

    Enruta según EXECUTION_MODE (app/config.py):
        - "local" (por defecto): ejecuta el script con subprocess en esta misma máquina.
        - "slurm": delega en SlurmExecutor (app/slurm_executor.py), que envía el trabajo
          al clúster Picasso de la UAL vía SSH + sbatch.

    Devuelve un dict con:
        - exito (bool)
        - log   (str): salida estándar del script
        - error (str): mensaje de error si falla
    """
    if EXECUTION_MODE == "slurm":
        return _ejecutar_en_slurm(ruta_algoritmo, *archivos)
    return _ejecutar_local(ruta_algoritmo, *archivos)


def _ejecutar_local(ruta_algoritmo: str, *archivos) -> dict:
    try:
        resultado = subprocess.run(
            [sys.executable, ruta_algoritmo, *archivos],
            capture_output=True,
            text=True,
            check=True,
        )
        return {
            "exito": True,
            "log":   resultado.stdout,
            "error": None,
        }
    except subprocess.CalledProcessError as e:
        return {
            "exito": False,
            "log":   e.stdout,
            "error": e.stderr,
        }


def _ejecutar_en_slurm(ruta_algoritmo: str, *archivos) -> dict:
    # Import diferido: paramiko y la dependencia del clúster solo son necesarias
    # cuando EXECUTION_MODE=slurm, así el modo local no requiere tenerlas instaladas.
    from app.slurm_executor import SlurmExecutor

    return SlurmExecutor().ejecutar_algoritmo(ruta_algoritmo, *archivos)
