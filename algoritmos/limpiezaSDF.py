# TIPO_ALGORITMO: preprocesado
"""
Limpieza de SDF con RDKit
Lee un SDF y vuelve a escribir solo las moléculas que RDKit pudo parsear
y sanear correctamente, descartando las que fallan (valencias incorrectas,
aromaticidad inconsistente, etc.).

Uso:
    python limpiezaSDF.py <archivo_entrada.sdf> <archivo_salida.sdf>

Parámetros aplicados:
    removeHs=False   Conserva los hidrógenos explícitos del SDF original
    sanitize=True    RDKit verifica y corrige valencia y aromaticidad
"""

import sys
import os
from rdkit import Chem


def limpiar_sdf(ruta_entrada: str, ruta_salida: str) -> None:
    supplier = Chem.SDMolSupplier(ruta_entrada, removeHs=False, sanitize=True)

    os.makedirs(os.path.dirname(ruta_salida) or ".", exist_ok=True)
    writer = Chem.SDWriter(ruta_salida)

    total = 0
    for mol in supplier:
        total += 1
        if mol is not None:
            writer.write(mol)

    escritas = writer.NumMols()
    writer.close()

    print(f"Moléculas leídas: {total}")
    print(f"Moléculas escritas: {escritas}")
    if escritas < total:
        print(f"Descartadas por RDKit (no parseables/sanitizables): {total - escritas}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python limpiezaSDF.py <entrada.sdf> <salida.sdf>", file=sys.stderr)
        sys.exit(1)

    try:
        limpiar_sdf(sys.argv[1], sys.argv[2])
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
