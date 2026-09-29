# TIPO_ALGORITMO: preprocesado
"""
Filtro de Lipinski — Regla de los 5 (Ro5)
Calcula propiedades fisicoquímicas y valida la druglikeness de cada molécula
de un archivo. Si el SDF contiene una biblioteca (varias moléculas), se
procesan todas, igual que recorrer un SDMolSupplier con un bucle "for".

Uso:
    python filtroLipinski.py <archivo_entrada> <archivo_salida_json>

Entrada: .mol2 (1 molécula) o .sdf/.mol (1 o varias moléculas)
Salida:  JSON con la lista de propiedades y el resultado PASS/FAIL de cada una

Propiedades calculadas:
    MW    Peso molecular promedio      (≤ 500 Da)
    LogP  Coeficiente de partición     (≤ 5)
    HBD   Donadores de enlace H        (≤ 5)
    HBA   Aceptores de enlace H        (≤ 10)
    TPSA  Área superficial polar topológica (informativa)

Una molécula pasa si tiene ≤ 1 violación (margen de Lipinski flexible).
"""

import sys
import os
import json
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors, Crippen


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



def cargar_moleculas(ruta: str) -> list:
    """Devuelve la lista de moléculas válidas del archivo (puede tener 1 o varias)."""
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".mol2":
        mol = _cargar_mol2(ruta, removeHs=True)
        moleculas = [mol] if mol is not None else []
    elif ext in (".sdf", ".mol"):
        supplier = Chem.SDMolSupplier(ruta, removeHs=True)
        moleculas = [m for m in supplier if m is not None]  # Salta las que RDKit no puede parsear
    else:
        raise ValueError(f"Formato no soportado: {ext}. Usa .mol2 o .sdf")

    if not moleculas:
        raise ValueError(f"No se pudo cargar ninguna molécula válida desde {ruta}")
    return moleculas


def calcular_propiedades_lipinski(mol, nombre: str = "molecula") -> dict:
    # Peso molecular PROMEDIO, no la masa monoisotopica (ExactMolWt), que
    # es lo que habia antes. La regla de Lipinski se enuncia sobre el peso
    # promedio --igual que lo publican ChEMBL y PubChem-- y la masa exacta
    # siempre sale por debajo: para la aspirina, 180,04 frente a 180,16.
    # La diferencia es del 0,1 %, pero va toda en el mismo sentido, asi que
    # en el umbral de 500 Da el filtro dejaba pasar compuestos que la regla
    # descarta. Ademas asi coincide con similaridadTanimoto.py, que ya
    # usaba Descriptors.MolWt: dos algoritmos del mismo catalogo daban
    # pesos distintos para la misma molecula.
    mw   = Descriptors.MolWt(mol)
    logp = Crippen.MolLogP(mol)
    hbd  = rdMolDescriptors.CalcNumHBD(mol)
    hba  = rdMolDescriptors.CalcNumHBA(mol)
    tpsa = rdMolDescriptors.CalcTPSA(mol)
    rot  = rdMolDescriptors.CalcNumRotatableBonds(mol)

    violaciones = sum([
        mw   > 500,
        logp > 5,
        hbd  > 5,
        hba  > 10,
    ])

    return {
        "nombre":      nombre,
        "MW":          round(mw,   2),
        "LogP":        round(logp, 3),
        "HBD":         hbd,
        "HBA":         hba,
        "TPSA":        round(tpsa, 2),
        "RotBonds":    rot,
        "violaciones": violaciones,
        "estado":      "PASS" if violaciones <= 1 else "FAIL",
        "detalle": {
            "MW_ok":   mw   <= 500,
            "LogP_ok": logp <= 5,
            "HBD_ok":  hbd  <= 5,
            "HBA_ok":  hba  <= 10,
        },
        "exito": True,
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python filtroLipinski.py <entrada> <salida_json>", file=sys.stderr)
        sys.exit(1)

    ruta_entrada = sys.argv[1]
    ruta_salida  = sys.argv[2]

    try:
        moleculas    = cargar_moleculas(ruta_entrada)
        base         = os.path.splitext(os.path.basename(ruta_entrada))[0]
        resultados   = []

        for i, mol in enumerate(moleculas):
            nombre = mol.GetProp("_Name") if mol.HasProp("_Name") and mol.GetProp("_Name") else f"{base}_{i + 1}"
            resultado = calcular_propiedades_lipinski(mol, nombre)
            resultados.append(resultado)

            # Mostrar resumen en consola
            print(
                f"{nombre}: MW={resultado['MW']}, LogP={resultado['LogP']}, "
                f"HBD={resultado['HBD']}, HBA={resultado['HBA']}, "
                f"TPSA={resultado['TPSA']} → {resultado['estado']}"
            )
            if resultado["estado"] == "FAIL":
                print(f"  Violaciones ({resultado['violaciones']}): "
                      + ", ".join(k for k, v in resultado["detalle"].items() if not v))

        salida = {
            "exito":    True,
            "total":    len(resultados),
            "pass":     sum(1 for r in resultados if r["estado"] == "PASS"),
            "fail":     sum(1 for r in resultados if r["estado"] == "FAIL"),
            "moleculas": resultados,
        }

        os.makedirs(os.path.dirname(ruta_salida) or ".", exist_ok=True)
        with open(ruta_salida, "w", encoding="utf-8") as f:
            json.dump(salida, f, indent=2, ensure_ascii=False)

        print(f"Resultado guardado en: {ruta_salida} ({salida['pass']} PASS / {salida['fail']} FAIL de {salida['total']})")
        sys.exit(0)

    except Exception as e:
        error = {"exito": False, "error": str(e)}
        print(f"Error: {e}", file=sys.stderr)
        try:
            with open(ruta_salida, "w") as f:
                json.dump(error, f, indent=2)
        except Exception:
            pass
        sys.exit(1)
