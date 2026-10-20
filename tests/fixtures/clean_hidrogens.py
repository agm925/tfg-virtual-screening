#!/usr/bin/env python3
"""
Elimina los hidrógenos de moléculas usando RDKit.

Formatos de entrada: .sdf, .mol, .mol2, .pdb, .smi/.smiles
Formatos de salida:  .sdf, .mol, .pdb, .smi/.smiles

Uso:
    python remove_hydrogens.py entrada.sdf                    # -> entrada_noH.sdf
    python remove_hydrogens.py entrada.mol2 -o salida.sdf
    python remove_hydrogens.py entrada.sdf --all              # elimina absolutamente todos los H
    python remove_hydrogens.py entrada.sdf --keep-coords      # (por defecto) conserva coordenadas 3D

Instalación:
    pip install rdkit
"""
import argparse
import os
import sys

from rdkit import Chem
from rdkit import RDLogger

RDLogger.DisableLog("rdApp.*")


def load_molecules(path):
    """Lee las moléculas del fichero y devuelve un generador de objetos Mol."""
    ext = os.path.splitext(path)[1].lower()

    if ext in (".sdf", ".sd"):
        # sanitize=False para no fallar al leer; se sanea después de quitar H
        for mol in Chem.SDMolSupplier(path, removeHs=False, sanitize=False):
            yield mol
    elif ext == ".mol":
        yield Chem.MolFromMolFile(path, removeHs=False, sanitize=False)
    elif ext == ".mol2":
        yield Chem.MolFromMol2File(path, removeHs=False, sanitize=False)
    elif ext == ".pdb":
        yield Chem.MolFromPDBFile(path, removeHs=False, sanitize=False)
    elif ext in (".smi", ".smiles", ".txt"):
        for mol in Chem.SmilesMolSupplier(path, titleLine=False, sanitize=False):
            yield mol
    else:
        raise ValueError(f"Formato no soportado: {ext}")


def strip_hydrogens(mol, remove_all=False):
    """
    Elimina hidrógenos de una molécula.

    remove_all=False -> Chem.RemoveHs: quita los H 'normales' pero conserva los
                        que son necesarios (isótopos, H puente, H en estereocentros
                        definidos solo por ellos, etc.).
    remove_all=True  -> Chem.RemoveAllHs: quita todos sin excepción.
    """
    if mol is None:
        return None
    try:
        if remove_all:
            mol = Chem.RemoveAllHs(mol, sanitize=False)
        else:
            mol = Chem.RemoveHs(mol, sanitize=False)
        Chem.SanitizeMol(mol)
        return mol
    except Exception as e:
        print(f"  [!] No se pudo procesar la molécula: {e}", file=sys.stderr)
        return None


def write_molecules(mols, path):
    ext = os.path.splitext(path)[1].lower()

    if ext in (".sdf", ".sd"):
        writer = Chem.SDWriter(path)
        for m in mols:
            writer.write(m)
        writer.close()
    elif ext in (".smi", ".smiles"):
        with open(path, "w") as f:
            for m in mols:
                name = m.GetProp("_Name") if m.HasProp("_Name") else ""
                f.write(f"{Chem.MolToSmiles(m)} {name}\n")
    elif ext == ".mol":
        Chem.MolToMolFile(mols[0], path)
    elif ext == ".pdb":
        Chem.MolToPDBFile(mols[0], path)
    else:
        raise ValueError(f"Formato de salida no soportado: {ext}")


def main():
    parser = argparse.ArgumentParser(description="Elimina hidrógenos de moléculas (RDKit).")
    parser.add_argument("input", help="Fichero de entrada")
    parser.add_argument("-o", "--output", help="Fichero de salida (por defecto: <entrada>_noH.<ext>)")
    parser.add_argument("--all", action="store_true",
                        help="Elimina TODOS los hidrógenos (RemoveAllHs)")
    args = parser.parse_args()

    out = args.output
    if out is None:
        base, ext = os.path.splitext(args.input)
        if ext.lower() == ".mol2":
            ext = ".sdf"  # RDKit no escribe mol2
        out = f"{base}_noH{ext}"

    results, total, failed = [], 0, 0
    for mol in load_molecules(args.input):
        total += 1
        n_before = mol.GetNumAtoms() if mol is not None else 0
        new = strip_hydrogens(mol, remove_all=args.all)
        if new is None:
            failed += 1
            continue
        print(f"Molécula {total}: {n_before} -> {new.GetNumAtoms()} átomos")
        results.append(new)

    if not results:
        sys.exit("No se obtuvo ninguna molécula válida.")

    write_molecules(results, out)
    print(f"\nProcesadas: {total} | correctas: {len(results)} | fallidas: {failed}")
    print(f"Guardado en: {out}")


if __name__ == "__main__":
    main()