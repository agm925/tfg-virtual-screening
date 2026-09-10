# TIPO_ALGORITMO: comparacion
"""
Cálculo de RMSD entre dos conformaciones de moléculas

Usa GetBestRMS, que prueba todas las simetrías del ligando y devuelve el RMSD
mínimo (evita penalizar grupos equivalentes como CH3 o anillos simétricos).

Criterio estándar de éxito en redocking: RMSD < 2.0 Å respecto a la pose
cristalográfica indica que el protocolo reprodujo correctamente la pose experimental.

Uso:
    python rmsdConformaciones.py <mol_referencia> <mol_query> <archivo_salida_json>

Entrada:
    mol_referencia  .sdf o .mol2  (p. ej. pose cristalográfica)
    mol_query       .sdf o .mol2  (p. ej. pose de docking)
Salida:
    JSON con el valor RMSD y la interpretación del resultado
"""

import sys
import os
import json
from rdkit import Chem
from rdkit.Chem import AllChem


def _cargar_mol2(ruta, removeHs=True):
    """
    Carga un .mol2 tolerando los que RDKit no consigue kekulizar.

    Los .mol2 que produce Open Babel a partir de un SDF de ChEMBL declaran
    enlaces aromaticos que RDKit no sabe kekulizar ("Can't kekulize mol"), de
    modo que MolFromMol2File devuelve None con los valores por defecto y la
    molecula se descarta como invalida. Sobre una biblioteca de mil compuestos
    reales, eso suponia perder el 27 % de las entradas.

    La solucion es leerla sin sanear y aplicar despues todas las
    comprobaciones MENOS la kekulizacion, que es la unica que falla. Los
    descriptores que calculan estos algoritmos --peso molecular, LogP, TPSA,
    fingerprints-- no dependen de ella.

    (Esta funcion se repite en cada algoritmo en lugar de compartirse en un
    modulo comun porque SlurmExecutor sube al cluster unicamente el fichero
    del algoritmo: un import de un modulo hermano fallaria en remoto.)
    """
    mol = Chem.MolFromMol2File(ruta, removeHs=removeHs)
    if mol is not None:
        return mol
    mol = Chem.MolFromMol2File(ruta, removeHs=removeHs, sanitize=False)
    if mol is None:
        return None
    try:
        Chem.SanitizeMol(
            mol,
            Chem.SanitizeFlags.SANITIZE_ALL ^ Chem.SanitizeFlags.SANITIZE_KEKULIZE,
        )
    except Exception:
        return None
    return mol



def cargar_molecula(ruta: str):
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".mol2":
        mol = _cargar_mol2(ruta, removeHs=True)
    elif ext in (".sdf", ".mol"):
        supplier = Chem.SDMolSupplier(ruta, removeHs=True)
        mol = next((m for m in supplier if m is not None), None)
    else:
        raise ValueError(f"Formato no soportado: {ext}")
    if mol is None:
        raise ValueError(f"No se pudo leer la molécula de {ruta}")
    return mol


def calcular_rmsd(ruta_ref: str, ruta_query: str, ruta_salida: str) -> dict:
    mol_ref   = cargar_molecula(ruta_ref)
    mol_query = cargar_molecula(ruta_query)

    # GetBestRMS prueba todas las permutaciones simétricas y devuelve el mínimo
    try:
        rmsd = AllChem.GetBestRMS(mol_ref, mol_query)
    except Exception as e:
        raise ValueError(
            f"Error al calcular RMSD. Asegúrate de que ambas moléculas son la misma "
            f"estructura con diferente conformación: {e}"
        )

    if rmsd < 1.0:
        interpretacion = "Excelente — poses prácticamente idénticas"
    elif rmsd < 2.0:
        interpretacion = "Buena — dentro del criterio estándar de redocking (< 2 Å)"
    elif rmsd < 3.0:
        interpretacion = "Moderada — poses similares pero con diferencias notables"
    else:
        interpretacion = "Alta — las poses son significativamente distintas"

    resultado = {
        "rmsd_angstroms": round(rmsd, 4),
        "criterio_redocking_superado": rmsd < 2.0,
        "interpretacion": interpretacion,
        "archivo_referencia": os.path.basename(ruta_ref),
        "archivo_query":      os.path.basename(ruta_query),
        "exito": True,
    }

    print(f"RMSD: {rmsd:.4f} Å — {interpretacion}")

    os.makedirs(os.path.dirname(ruta_salida) or ".", exist_ok=True)
    with open(ruta_salida, "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)

    print(f"Resultado guardado en: {ruta_salida}")
    return resultado


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Uso: python rmsdConformaciones.py <referencia> <query> <salida_json>",
              file=sys.stderr)
        sys.exit(1)

    try:
        calcular_rmsd(sys.argv[1], sys.argv[2], sys.argv[3])
    except Exception as e:
        error = {"exito": False, "error": str(e)}
        print(f"Error: {e}", file=sys.stderr)
        try:
            with open(sys.argv[3], "w") as f:
                json.dump(error, f, indent=2)
        except Exception:
            pass
        sys.exit(1)
