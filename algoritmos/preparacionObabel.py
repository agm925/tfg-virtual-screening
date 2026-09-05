# TIPO_ALGORITMO: preprocesado
"""
Preparación de moléculas con OpenBabel
Añade hidrógenos a pH 7.4, genera coordenadas 3D y centra la molécula.

Uso (molécula individual):
    python preparacionObabel.py <archivo_entrada> <archivo_salida>

Uso (procesamiento por lotes):
    python preparacionObabel.py <archivo_entrada> <archivo_salida> --batch

    En modo batch el archivo de salida actúa como patrón: para "molecula.mol2"
    OpenBabel genera "molecula1.mol2", "molecula2.mol2", etc.

Uso (conversión pura, sin preparación):
    python preparacionObabel.py <archivo_entrada> <archivo_salida> --sin-h --sin-3d --sin-center

    Con los tres flags desactivados, el script actúa como un simple
    conversor de formatos (equivalente a "obabel -i ... -o ... -O ...").

Parámetros aplicados (activos por defecto, desactivables con los flags --sin-*):
    --sin-h        Omite "-h --pH 7.4" (no añade hidrógenos explícitos)
    --sin-3d       Omite "--gen3d" (no genera coordenadas 3D)
    --sin-center   Omite "--center" (no centra la molécula en el origen)
    --partialcharge gasteiger  (solo cuando la salida es PDBQT)
    -m             Divide el archivo en moléculas individuales (solo en modo batch)
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
    return equivalencias.get(ext, ext) or "mol2"


def preparar_molecula(
    ruta_entrada: str,
    ruta_salida: str,
    batch: bool = False,
    anadir_h: bool = True,
    gen3d: bool = True,
    center: bool = True,
) -> None:
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
    ]

    if anadir_h:
        cmd += ["-h", "--pH", "7.4"]   # Hidrógenos explícitos a pH fisiológico
    if gen3d:
        cmd.append("--gen3d")          # Coordenadas 3D (MMFF94) si no existen
    if center:
        cmd.append("--center")         # Trasladar centroide al origen

    if fmt_salida == "pdbqt":
        cmd += ["--partialcharge", "gasteiger", "-p", "7.4"]

    if batch:
        cmd.append("-m")

    resultado = subprocess.run(cmd, capture_output=True, text=True)

    if batch:
        # En modo batch OpenBabel genera varios archivos; verificamos que exista al menos uno
        directorio = os.path.dirname(ruta_salida) or "."
        base = os.path.splitext(os.path.basename(ruta_salida))[0]
        ext = os.path.splitext(ruta_salida)[1]
        archivos_generados = [
            f for f in os.listdir(directorio)
            if f.startswith(base) and f.endswith(ext)
        ]
        if not archivos_generados:
            raise RuntimeError(
                f"OpenBabel no generó ningún archivo de salida en modo batch.\n"
                f"Comando: {' '.join(cmd)}\n"
                f"stderr: {resultado.stderr}"
            )
        print(f"{len(archivos_generados)} moléculas generadas en: {directorio}")
    else:
        if not os.path.exists(ruta_salida):
            raise RuntimeError(
                f"OpenBabel no generó el archivo de salida.\n"
                f"Comando: {' '.join(cmd)}\n"
                f"stderr: {resultado.stderr}"
            )
        print(f"Molécula preparada guardada en: {ruta_salida}")

    if resultado.stdout:
        print(resultado.stdout.strip())
    if resultado.stderr:
        print(f"[obabel info] {resultado.stderr.strip()}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Uso: python preparacionObabel.py <entrada> <salida> "
            "[--batch] [--sin-h] [--sin-3d] [--sin-center]",
            file=sys.stderr,
        )
        sys.exit(1)

    batch_mode = "--batch" in sys.argv
    anadir_h   = "--sin-h" not in sys.argv
    gen3d      = "--sin-3d" not in sys.argv
    center     = "--sin-center" not in sys.argv

    try:
        preparar_molecula(
            sys.argv[1], sys.argv[2],
            batch=batch_mode, anadir_h=anadir_h, gen3d=gen3d, center=center,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
