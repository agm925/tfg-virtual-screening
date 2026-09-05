# TIPO_ALGORITMO: docking
"""
Docking molecular con Smina (variante mejorada de AutoDock Vina)

Soporta tres formas de definir la caja de búsqueda:
    auto        Autobox sobre el propio ligando de entrada (por defecto).
                Útil para redocking de validación: el ligando cristalográfico
                se redockea sobre sí mismo y luego se compara el RMSD con
                rmsdConformaciones.py (sección 2.6).
    referencia  Autobox sobre un ligando de referencia distinto (p. ej. el
                ligando cristalográfico del complejo) vía --referencia.
    manual      Caja definida a mano con --center_x/y/z y --size_x/y/z.

Uso:
    python dockingSmina.py <ligando> <receptor> <archivo_salida> [opciones]

Opciones:
    --referencia <archivo>           Ligando de referencia para autobox (modo "referencia")
    --center_x/--center_y/--center_z <float>   Centro de la caja manual (activa modo "manual")
    --size_x/--size_y/--size_z <float>         Tamaño de la caja manual (Å)
    --autobox_add <float>             Margen en Å para los modos autobox (por defecto 8)
    --exhaustiveness <int>            Profundidad de búsqueda (por defecto 8)
    --num_modes <int>                 Número máximo de poses (por defecto 5)
    --scoring <vina|vinardo|dkoes_fast|dkoes_scoring>   Función de scoring (por defecto vinardo)

Entrada:
    ligando    .sdf o .pdbqt  (molécula a acoplar)
    receptor   .pdbqt         (proteína preparada con cargas y H polares)
Salida:
    .sdf con todas las poses generadas
    JSON con las energías de cada pose (mismo nombre, extensión .json)

Instalar Smina:
    conda install -c conda-forge smina
    o descarga binarios desde: https://github.com/mwojcikowski/smina
"""

import sys
import os
import re
import json
import subprocess
import shutil


def verificar_smina() -> None:
    if not shutil.which("smina"):
        raise RuntimeError(
            "Smina no está instalado o no se encuentra en el PATH.\n"
            "Instálalo con:  conda install -c conda-forge smina\n"
            "o descarga el binario desde https://github.com/mwojcikowski/smina"
        )


def parsear_energias(log: str) -> list:
    """Extrae las energías de afinidad del output de Smina."""
    energias = []
    for linea in log.splitlines():
        # Líneas con formato: "   1         -8.4      0.000      0.000"
        match = re.match(r"\s+(\d+)\s+([-\d.]+)\s+[-\d.]+\s+[-\d.]+", linea)
        if match:
            energias.append({
                "pose": int(match.group(1)),
                "afinidad_kcal_mol": float(match.group(2)),
            })
    return energias


