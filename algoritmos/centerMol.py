# TIPO_ALGORITMO: alineacion
#
# prePCA.py
# Example code demonstrating PCA-based preprocessing for molecules
#
# This code, or one similar, should be run on molecules prior to
# processing with PAPER to do inertial overlay
# 
# Modifies each of its input files (specified on the command line)
# reorienting each molecule along its principal component axes
# Depends on the OpenEye Python toolkits
#  
# Author: Imran Haque, 2009
# Copyright 2009, Stanford University
#
# This file is licensed under the terms of the GPL. Please see
# the COPYING file in the accompanying source distribution for
# full license terms.


import sys
import os
import numpy as np
from numpy.linalg import svd, det
from rdkit import Chem

def pcaProjectMol(mol):
    """Reorient a molecule along its principal axes to reduce the size of the bounding box"""
    conf = mol.GetConformer()
    n_atoms = mol.GetNumAtoms()
    x = np.array([list(conf.GetAtomPosition(i)) for i in range(n_atoms)])
    (u, s, vh) = svd(x)
    print("S:", s)
    # Check for negative determinant to avoid reflection
    if det(vh) < 0:
        vh = -vh

    for i in range(n_atoms):
        coords = np.array(conf.GetAtomPosition(i))
        new_coords = vh @ coords
        conf.SetAtomPosition(i, new_coords.tolist())

def centerMol(mol):
    conf = mol.GetConformer()
    n_atoms = mol.GetNumAtoms()
    centroid = np.zeros(3)
    for i in range(n_atoms):
        centroid += np.array(conf.GetAtomPosition(i))
    centroid /= n_atoms

    for i in range(n_atoms):
        coords = np.array(conf.GetAtomPosition(i))
        new_coords = coords - centroid
        conf.SetAtomPosition(i, new_coords.tolist())

