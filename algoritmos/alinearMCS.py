# TIPO_ALGORITMO: alineacion
"""
Alineación 3D por Máxima Subestructura Común (MCS)

Cuando dos moléculas no son similares globalmente pero comparten un núcleo
(scaffold), la alineación por MCS es más precisa que O3A porque ancla
la superposición en los átomos estructuralmente equivalentes.

Uso (con referencia):
    python alinearMCS.py <query> <referencia> <salida>

Uso (modo prueba, sin referencia):
    python alinearMCS.py <query> <salida>

Requisito mínimo: la MCS debe tener ≥ 5 átomos para que la alineación sea fiable.

Entrada:
    query      .sdf o .mol2
    referencia .sdf o .mol2
Salida:
    .sdf con la molécula query alineada sobre el scaffold común
"""

import sys
import os
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolAlign, rdFMCS


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


def alinear_mcs(ruta_query: str, ruta_ref: str, ruta_salida: str) -> float:
    """Alinea query sobre ref usando el scaffold de la MCS. Devuelve el RMSD."""
    ref   = cargar_molecula(ruta_ref)
    query = cargar_molecula(ruta_query)

    # FindMCS: busca la subestructura máxima común entre las dos moléculas
    # timeout=10 evita bloqueos en moléculas complejas
    resultado_mcs = rdFMCS.FindMCS(
        [ref, query],
        timeout=10,
        atomCompare=rdFMCS.AtomCompare.CompareElements,  # Coincidencia por elemento químico
        bondCompare=rdFMCS.BondCompare.CompareOrder,      # Coincidencia por orden de enlace
        completeRingsOnly=True,                           # Solo anillos completos (evita alineaciones incorrectas)
    )

    n_atomos_mcs = resultado_mcs.numAtoms
    print(f"MCS encontrada: {n_atomos_mcs} átomos  SMARTS: {resultado_mcs.smartsString}")

    if n_atomos_mcs < 5:
        raise ValueError(
            f"MCS demasiado pequeña ({n_atomos_mcs} átomos, mínimo 5). "
            "Las moléculas son demasiado distintas para alinear por MCS. "
            "Usa alinear3D.py (O3A) como alternativa."
        )

    # Obtener el patrón SMARTS y los mapeos de átomos
    mcs_mol     = Chem.MolFromSmarts(resultado_mcs.smartsString)
    ref_match   = ref.GetSubstructMatch(mcs_mol)
    query_match = query.GetSubstructMatch(mcs_mol)

    if not ref_match or not query_match:
        raise ValueError("No se encontraron los átomos de la MCS en las moléculas.")

    # atom_map: pares (átomo_query, átomo_ref) que se corresponden por MCS
    atom_map = list(zip(query_match, ref_match))

    # AlignMol: alineación rígida usando solo los átomos del scaffold como ancla
    rmsd = rdMolAlign.AlignMol(query, ref, atomMap=atom_map)

    print(f"RMSD MCS: {rmsd:.4f} Å", end="  ")
    if rmsd < 1.5:
        print("(superposición excelente)")
    elif rmsd < 3.0:
        print("(superposición aceptable)")
    else:
        print("(RMSD alto — revisar scaffold)")

    ext_salida = os.path.splitext(ruta_salida)[1].lower()
    if ext_salida not in (".sdf", ".mol"):
        ruta_salida = os.path.splitext(ruta_salida)[0] + ".sdf"

    writer = Chem.SDWriter(ruta_salida)
    writer.write(query)
    writer.close()

    print(f"Molécula alineada (MCS) guardada en: {ruta_salida}")
    return rmsd


if __name__ == "__main__":
    if len(sys.argv) == 3:
        ruta_query  = sys.argv[1]
        ruta_ref    = sys.argv[1]  # Sin referencia: alinea sobre sí misma
        ruta_salida = sys.argv[2]
        print("Modo single-input: se usa la misma molécula como referencia.")
    elif len(sys.argv) == 4:
        ruta_query  = sys.argv[1]
        ruta_ref    = sys.argv[2]
        ruta_salida = sys.argv[3]
    else:
        print("Uso: python alinearMCS.py <query> [<referencia>] <salida>", file=sys.stderr)
        sys.exit(1)

    try:
        alinear_mcs(ruta_query, ruta_ref, ruta_salida)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
