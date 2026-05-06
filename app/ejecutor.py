import os
import sys
import subprocess

def ejecutar_algoritmo(ruta_algoritmo: str, ruta_mol_entrada: str, ruta_mol_salida: str) -> dict:
    """
    Ejecuta un algoritmo sobre una molécula y devuelve el resultado.
    
    Ahora mismo: ejecuta localmente con subprocess (para desarrollo).
    En el futuro: aquí se sustituirá por la llamada al HPC (SLURM, SSH, API del clúster...).
    
    Devuelve un dict con:
        - exito (bool)
        - log (str): lo que imprime el script
        - error (str): mensaje de error si falla
    """
    try:
        resultado = subprocess.run(
            [sys.executable, ruta_algoritmo, ruta_mol_entrada, ruta_mol_salida],
            capture_output=True,
            text=True,
            check=True
        )
        return {
            "exito": True,
            "log": resultado.stdout,
            "error": None
        }
    except subprocess.CalledProcessError as e:
        return {
            "exito": False,
            "log": None,
            "error": e.stderr
        }