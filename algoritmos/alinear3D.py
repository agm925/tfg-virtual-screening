# TIPO_ALGORITMO: alineacion
"""
Alineación 3D rígida mediante Open3DAlign (O3A)

O3A busca la superposición óptima entre dos moléculas usando campos de distancias
atómicas sin necesidad de un mapeo explícito de átomos equivalentes.
Un RMSD < 1.5 Å indica buena superposición; > 3 Å indica poca similitud.

Uso (con referencia):
    python alinear3D.py <query> <referencia> <salida>

Uso (modo solo geometría, sin referencia externa):
    python alinear3D.py <query> <salida>
    En este modo la molécula se centra y se alinea sobre sí misma (PCA).

Entrada:
    query      .sdf o .mol2  (molécula a alinear)
    referencia .sdf o .mol2  (molécula de referencia, p. ej. ligando cristalográfico)
Salida:
    .sdf con la molécula query superpuesta sobre la referencia
"""

import sys
import os
from rdkit import Chem
from rdkit.Chem import rdMolAlign


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
        mol = _cargar_mol2(ruta, removeHs=False)
    elif ext in (".sdf", ".mol"):
        supplier = Chem.SDMolSupplier(ruta, removeHs=False)
        mol = next((m for m in supplier if m is not None), None)
    else:
        raise ValueError(f"Formato no soportado: {ext}. Usa .mol2 o .sdf")
    if mol is None:
        raise ValueError(f"No se pudo leer la molécula de {ruta}")
    return mol


def alinear_o3a(ruta_query: str, ruta_ref: str, ruta_salida: str) -> float:
    """Alinea query sobre ref usando O3A. Devuelve el RMSD final."""
    ref   = cargar_molecula(ruta_ref)
    query = cargar_molecula(ruta_query)

    # Eliminar H para la alineación (más estable numéricamente)
    ref_sin_h   = Chem.RemoveHs(ref)
    query_sin_h = Chem.RemoveHs(query)

    # GetO3A devuelve un objeto alineador que maximiza la superposición de campos atómicos
    alineador = rdMolAlign.GetO3A(query_sin_h, ref_sin_h)
    rmsd = alineador.Align()

    print(f"RMSD O3A: {rmsd:.4f} Å", end="  ")
    if rmsd < 1.5:
        print("(superposición excelente)")
    elif rmsd < 3.0:
        print("(superposición aceptable)")
    else:
        print("(RMSD alto — las moléculas pueden no compartir scaffold)")

    ext_salida = os.path.splitext(ruta_salida)[1].lower()
    if ext_salida not in (".sdf", ".mol"):
        ruta_salida = os.path.splitext(ruta_salida)[0] + ".sdf"

    writer = Chem.SDWriter(ruta_salida)
    writer.write(query_sin_h)
    writer.close()

    print(f"Molécula alineada guardada en: {ruta_salida}")
    return rmsd


if __name__ == "__main__":
    if len(sys.argv) == 3:
        # Modo de un solo archivo: usar la misma molécula como referencia (prueba de geometría)
        ruta_query = sys.argv[1]
        ruta_ref   = sys.argv[1]
        ruta_salida = sys.argv[2]
        print("Modo single-input: alineando la molécula sobre sí misma (solo recentrado).")
    elif len(sys.argv) == 4:
        ruta_query  = sys.argv[1]
        ruta_ref    = sys.argv[2]
        ruta_salida = sys.argv[3]
    else:
        print("Uso: python alinear3D.py <query> [<referencia>] <salida>", file=sys.stderr)
        sys.exit(1)

    try:
        alinear_o3a(ruta_query, ruta_ref, ruta_salida)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