def read_molecule(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext in ('.sdf', '.mol'):
        mol = Chem.MolFromMolFile(filepath, removeHs=False, sanitize=False)
    elif ext == '.mol2':
        mol = Chem.MolFromMol2File(filepath, removeHs=False, sanitize=False)
    else:
        raise ValueError(f"Unsupported file format: {ext}")

    if mol is not None:
        try:
            Chem.SanitizeMol(mol)
        except Exception:
            try:
                # Skip valence/property checks (handles C.Cat and similar exotic types)
                Chem.SanitizeMol(
                    mol,
                    Chem.SanitizeFlags.SANITIZE_ALL ^ Chem.SanitizeFlags.SANITIZE_PROPERTIES
                )
            except Exception:
                try:
                    # Also skip aromaticity (handles non-ring aromatic atoms)
                    Chem.SanitizeMol(
                        mol,
                        Chem.SanitizeFlags.SANITIZE_ALL
                        ^ Chem.SanitizeFlags.SANITIZE_PROPERTIES
                        ^ Chem.SanitizeFlags.SANITIZE_SETAROMATICITY,
                    )
                except Exception as e3:
                    print(f"Warning: sanitization failed for {filepath}: {e3}", file=sys.stderr)

    return mol


def write_mol2_with_new_coords(source_mol2, out_path, mol):
    """
    Escribe un fichero mol2 copiando el original y reemplazando solo las
    columnas de coordenadas (x, y, z) con las del conformer de `mol`.
    Preserva los tipos de átomo SYBYL y toda la información mol2 original.
    """
    conf = mol.GetConformer()
    atom_idx = 0

    with open(source_mol2) as fh:
        lines = fh.readlines()

    out_lines = []
    in_atom_block = False

    for line in lines:
        stripped = line.strip()
        if stripped == "@<TRIPOS>ATOM":
            in_atom_block = True
            out_lines.append(line)
            continue
        if stripped.startswith("@<TRIPOS>") and stripped != "@<TRIPOS>ATOM":
            in_atom_block = False

        if in_atom_block and stripped and not stripped.startswith("#"):
            parts = line.split()
            # formato mol2: id name x y z [type [subst_id [subst_name [charge]]]]
            if len(parts) >= 5:
                pos = conf.GetAtomPosition(atom_idx)
                # reconstruir manteniendo los campos originales
                new_line = (
                    f"{parts[0]:>7} {parts[1]:<8} "
                    f"{pos.x:>10.4f} {pos.y:>10.4f} {pos.z:>10.4f}"
                )
                if len(parts) > 5:
                    new_line += "  " + "  ".join(parts[5:])
                out_lines.append(new_line + "\n")
                atom_idx += 1
                continue

        out_lines.append(line)

    with open(out_path, "w") as fh:
        fh.writelines(out_lines)


def write_molecule(mol, filepath, source_path=None):
    ext = os.path.splitext(filepath)[1].lower()
    if ext in ('.sdf', '.mol'):
        writer = Chem.SDWriter(filepath)
        writer.write(mol)
        writer.close()
    elif ext == '.mol2':
        if source_path is None:
            raise ValueError("Se necesita source_path para escribir mol2")
        write_mol2_with_new_coords(source_path, filepath, mol)
    else:
        raise ValueError(f"Unsupported file format: {ext}")


def read_and_align_mol2(filepath):
    """
    Lee una molécula en formato mol2 (u otros soportados), la centra en el
    origen y alinea sus ejes principales con los ejes de coordenadas usando PCA
    geométrico (todos los átomos con peso igual a 1):
      - eje mayor    (mayor autovalor)  → eje X
      - eje intermedio                  → eje Y
      - eje menor    (menor autovalor)  → eje Z

    Devuelve el objeto mol de RDKit con la geometría transformada.
    """
    mol = read_molecule(filepath)
    if mol is None:
        raise ValueError(f"No se pudo leer la molécula de {filepath}")

    conf = mol.GetConformer()
    n_atoms = mol.GetNumAtoms()

    # 1. Obtener todas las coordenadas como matriz N×3
    coords = np.array([list(conf.GetAtomPosition(i)) for i in range(n_atoms)], dtype=float)

    # 2. Centrar exactamente en el centroide geométrico (peso 1 por átomo)
    centroid = coords.mean(axis=0)
    coords -= centroid
    print(f"Centroide antes de alinear ({os.path.basename(filepath)}): {centroid}")

    # 3. Matriz de covarianza geométrica (3×3), cada átomo contribuye igual
    cov = (coords.T @ coords) / n_atoms

    # 4. Eigendescomposición: eigenvectors[:, i] es el eje del autovalor eigenvalues[i]
    #    np.linalg.eigh devuelve autovalores en orden ASCENDENTE
    eigenvalues, eigenvectors = np.linalg.eigh(cov)

    # 5. Reordenar en orden DESCENDENTE: mayor varianza primero
    idx = np.argsort(eigenvalues)[::-1]   # [mayor, intermedio, menor]
    eigenvalues  = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]   # columnas = ejes principales

    print(f"Autovalores geométricos: {eigenvalues}")

    # 6. Garantizar sistema dextrógiro (det = +1, sin reflexión)
    if det(eigenvectors) < 0:
        eigenvectors[:, 2] = -eigenvectors[:, 2]

    # 7. Rotar: new[i] = eigenvectors.T @ coords[i]
    #    → columna X = proyección sobre eje mayor
    #    → columna Y = proyección sobre eje intermedio
    #    → columna Z = proyección sobre eje menor
    new_coords = coords @ eigenvectors   # equivalente a (eigenvectors.T @ coords.T).T

    # Verificación: el centroide debe ser (0,0,0) tras la rotación
    assert np.allclose(new_coords.mean(axis=0), 0.0, atol=1e-6), \
        "Error: el centroide no quedó en el origen tras la rotación"

    # 8. Escribir coordenadas transformadas de vuelta en el conformer
    for i in range(n_atoms):
        conf.SetAtomPosition(i, new_coords[i].tolist())

    return mol


def main():
    for f in sys.argv[1:]:
        try:
            mol = read_and_align_mol2(f)
        except Exception as e:
            # RDKit no siempre lanza ValueError ante un fichero invalido o
            # inexistente (p. ej. MolFromMol2File lanza OSError); se captura
            # Exception en general para que un fichero de entrada problematico
            # se reporte con un mensaje "Error: ..." legible, en vez de un
            # traceback sin controlar, igual que el resto de algoritmos del
            # catalogo.
            print(f"Error: {e}", file=sys.stderr)
            continue
        base, ext = os.path.splitext(f)
        out_path = f"{base}_aligned{ext}"
        write_molecule(mol, out_path, source_path=f)
        print(f"Molécula alineada guardada en: {out_path}")

try:
    import psyco
    psyco.full()
except Exception:
    pass

main()