#!/usr/bin/env python
# TIPO_ALGORITMO: comparacion
"""
Algoritmo de Similitud Química - Tanimoto
Compara dos moléculas usando fingerprints de Tanimoto (RDKit)

Uso:
    python similaridadTanimoto.py <archivo_mol_1> <archivo_mol_2> <archivo_salida>

Entrada:
    - archivo_mol_1: Primer archivo .mol2 o .sdf
    - archivo_mol_2: Segundo archivo .mol2 o .sdf
    - archivo_salida: Archivo JSON con resultado de similitud

Salida:
    JSON con:
    {
        "similitud": 0.85,
        "num_atomos_mol1": 25,
        "num_atomos_mol2": 23,
        "fingerprint_molweight_mol1": X,
        "fingerprint_molweight_mol2": Y
    }
"""

import sys
import json
import os
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors

def cargar_molecula(ruta_archivo):
    """Carga una molécula desde un archivo .mol2 o .sdf"""
    try:
        if ruta_archivo.endswith('.mol2'):
            mol = Chem.MolFromMol2File(ruta_archivo, removeHs=False)
        elif ruta_archivo.endswith('.sdf'):
            suppl = Chem.SDMolSupplier(ruta_archivo, removeHs=False)
            mol = suppl[0]
        else:
            raise ValueError(f"Formato no soportado: {ruta_archivo}")
        
        if mol is None:
            raise ValueError(f"No se pudo cargar la molécula desde {ruta_archivo}")
        
        return mol
    except Exception as e:
        raise Exception(f"Error cargando {ruta_archivo}: {str(e)}")


def calcular_fingerprint_tanimoto(mol1, mol2):
    """Calcula similitud Tanimoto entre dos moléculas usando fingerprints"""
    try:
        # Generar fingerprints Morgan (parecido a ECFP4)
        fp1 = AllChem.GetMorganFingerprintAsBitVect(mol1, 2, nBits=1024)
        fp2 = AllChem.GetMorganFingerprintAsBitVect(mol2, 2, nBits=1024)
        
        # Calcular coeficiente Tanimoto (similitud 0-1)
        similitud = DataStructs.TanimotoSimilarity(fp1, fp2)
        
        return similitud
    except Exception as e:
        raise Exception(f"Error calculando fingerprint: {str(e)}")


def calcular_similitud_tanimoto(archivo_mol1, archivo_mol2):
    """Función principal que calcula similitud entre dos moléculas"""
    try:
        # Cargar moléculas
        mol1 = cargar_molecula(archivo_mol1)
        mol2 = cargar_molecula(archivo_mol2)
        
        # Calcular fingerprints
        from rdkit.DataStructs import TanimotoSimilarity
        fp1 = AllChem.GetMorganFingerprintAsBitVect(mol1, 2, nBits=1024)
        fp2 = AllChem.GetMorganFingerprintAsBitVect(mol2, 2, nBits=1024)
        similitud = TanimotoSimilarity(fp1, fp2)
        
        # Obtener propiedades
        num_atomos_mol1 = mol1.GetNumAtoms()
        num_atomos_mol2 = mol2.GetNumAtoms()
        peso_mol1 = Descriptors.MolWt(mol1)
        peso_mol2 = Descriptors.MolWt(mol2)
        
        resultado = {
            "similitud": round(similitud, 4),
            "num_atomos_mol1": num_atomos_mol1,
            "num_atomos_mol2": num_atomos_mol2,
            "peso_molecular_mol1": round(peso_mol1, 2),
            "peso_molecular_mol2": round(peso_mol2, 2),
            "exito": True
        }
        
        return resultado
        
    except Exception as e:
        return {
            "exito": False,
            "error": str(e)
        }


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(json.dumps({
            "exito": False,
            "error": "Uso: python similaridadTanimoto.py <archivo_mol_1> <archivo_mol_2> <archivo_salida>"
        }))
        sys.exit(1)
    
    archivo_mol1 = sys.argv[1]
    archivo_mol2 = sys.argv[2]
    archivo_salida = sys.argv[3]
    
    # Calcular similitud
    resultado = calcular_similitud_tanimoto(archivo_mol1, archivo_mol2)
    
    # Guardar resultado en JSON
    try:
        os.makedirs(os.path.dirname(archivo_salida) or ".", exist_ok=True)
        with open(archivo_salida, 'w') as f:
            json.dump(resultado, f, indent=2)
        print(f"Resultado guardado en {archivo_salida}")
        sys.exit(0 if resultado.get("exito", False) else 1)
    except Exception as e:
        print(json.dumps({
            "exito": False,
            "error": f"Error guardando resultado: {str(e)}"
        }))
        sys.exit(1)