def ejecutar_docking(
    ruta_ligando: str,
    ruta_receptor: str,
    ruta_salida: str,
    exhaustiveness: int = 8,
    num_modes: int = 5,
    autobox_add: float = 8.0,
    scoring: str = "vinardo",
    ruta_referencia: str = None,
    caja_manual: dict = None,
) -> dict:
    """
    caja_manual, si se indica, debe ser un dict con center_x/y/z y size_x/y/z
    y tiene prioridad sobre ruta_referencia (caja manual vs. autobox).
    Si no se indica ni caja_manual ni ruta_referencia, se usa autobox sobre
    el propio ligando (modo "auto", válido para redocking de validación).
    """
    verificar_smina()

    ext_salida = os.path.splitext(ruta_salida)[1].lower()
    if ext_salida not in (".sdf", ".pdbqt"):
        ruta_salida = os.path.splitext(ruta_salida)[0] + ".sdf"

    ruta_log  = os.path.splitext(ruta_salida)[0] + "_smina.log"
    ruta_json = os.path.splitext(ruta_salida)[0] + "_energias.json"

    cmd = [
        "smina",
        "--receptor",        ruta_receptor,
        "--ligand",          ruta_ligando,
        "--out",             ruta_salida,
        "--log",             ruta_log,
        "--scoring",         scoring,
        "--exhaustiveness",  str(exhaustiveness),
        "--num_modes",       str(num_modes),
    ]

    if caja_manual:
        cmd += [
            "--center_x", str(caja_manual["center_x"]),
            "--center_y", str(caja_manual["center_y"]),
            "--center_z", str(caja_manual["center_z"]),
            "--size_x",   str(caja_manual["size_x"]),
            "--size_y",   str(caja_manual["size_y"]),
            "--size_z",   str(caja_manual["size_z"]),
        ]
    else:
        # Autobox: sobre la referencia cristalográfica si se da, si no sobre el propio ligando
        referencia = ruta_referencia or ruta_ligando
        cmd += ["--autobox_ligand", referencia, "--autobox_add", str(autobox_add)]

    print(f"Ejecutando docking: {' '.join(cmd)}")
    resultado = subprocess.run(cmd, capture_output=True, text=True)

    log_completo = resultado.stdout + resultado.stderr

    if not os.path.exists(ruta_salida) and resultado.returncode != 0:
        raise RuntimeError(
            f"Smina falló (código {resultado.returncode}).\n"
            f"stderr: {resultado.stderr[:500]}"
        )

    energias = parsear_energias(log_completo)

    mejor_energia = energias[0]["afinidad_kcal_mol"] if energias else None
    print(f"\nPoses generadas: {len(energias)}")
    for pose in energias:
        print(f"  Pose {pose['pose']}: {pose['afinidad_kcal_mol']} kcal/mol")
    if mejor_energia is not None:
        umbral = "✓ Hit potencial (≤ -7.0)" if mejor_energia <= -7.0 else "— Por encima del umbral típico"
        print(f"\nMejor afinidad: {mejor_energia} kcal/mol  {umbral}")

    resultado_json = {
        "exito":           True,
        "poses_generadas": len(energias),
        "mejor_afinidad":  mejor_energia,
        "energias":        energias,
        "archivo_poses":   ruta_salida,
        "scoring":         scoring,
        "exhaustiveness":  exhaustiveness,
    }

    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(resultado_json, f, indent=2, ensure_ascii=False)

    print(f"\nPoses guardadas en: {ruta_salida}")
    print(f"Energías guardadas en: {ruta_json}")

    return resultado_json


def _parsear_argv_opcionales(argv: list) -> dict:
    """Parsea flags --clave valor de la forma --center_x 10.5 en un dict."""
    opciones = {}
    i = 0
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv):
            opciones[argv[i][2:]] = argv[i + 1]
            i += 2
        else:
            i += 1
    return opciones


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Uso: python dockingSmina.py <ligando> <receptor> <salida_poses> [opciones]",
              file=sys.stderr)
        sys.exit(1)

    opc = _parsear_argv_opcionales(sys.argv[4:])

    campos_caja = ("center_x", "center_y", "center_z", "size_x", "size_y", "size_z")
    caja_manual = (
        {campo: float(opc[campo]) for campo in campos_caja}
        if all(campo in opc for campo in campos_caja) else None
    )

    try:
        ejecutar_docking(
            sys.argv[1], sys.argv[2], sys.argv[3],
            exhaustiveness=int(opc.get("exhaustiveness", 8)),
            num_modes=int(opc.get("num_modes", 5)),
            autobox_add=float(opc.get("autobox_add", 8.0)),
            scoring=opc.get("scoring", "vinardo"),
            ruta_referencia=opc.get("referencia"),
            caja_manual=caja_manual,
        )
    except Exception as e:
        error = {"exito": False, "error": str(e)}
        print(f"Error: {e}", file=sys.stderr)
        try:
            ruta_json = os.path.splitext(sys.argv[3])[0] + "_energias.json"
            with open(ruta_json, "w") as f:
                json.dump(error, f, indent=2)
        except Exception:
            pass
        sys.exit(1)
