# TIPO_ALGORITMO: preprocesado
"""
Filtro de propiedades con OpenBabel (--filter)
Filtra una molécula o biblioteca según una expresión sobre propiedades
fisicoquímicas (MW, logP, HBD, HBA, TPSA, ...) sin necesidad de convertir
manualmente de formato.

Uso:
    python filtroObabel.py <archivo_entrada> <archivo_salida> [expresion_filtro]

    expresion_filtro por defecto: "MW>200"

Ejemplo:
    python filtroObabel.py biblioteca.sdf filtrado.sdf "MW>200 and HBD<=5"

Si ninguna molécula cumple el filtro, el archivo de salida queda vacío
(comportamiento estándar de OpenBabel) y se informa por consola.
"""

import sys
import os
import subprocess
import shutil


def obtener_formato(ruta: str) -> str:
    """Devuelve el identificador de formato que entiende OpenBabel a partir de la extensión."""
    ext = os.path.splitext(ruta)[1].lower().lstrip(".")
    equivalencias = {"mol": "mol", "mol2": "mol2", "sdf": "sdf", "pdb": "pdb",
                     "pdbqt": "pdbqt", "smi": "smi", "xyz": "xyz"}
    return equivalencias.get(ext, ext) or "sdf"


def filtrar_molecula(ruta_entrada: str, ruta_salida: str, expresion_filtro: str = "MW>200") -> None:
    if not shutil.which("obabel"):
        raise RuntimeError(
            "OpenBabel no está instalado o no se encuentra en el PATH.\n"
            "Instálalo con:  conda install -c conda-forge openbabel\n"
            "o bien:         apt install openbabel  (Linux)"
        )

    fmt_entrada = obtener_formato(ruta_entrada)
    fmt_salida = obtener_formato(ruta_salida)

    cmd = [
        "obabel",
        f"-i{fmt_entrada}", ruta_entrada,
        f"-o{fmt_salida}", "-O", ruta_salida,
        "--filter", expresion_filtro,
    ]

    resultado = subprocess.run(cmd, capture_output=True, text=True)

    if not os.path.exists(ruta_salida):
        raise RuntimeError(
            f"OpenBabel no generó el archivo de salida.\n"
            f"Comando: {' '.join(cmd)}\n"
            f"stderr: {resultado.stderr}"
        )

    if os.path.getsize(ruta_salida) == 0:
        print(f"Ninguna molécula cumple el filtro '{expresion_filtro}'.")
    else:
        print(f"Molécula(s) filtrada(s) con '{expresion_filtro}' guardada(s) en: {ruta_salida}")

    if resultado.stdout:
        print(resultado.stdout.strip())
    if resultado.stderr:
        print(f"[obabel info] {resultado.stderr.strip()}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('Uso: python filtroObabel.py <entrada> <salida> ["expresion_filtro"]', file=sys.stderr)
        sys.exit(1)

    expresion = sys.argv[3] if len(sys.argv) > 3 else "MW>200"

    try:
        filtrar_molecula(sys.argv[1], sys.argv[2], expresion)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
