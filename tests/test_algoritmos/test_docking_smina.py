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

# Salida REAL de smina, copiada de una ejecucion de verdad en el worker.
#
# Importa la diferencia con la de arriba: smina escribe las filas de pose
# PEGADAS AL MARGEN, sin sangria. El patron original exigia al menos un
# espacio antes del numero de pose, asi que sobre esto no encontraba ninguna
# --toda ejecucion de docking devolvia poses_generadas=0 y mejor_afinidad=null
# aunque el .sdf de poses estuviera bien escrito--. Y el test de arriba no lo
# detectaba porque su log estaba escrito a mano, con sangria, y no se parecia
# a lo que emite el binario.
#
# Se incluye entera, con la tabla de pesos, porque esas lineas TAMBIEN empiezan
# por digito y son el falso positivo que hay que evitar al relajar el patron.
LOG_SMINA_REAL = """\
smina is based off AutoDock Vina. Please cite appropriately.

Weights      Terms
-0.045       gauss(o=0,_w=0.8,_c=8)
0.8          repulsion(o=0,_c=8)
-0.035       hydrophobic(g=0,_b=2.5,_c=8)
-0.6         non_dir_h_bond(g=-0.6,_b=0,_c=8)
0            num_tors_div

Using random seed: -2056718428

mode |   affinity | dist from best mode
     | (kcal/mol) | rmsd l.b.| rmsd u.b.
-----+------------+----------+----------
1       -9.1       0.000      0.000
2       -8.3       10.712     11.752
3       -7.6       6.054      6.749
"""


def test_parsear_energias_extrae_todas_las_poses(importar_algoritmo):
    modulo = importar_algoritmo("dockingSmina")
    energias = modulo.parsear_energias(LOG_SMINA_EJEMPLO)

    assert len(energias) == 3
    assert energias[0] == {"pose": 1, "afinidad_kcal_mol": -8.4}
    assert energias[-1]["pose"] == 3


def test_parsear_energias_sobre_la_salida_real_de_smina(importar_algoritmo):
    """
    El caso que de verdad importa: smina no sangra las filas de pose.
    """
    modulo = importar_algoritmo("dockingSmina")
    energias = modulo.parsear_energias(LOG_SMINA_REAL)

    assert len(energias) == 3, "smina dio 3 poses y el parser debe encontrarlas"
    assert energias[0] == {"pose": 1, "afinidad_kcal_mol": -9.1}
    assert [e["pose"] for e in energias] == [1, 2, 3]


def test_parsear_energias_no_confunde_la_tabla_de_pesos_con_poses(importar_algoritmo):
    """
    "0.8          repulsion(o=0,_c=8)" tambien empieza por digito y va sin
    sangria: al aceptar filas sin sangria hay que seguir descartandola, o el
    docking reportaria poses que no existen.
    """
    modulo = importar_algoritmo("dockingSmina")
    tabla_de_pesos = (
        "Weights      Terms\n"
        "-0.045       gauss(o=0,_w=0.8,_c=8)\n"
        "0.8          repulsion(o=0,_c=8)\n"
        "0            num_tors_div\n"
    )
    assert modulo.parsear_energias(tabla_de_pesos) == []


def test_parsear_energias_acepta_afinidad_de_cero(importar_algoritmo):
    """
    Un redocking sobre una caja mal puesta da "-0.0", que es un numero
    perfectamente valido y no debe descartarse como si no hubiera pose.
    """
    modulo = importar_algoritmo("dockingSmina")
    energias = modulo.parsear_energias("1       -0.0       0.000      0.000    \n")
    assert energias == [{"pose": 1, "afinidad_kcal_mol": -0.0}]


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
