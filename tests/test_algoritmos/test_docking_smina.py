"""
Tests unitarios de algoritmos/dockingSmina.py.

Un docking real necesita un receptor PDBQT preparado (proteina con cargas y
Hs polares) que no tiene sentido sintetizar a mano para un test rapido; en
su lugar se prueban directamente las funciones puras del modulo (parseo del
log de Smina, deteccion de binario ausente) importandolo con
`importar_algoritmo`, sin pasar por subprocess ni necesitar el binario
`smina` instalado.
"""
import pytest


LOG_SMINA_EJEMPLO = """\
mode |   affinity | dist from best mode
     | (kcal/mol) | rmsd l.b.| rmsd u.b.
-----+------------+----------+----------
   1         -8.4      0.000      0.000
   2         -7.9      1.230      2.410
   3         -7.1      2.050      3.980
"""


def test_parsear_energias_extrae_todas_las_poses(importar_algoritmo):
    modulo = importar_algoritmo("dockingSmina")
    energias = modulo.parsear_energias(LOG_SMINA_EJEMPLO)

    assert len(energias) == 3
    assert energias[0] == {"pose": 1, "afinidad_kcal_mol": -8.4}
    assert energias[-1]["pose"] == 3


def test_parsear_energias_con_log_vacio_devuelve_lista_vacia(importar_algoritmo):
    modulo = importar_algoritmo("dockingSmina")
    assert modulo.parsear_energias("") == []


def test_verificar_smina_lanza_error_claro_si_falta_el_binario(importar_algoritmo, monkeypatch):
    modulo = importar_algoritmo("dockingSmina")
    monkeypatch.setattr(modulo.shutil, "which", lambda _: None)

    with pytest.raises(RuntimeError, match="Smina no está instalado"):
        modulo.verificar_smina()


def test_parsear_argv_opcionales_reconoce_flags_con_valor(importar_algoritmo):
    modulo = importar_algoritmo("dockingSmina")
    opciones = modulo._parsear_argv_opcionales(
        ["--exhaustiveness", "16", "--scoring", "vina"]
    )
    assert opciones == {"exhaustiveness": "16", "scoring": "vina"}
