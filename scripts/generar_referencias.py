"""
Genera los ligandos de referencia ligando_c ... ligando_f del banco de pruebas.

Por que existe: el banco ejecuta cada algoritmo subido contra moleculas de
referencia (app/banco_pruebas.py). Hasta la spec 013 cada tipo tenia sus
entradas fijas y bastaban dos ligandos --dos conformeros de la difenhidramina--
y un receptor. Ahora un algoritmo puede declarar hasta 6 entradas, y cada
entrada de tipo molecula necesita su propio ligando: con el mismo fichero
repetido, un algoritmo que compara o combina sus entradas no se probaria de
verdad.

Son moleculas pequenas y conocidas, para que la prueba tarde poco: paracetamol,
cafeina, ibuprofeno y acido salicilico. Se escriben como los dos ligandos que
ya habia: SDF con coordenadas 3D y sin hidrogenos explicitos.

Es determinista (semilla fija): repetirlo da los mismos ficheros, asi que solo
hace falta volver a lanzarlo si se cambia la lista.

Uso:
    python scripts/generar_referencias.py
"""
import os
import sys

from rdkit import Chem
from rdkit.Chem import AllChem

REFERENCIA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "referencia")

LIGANDOS = {
    "ligando_c": ("paracetamol", "CC(=O)Nc1ccc(O)cc1"),
    "ligando_d": ("cafeina", "Cn1c(=O)c2c(ncn2C)n(C)c1=O"),
    "ligando_e": ("ibuprofeno", "CC(C)Cc1ccc(cc1)C(C)C(=O)O"),
    "ligando_f": ("acido_salicilico", "OC(=O)c1ccccc1O"),
}

SEMILLA = 2026


def generar(nombre: str, smiles: str, ruta: str) -> None:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    if AllChem.EmbedMolecule(mol, randomSeed=SEMILLA) != 0:
        sys.exit(f"No se pudieron generar las coordenadas 3D de {nombre}.")
    AllChem.MMFFOptimizeMolecule(mol)
    mol = Chem.RemoveHs(mol)
    mol.SetProp("_Name", f"referencia_{nombre}")
    escritor = Chem.SDWriter(ruta)
    escritor.write(mol)
    escritor.close()


def main() -> None:
    for fichero, (nombre, smiles) in LIGANDOS.items():
        ruta = os.path.join(REFERENCIA, f"{fichero}.sdf")
        generar(nombre, smiles, ruta)
        print(f"{fichero}.sdf: {nombre}")


if __name__ == "__main__":
    main()
