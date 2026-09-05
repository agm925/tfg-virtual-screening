# TIPO_ALGORITMO: preprocesado
"""
Generación de coordenadas 3D con RDKit — ETKDGv3 + MMFF94s

El método ETKDGv3 usa distancias experimentales de cristalografía para generar
conformaciones de mayor calidad que los métodos puramente geométricos.
Tras la generación se minimiza la geometría con el campo de fuerzas MMFF94s.

Uso:
    python gen3dRDKit.py <archivo_entrada> <archivo_salida>

Entrada: .sdf, .mol2 o .smi (la molécula puede carecer de coordenadas 3D)
Salida:  .sdf con coordenadas 3D optimizadas e hidrógenos explícitos
"""

import sys
import os
from rdkit import Chem
from rdkit.Chem import AllChem


def cargar_molecula(ruta: str):
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".mol2":
        mol = Chem.MolFromMol2File(ruta, removeHs=False)
    elif ext in (".sdf", ".mol"):
        supplier = Chem.SDMolSupplier(ruta, removeHs=False)
        mol = next((m for m in supplier if m is not None), None)
    elif ext == ".smi":
        with open(ruta, "r", encoding="utf-8") as f:
            primera_linea = f.readline().strip()
        smiles = primera_linea.split()[0] if primera_linea else ""
        mol = Chem.MolFromSmiles(smiles) if smiles else None
    else:
        raise ValueError(f"Formato no soportado: {ext}. Usa .mol2, .sdf o .smi")
    if mol is None:
        raise ValueError(f"No se pudo leer la molécula de {ruta}")
    return mol


def generar_3d(ruta_entrada: str, ruta_salida: str) -> None:
    mol = cargar_molecula(ruta_entrada)

    # Añadir hidrógenos explícitos (obligatorio antes de EmbedMolecule)
    mol = Chem.AddHs(mol)

    # Parámetros ETKDGv3: usa distancias experimentales de cristalografía
    params = AllChem.ETKDGv3()
    params.randomSeed = 42  # Semilla para reproducibilidad

    resultado_embed = AllChem.EmbedMolecule(mol, params)
    if resultado_embed == -1:
        raise ValueError(
            "ETKDGv3 no pudo generar una conformación 3D. "
            "Comprueba que la estructura SMILES/mol2 sea válida."
        )

    # Minimización de geometría con MMFF94s
    # mmffVariant='MMFF94s' es la variante estereoelectrónica (más precisa para chirales)
    resultado_min = AllChem.MMFFOptimizeMolecule(mol, mmffVariant="MMFF94s")
    if resultado_min == -1:
        print("Advertencia: MMFF94s no convergió. Se usa la conformación sin minimizar.",
              file=sys.stderr)

    # Determinar extensión de salida
    ext_salida = os.path.splitext(ruta_salida)[1].lower()
    if ext_salida not in (".sdf", ".mol"):
        ruta_salida = os.path.splitext(ruta_salida)[0] + ".sdf"

    writer = Chem.SDWriter(ruta_salida)
    writer.write(mol)
    writer.close()

    n_atomos = mol.GetNumAtoms()
    print(f"Conformación 3D generada: {n_atomos} átomos → {ruta_salida}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python gen3dRDKit.py <entrada> <salida>", file=sys.stderr)
        sys.exit(1)

    try:
        generar_3d(sys.argv[1], sys.argv[2])
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
