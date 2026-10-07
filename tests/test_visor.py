"""
Tests de app/visor.py: la logica del visor 3D (spec 002), sin HTTP.

Son funciones puras sobre texto y bytes --las que abren ficheros se prueban
con ficheros temporales--, asi que no necesitan servidor, ni red, ni RDKit
salvo donde se dice.
"""
import pytest

from app import visor


# ---------------------------------------------------------------------------
# normalizar y formato_de (T05)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("texto, esperado", [
    ("Cafeína ", "cafeina"),
    ("  ASPIRINA  ", "aspirina"),
    ("Ácido   acetil\tsalicílico", "acido acetil salicilico"),
    ("CHEMBL25", "chembl25"),
    ("", ""),
    ("ñandú", "nandu"),
])
def test_normalizar_quita_mayusculas_tildes_y_espacios_sobrantes(texto, esperado):
    """El buscador no distingue mayúsculas ni tildes (RF-3, RF-6)."""
    assert visor.normalizar(texto) == esperado


@pytest.mark.parametrize("nombre, esperado", [
    ("lote.sdf", "sdf"),
    ("LOTE.SDF", "sdf"),
    ("ligando.mol", "mol"),
    ("receptor.mol2", "mol2"),
    ("1hsg.pdb", "pdb"),
    ("receptor.pdbqt", "pdbqt"),
    ("agua.xyz", "xyz"),
    ("cafeina.smi", "smi"),
    ("ranking_e9.csv", "desconocido"),
    ("sin_extension", "desconocido"),
    ("raro.sdf.bak", "desconocido"),
])
def test_formato_de_reconoce_los_formatos_de_moleculas(nombre, esperado):
    """De la extension sale como se analiza y si se puede dibujar (RF-12)."""
    assert visor.formato_de(nombre) == esperado


# ---------------------------------------------------------------------------
# ficheros_para_buscador (T16, RF-3): grupos, formatos, filtro y orden
# ---------------------------------------------------------------------------

def _fila(nombre, tipo, visibilidad="biblioteca", dia=1, num=None):
    """Lo que el buscador lee de una fila de `archivos`."""
    from datetime import datetime
    from types import SimpleNamespace

    from app import models
    return SimpleNamespace(
        nombre=nombre,
        tipo=models.TipoArchivo(tipo) if tipo else None,
        visibilidad=models.VisibilidadArchivo(visibilidad),
        num_moleculas=num,
        fecha_creacion=datetime(2026, 10, dia),
    )


def test_el_buscador_agrupa_y_pone_lo_mas_reciente_primero():
    filas = [
        _fila("viejo.mol2", "molecula", dia=1),
        _fila("lote.sdf", "base_de_datos", dia=2, num=500),
        _fila("nuevo.pdb", "molecula", dia=3),
        _fila("poses_e9.sdf", "resultado", "resultado", dia=4, num=20),
    ]

    lista = visor.ficheros_para_buscador(filas, "")

    assert [(f["grupo"], f["nombre"]) for f in lista] == [
        ("molecula", "nuevo.pdb"), ("molecula", "viejo.mol2"),
        ("biblioteca", "lote.sdf"), ("resultado", "poses_e9.sdf"),
    ]
    assert lista[1]["formato"] == "mol2"
    assert lista[2]["num_moleculas"] == 500


def test_el_buscador_filtra_sin_mayusculas_ni_tildes():
    filas = [_fila("Cafeína.sdf", "molecula"), _fila("aspirina.sdf", "molecula")]

    assert [f["nombre"] for f in visor.ficheros_para_buscador(filas, "cafe")] == ["Cafeína.sdf"]


def test_el_buscador_no_ofrece_lo_que_no_son_moleculas():
    filas = [_fila("ranking_e9.csv", "resultado", "resultado"),
             _fila("resultados_e9.json", "resultado", "resultado"),
             _fila("cafeina.smi", "molecula")]

    # El SMILES si: se ofrece y al elegirlo se explica que no se dibuja (RF-12).
    assert [f["nombre"] for f in visor.ficheros_para_buscador(filas, "")] == ["cafeina.smi"]


def test_un_fichero_sin_tipo_anotado_se_agrupa_por_su_visibilidad():
    """Filas anteriores a la columna `tipo` que migrate.py aun no haya rellenado."""
    filas = [_fila("viejo.sdf", None), _fila("res.sdf", None, "resultado")]

    assert {f["nombre"]: f["grupo"] for f in visor.ficheros_para_buscador(filas, "")} == {
        "viejo.sdf": "molecula", "res.sdf": "resultado"}


# ---------------------------------------------------------------------------
# buscar_en_titulos (T06, RF-6): la lista de una biblioteca
# ---------------------------------------------------------------------------

def _posiciones(resultado):
    return [c["posicion"] for c in resultado["coincidencias"]]


def test_sin_consulta_lista_por_orden_desde_la_posicion_1():
    resultado = visor.buscar_en_titulos(["A", "B", "C"], "", 0, 50)

    assert resultado["total"] == 3
    assert resultado["coincidencias"] == [
        {"posicion": 1, "nombre": "A"},
        {"posicion": 2, "nombre": "B"},
        {"posicion": 3, "nombre": "C"},
    ]
    assert resultado["hay_mas"] is False
    assert resultado["fuera_de_rango"] is False


def test_busca_por_nombre_sin_mayusculas_ni_tildes():
    titulos = ["Cafeína", "aspirina", "teofilina"]

    assert _posiciones(visor.buscar_en_titulos(titulos, "CAFEINA", 0, 50)) == [1]
    assert _posiciones(visor.buscar_en_titulos(titulos, "ina", 0, 50)) == [1, 2, 3]
    assert _posiciones(visor.buscar_en_titulos(titulos, "ibuprofeno", 0, 50)) == []


def test_un_numero_da_su_posicion_primero_y_luego_los_nombres_que_lo_llevan():
    """
    "25" muestra la nº 25 y CHEMBL25 (RF-6). La nº 25 no se repite aunque su
    nombre tambien contenga "25".
    """
    titulos = ["M{}".format(i) for i in range(1, 31)]
    titulos[2] = "CHEMBL25"           # posicion 3

    resultado = visor.buscar_en_titulos(titulos, "25", 0, 50)

    assert _posiciones(resultado) == [25, 3]
    assert resultado["fuera_de_rango"] is False


def test_un_numero_fuera_de_rango_lo_dice_y_sigue_buscando_por_nombre():
    titulos = ["M1", "CHEMBL99", "M3"]

    resultado = visor.buscar_en_titulos(titulos, "99", 0, 50)

    assert resultado["fuera_de_rango"] is True
    assert resultado["total"] == 3
    assert _posiciones(resultado) == [2]


def test_la_posicion_0_esta_fuera_de_rango():
    """Las posiciones empiezan en 1 en todo lo que ve el usuario."""
    assert visor.buscar_en_titulos(["A"], "0", 0, 50)["fuera_de_rango"] is True


@pytest.mark.parametrize("consulta", ["-3", "2.5"])
def test_negativos_y_decimales_se_buscan_como_texto(consulta):
    titulos = ["A", "lote-3", "pH 2.5"]

    resultado = visor.buscar_en_titulos(titulos, consulta, 0, 50)

    assert resultado["fuera_de_rango"] is False
    assert len(resultado["coincidencias"]) == 1
    assert resultado["coincidencias"][0]["nombre"] in ("lote-3", "pH 2.5")


def test_un_registro_sin_nombre_se_llama_por_su_posicion():
    resultado = visor.buscar_en_titulos(["A", "", "  "], "", 0, 50)

    assert [c["nombre"] for c in resultado["coincidencias"]] == ["A", "Molécula nº 2", "Molécula nº 3"]


def test_un_registro_sin_nombre_se_encuentra_por_su_posicion():
    resultado = visor.buscar_en_titulos(["A", ""], "2", 0, 50)

    assert resultado["coincidencias"] == [{"posicion": 2, "nombre": "Molécula nº 2"}]


def test_pagina_de_50_en_50():
    titulos = ["M{}".format(i) for i in range(1, 121)]

    primera = visor.buscar_en_titulos(titulos, "", 0, 50)
    ultima = visor.buscar_en_titulos(titulos, "", 100, 50)

    assert _posiciones(primera) == list(range(1, 51))
    assert primera["hay_mas"] is True
    assert _posiciones(ultima) == list(range(101, 121))
    assert ultima["hay_mas"] is False


def test_las_paginas_de_una_busqueda_numerica_no_repiten_ni_se_saltan():
    """La posición pedida va en la primera página; las demás siguen por nombre."""
    titulos = ["X5{}".format(i) for i in range(60)]   # todos contienen "5"

    primera = visor.buscar_en_titulos(titulos, "5", 0, 50)
    segunda = visor.buscar_en_titulos(titulos, "5", 50, 50)
    vistas = _posiciones(primera) + _posiciones(segunda)

    assert vistas[0] == 5
    assert sorted(vistas) == list(range(1, 61))
    assert segunda["hay_mas"] is False


# ---------------------------------------------------------------------------
# analizar_sdf (T07-T08, RF-10, RF-12)
# ---------------------------------------------------------------------------

# Etanol sin hidrogenos, 3D, con tres campos: uno con marcado y otro de dos
# lineas. Escrito a mano para no depender de RDKit en estas pruebas.
ETANOL = (
    "etanol\n"
    "  prueba          3D\n"
    "\n"
    "  3  2  0  0  0  0  0  0  0  0999 V2000\n"
    "   -0.8883    0.1670    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "    0.4931   -0.3966    0.2150 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "    1.3952    0.6316   -0.1200 O   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "  1  2  1  0\n"
    "  2  3  1  0\n"
    "M  END\n"
    "> <afinidad>\n"
    "-7.4\n"
    "\n"
    "> <nota>\n"
    "<b>negrita</b>\n"
    "\n"
    "> <comentario>\n"
    "linea uno\n"
    "linea dos\n"
    "\n"
    "$$$$\n"
)


def test_analizar_sdf_da_nombre_y_atomos():
    datos = visor.analizar_sdf(ETANOL.encode())

    assert datos["nombre"] == "etanol"
    assert datos["num_atomos"] == 3


def test_analizar_sdf_da_los_campos_en_el_orden_del_fichero():
    datos = visor.analizar_sdf(ETANOL.encode())

    assert [c["nombre"] for c in datos["campos"]] == ["afinidad", "nota", "comentario"]
    assert datos["campos"][0]["valor"] == "-7.4"
    assert datos["campos"][2]["valor"] == "linea uno\nlinea dos"


def test_analizar_sdf_deja_los_valores_literales():
    """
    El contenido de un SDF lo escribe cualquiera que suba un fichero: se
    devuelve tal cual, y es la interfaz la que lo pinta como texto (RNF-2).
    """
    datos = visor.analizar_sdf(ETANOL.encode())

    assert datos["campos"][1]["valor"] == "<b>negrita</b>"


def test_analizar_sdf_con_crlf_y_sin_campos():
    registro = ETANOL.split("> <afinidad>")[0] + "$$$$\n"

    datos = visor.analizar_sdf(registro.replace("\n", "\r\n").encode())

    assert datos["nombre"] == "etanol"
    assert datos["num_atomos"] == 3
    assert datos["campos"] == []


def test_analizar_sdf_lee_los_atomos_de_un_v3000():
    registro = (
        "v3\n  prueba          3D\n\n"
        "  0  0  0     0  0            999 V3000\n"
        "M  V30 BEGIN CTAB\n"
        "M  V30 COUNTS 2 1 0 0 0\n"
        "M  V30 BEGIN ATOM\n"
        "M  V30 1 C 0 0 0 0\n"
        "M  V30 2 O 1.4 0 0.2 0\n"
        "M  V30 END ATOM\n"
        "M  V30 BEGIN BOND\n"
        "M  V30 1 1 1 2\n"
        "M  V30 END BOND\n"
        "M  V30 END CTAB\n"
        "M  END\n$$$$\n"
    )

    datos = visor.analizar_sdf(registro.encode())
    assert datos["num_atomos"] == 2
    # El O tiene z = 0.2: no es 2D aunque el C este en el origen.
    assert datos["solo_2d"] is False
    assert visor.analizar_sdf(registro.replace("1.4 0 0.2", "1.4 0 0").encode())["solo_2d"] is True


# El mismo bloque con valencia imposible que tests/conftest.py (N con cuatro
# enlaces simples y sin carga): RDKit no lo puede sanear.
VALENCIA_IMPOSIBLE = """molecula_rota
     RDKit          2D

  5  4  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0
    1.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    2.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000    1.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    0.0000   -1.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  1  3  1  0
  1  4  1  0
  1  5  1  0
M  END
$$$$
"""

VACIO = "vacio\n  prueba\n\n  0  0  0  0  0  0  0  0  0  0999 V2000\nM  END\n$$$$\n"


def _sin_jerga(motivo):
    """Lenguaje llano (principio 7): ni trazas, ni rutas, ni nombres de herramientas."""
    assert motivo
    for prohibido in ("Traceback", "RDKit", "valence", "Exception", "/", "\\"):
        assert prohibido not in motivo


def test_un_registro_3d_se_puede_dibujar():
    datos = visor.analizar_sdf(ETANOL.encode())

    assert datos["dibujable"] is True
    assert datos["motivo"] is None
    assert datos["solo_2d"] is False


def test_un_registro_con_todas_las_z_a_cero_es_2d():
    plano = ETANOL.replace("    0.2150 C", "    0.0000 C").replace("   -0.1200 O", "    0.0000 O")

    datos = visor.analizar_sdf(plano.encode())

    assert datos["solo_2d"] is True
    # Se dibuja igual: solo se avisa (RF-12).
    assert datos["dibujable"] is True


def test_un_registro_sin_atomos_no_se_puede_dibujar():
    datos = visor.analizar_sdf(VACIO.encode())

    assert datos["num_atomos"] == 0
    assert datos["dibujable"] is False
    _sin_jerga(datos["motivo"])


def test_un_registro_ilegible_no_se_puede_dibujar():
    datos = visor.analizar_sdf(b"roto\nbasura\n\nesto no es un molfile\n$$$$\n")

    assert datos["dibujable"] is False
    assert datos["num_atomos"] is None
    _sin_jerga(datos["motivo"])


def test_un_registro_con_valencia_imposible_no_se_puede_dibujar():
    """
    Es el mismo criterio que el inventario del cribado, que tambien usa RDKit:
    lo que el cribado no pudo leer, el visor no lo dibuja.
    """
    pytest.importorskip("rdkit")

    datos = visor.analizar_sdf(VALENCIA_IMPOSIBLE.encode())

    assert datos["dibujable"] is False
    assert datos["num_atomos"] == 5
    _sin_jerga(datos["motivo"])


# ---------------------------------------------------------------------------
# analizar_pdb (T09, RF-9, RF-10): proteina segun lo que declara el fichero
# ---------------------------------------------------------------------------

def _atomo(registro, n, nombre, residuo, cadena, num_res, x, y, z, elemento):
    """Una linea ATOM/HETATM en columnas fijas, como las escribe el PDB."""
    return "{:<6}{:>5} {:<4} {:>3} {}{:>4}    {:>8.3f}{:>8.3f}{:>8.3f}  1.00  0.00          {:>2}\n".format(
        registro, n, nombre, residuo, cadena, num_res, x, y, z, elemento)


PDB_PROTEINA = (
    "HEADER    PRUEBA\n"
    "SEQRES   1 A    2  ALA GLY\n"
    + _atomo("ATOM", 1, "N", "ALA", "A", 1, 0.0, 0.0, 0.0, "N")
    + _atomo("ATOM", 2, "CA", "ALA", "A", 1, 1.4, 0.0, 0.1, "C")
    + _atomo("ATOM", 3, "N", "GLY", "A", 2, 2.5, 0.8, 0.2, "N")
    + _atomo("HETATM", 4, "O", "HOH", "A", 101, 5.0, 5.0, 5.0, "O")
    + "END\n"
)

PDB_LIGANDO = (
    _atomo("HETATM", 1, "C1", "LIG", "X", 1, 0.0, 0.0, 0.0, "C")
    + _atomo("HETATM", 2, "O1", "LIG", "X", 1, 1.2, 0.0, 0.3, "O")
    + "END\n"
)

PDBQT_SIN_SEQRES = (
    _atomo("ATOM", 1, "N", "ALA", "A", 1, 0.0, 0.0, 0.0, "N")
    + _atomo("ATOM", 2, "CA", "ALA", "A", 1, 1.4, 0.0, 0.1, "C")
)

PDB_ADN = (
    "SEQRES   1 B    2   DA  DT\n"
    + _atomo("ATOM", 1, "P", " DA", "B", 1, 0.0, 0.0, 0.0, "P")
    + _atomo("ATOM", 2, "P", " DT", "B", 2, 6.0, 0.0, 0.5, "P")
)


def test_un_pdb_con_seqres_de_aminoacidos_es_proteina():
    datos = visor.analizar_pdb(PDB_PROTEINA)

    assert datos["es_proteina"] is True
    # Atomos tal como vienen: los de la proteina y el agua.
    assert datos["num_atomos"] == 4
    assert datos["dibujable"] is True
    assert datos["motivo"] is None


def test_un_pdb_con_solo_un_ligando_no_es_proteina():
    """Un ligando guardado en PDB se dibuja en varillas, no en cintas."""
    datos = visor.analizar_pdb(PDB_LIGANDO)

    assert datos["es_proteina"] is False
    assert datos["num_atomos"] == 2


def test_un_pdbqt_sin_seqres_es_proteina_por_sus_registros_atom():
    """Los PDBQT de las herramientas de docking no traen SEQRES."""
    assert visor.analizar_pdb(PDBQT_SIN_SEQRES)["es_proteina"] is True


def test_un_pdb_de_adn_no_es_proteina():
    """SEQRES declara un polimero, pero de nucleotidos: no lleva cintas de proteina."""
    assert visor.analizar_pdb(PDB_ADN)["es_proteina"] is False


def test_un_pdb_con_varios_modelos_cuenta_los_atomos_del_primero():
    modelos = "MODEL        1\n" + PDB_LIGANDO.replace("END\n", "ENDMDL\n") \
        + "MODEL        2\n" + PDB_LIGANDO.replace("END\n", "ENDMDL\n") + "END\n"

    assert visor.analizar_pdb(modelos)["num_atomos"] == 2


def test_un_pdb_sin_atomos_no_se_puede_dibujar():
    datos = visor.analizar_pdb("HEADER    VACIO\nEND\n")

    assert datos["num_atomos"] == 0
    assert datos["dibujable"] is False
    _sin_jerga(datos["motivo"])


def test_un_pdb_con_coordenadas_ilegibles_no_se_puede_dibujar():
    roto = PDB_LIGANDO.replace("   0.000   0.000   0.000", "   0.000   basura  0.000", 1)

    datos = visor.analizar_pdb(roto)

    assert datos["dibujable"] is False
    _sin_jerga(datos["motivo"])


# ---------------------------------------------------------------------------
# analizar_mol2 (T10, RF-9, RF-10): el tipo de molecula lo dice la cabecera
# ---------------------------------------------------------------------------

def _mol2(nombre, tipo, atomos):
    """Un MOL2 minimo; `atomos` son (elemento, x, y, z, subestructura)."""
    lineas = ["@<TRIPOS>MOLECULE", nombre, "{} 0 1 0 0".format(len(atomos)), tipo, "NO_CHARGES", "",
              "@<TRIPOS>ATOM"]
    for i, (el, x, y, z, sub) in enumerate(atomos, start=1):
        lineas.append("{:>7} {:<4} {:>9} {:>9} {:>9} {:<5} 1 {:<6} 0.0000".format(i, el, x, y, z, el, sub))
    return "\n".join(lineas) + "\n"


ATOMOS_PROTEINA = [("N", "0.000", "0.000", "0.000", "ALA1"), ("C", "1.400", "0.000", "0.100", "ALA1")]
ATOMOS_LIGANDO = [("C", "0.000", "0.000", "0.000", "LIG1"), ("O", "1.200", "0.000", "0.300", "LIG1")]


def test_un_mol2_declarado_protein_es_proteina():
    datos = visor.analizar_mol2(_mol2("receptor", "PROTEIN", ATOMOS_PROTEINA))

    assert datos["es_proteina"] is True
    assert datos["nombre"] == "receptor"
    assert datos["num_atomos"] == 2
    assert datos["dibujable"] is True


def test_un_mol2_declarado_small_no_es_proteina():
    datos = visor.analizar_mol2(_mol2("ligando", "SMALL", ATOMOS_LIGANDO))

    assert datos["es_proteina"] is False
    assert datos["nombre"] == "ligando"


def test_un_mol2_biopolymer_es_proteina_solo_si_sus_residuos_son_aminoacidos():
    """
    BIOPOLYMER vale para proteinas y para acidos nucleicos: se mira que
    residuos declara, igual que el SEQRES de un PDB.
    """
    adn = [("P", "0.000", "0.000", "0.000", "DA1"), ("P", "6.000", "0.000", "0.500", "DT2")]

    assert visor.analizar_mol2(_mol2("p", "BIOPOLYMER", ATOMOS_PROTEINA))["es_proteina"] is True
    assert visor.analizar_mol2(_mol2("a", "BIOPOLYMER", adn))["es_proteina"] is False


def test_un_mol2_sin_atomos_no_se_puede_dibujar():
    datos = visor.analizar_mol2(_mol2("vacio", "SMALL", []))

    assert datos["num_atomos"] == 0
    assert datos["dibujable"] is False
    _sin_jerga(datos["motivo"])


def test_un_mol2_sin_cabecera_no_se_puede_dibujar():
    datos = visor.analizar_mol2("esto no es un mol2\n")

    assert datos["dibujable"] is False
    assert datos["es_proteina"] is False
    _sin_jerga(datos["motivo"])


# ---------------------------------------------------------------------------
# analizar_xyz y SMILES (T11, RF-12)
# ---------------------------------------------------------------------------

AGUA_XYZ = "3\nagua\nO 0.000 0.000 0.000\nH 0.757 0.586 0.000\nH -0.757 0.586 0.000\n"


def test_un_xyz_se_dibuja_pero_avisa_de_que_no_trae_enlaces():
    """El visor deduce los enlaces por distancia: puede equivocarse (RF-12)."""
    datos = visor.analizar_xyz(AGUA_XYZ)

    assert datos["nombre"] == "agua"
    assert datos["num_atomos"] == 3
    assert datos["sin_enlaces"] is True
    assert datos["dibujable"] is True
    assert datos["motivo"] is None


def test_un_xyz_con_menos_atomos_de_los_que_declara_esta_danado():
    datos = visor.analizar_xyz(AGUA_XYZ.replace("3\n", "4\n", 1))

    assert datos["dibujable"] is False
    _sin_jerga(datos["motivo"])


def test_un_xyz_sin_atomos_no_se_puede_dibujar():
    datos = visor.analizar_xyz("0\nvacio\n")

    assert datos["dibujable"] is False
    _sin_jerga(datos["motivo"])


def test_un_smiles_no_se_puede_dibujar_y_dice_por_que():
    """
    Un SMILES no trae coordenadas: se ofrece en el buscador, pero al elegirlo
    se explica que hay que generar su 3D (RF-12; generarlo al vuelo queda fuera
    de esta version).
    """
    datos = visor.analizar_smi("CN1C=NC2=C1C(=O)N(C(=O)N2C)C cafeina\n")

    assert datos["nombre"] == "cafeina"
    assert datos["dibujable"] is False
    assert "3D" in datos["motivo"]
    assert "preparación" in datos["motivo"]
    _sin_jerga(datos["motivo"])


# ---------------------------------------------------------------------------
# nombre_descarga (T12, RF-11): el nombre sale del contenido del SDF
# ---------------------------------------------------------------------------

def _es_seguro(nombre):
    """Un nombre de fichero que no puede salirse de la carpeta de descargas."""
    assert nombre.endswith(".sdf")
    assert "/" not in nombre and "\\" not in nombre
    assert ".." not in nombre
    assert all(c.isprintable() for c in nombre)
    assert len(nombre) <= 100


def test_el_nombre_lleva_biblioteca_molecula_y_posicion():
    assert visor.nombre_descarga("CHEMBL25", 25, "chembl_500.sdf") == "chembl_500_CHEMBL25_n25.sdf"


def test_una_molecula_sin_nombre_se_llama_por_su_posicion():
    assert visor.nombre_descarga("", 7, "lote.sdf") == "lote_molecula_7.sdf"
    assert visor.nombre_descarga("   ", 7, "lote.sdf") == "lote_molecula_7.sdf"


def test_dos_moleculas_con_el_mismo_nombre_no_se_pisan():
    assert visor.nombre_descarga("ligando", 1, "lote.sdf") != visor.nombre_descarga("ligando", 2, "lote.sdf")


@pytest.mark.parametrize("nombre_molecula", [
    "../../etc/passwd",
    "..\\..\\windows\\system32",
    "con\x00trol\x07es\x1b[31m",
    "a" * 300,
    "nombre con espacios y / barras",
    "....",
])
def test_el_nombre_es_siempre_seguro(nombre_molecula):
    """
    El nombre de una molecula lo escribe quien sube el SDF: se trata como no
    fiable (principio 5, RNF-2).
    """
    _es_seguro(visor.nombre_descarga(nombre_molecula, 3, "lote.sdf"))


def test_la_biblioteca_tambien_se_sanea():
    nombre = visor.nombre_descarga("m", 1, "../uploads/../secreto.sdf")

    _es_seguro(nombre)
    assert nombre.startswith("secreto_")


def test_las_tildes_se_quitan_para_que_el_nombre_viaje_bien():
    """Un nombre ASCII se descarga igual en cualquier navegador y sistema."""
    assert visor.nombre_descarga("Cafeína", 1, "Café.sdf") == "Cafe_Cafeina_n1.sdf"


# ---------------------------------------------------------------------------
# leer_molecula y pagina_de_moleculas (T13, RF-5, RF-6, RF-10): con ficheros
# ---------------------------------------------------------------------------

CLAVES_MOLECULA = {"nombre", "num_atomos", "campos", "es_proteina", "solo_2d", "sin_enlaces",
                   "dibujable", "motivo", "contenido", "formato", "origen", "posicion"}


@pytest.fixture
def biblioteca(tmp_path):
    """Tres registros: etanol, uno sin nombre y otro etanol (nombre repetido)."""
    ruta = tmp_path / "lote.sdf"
    sin_nombre = "\n" + ETANOL.split("\n", 1)[1]
    ruta.write_bytes((ETANOL + sin_nombre + ETANOL).encode("utf-8"))
    return ruta


def test_leer_la_molecula_de_una_posicion(biblioteca):
    datos = visor.leer_molecula(str(biblioteca), 1)

    assert set(datos) == CLAVES_MOLECULA
    assert datos["nombre"] == "etanol"
    assert datos["posicion"] == 1
    assert datos["origen"] == "lote.sdf"
    assert datos["formato"] == "sdf"
    assert datos["num_atomos"] == 3
    assert datos["campos"][0] == {"nombre": "afinidad", "valor": "-7.4"}
    # Solo ese registro: nunca la biblioteca entera (RNF-1).
    assert datos["contenido"].startswith("etanol\n")
    assert datos["contenido"].count("$$$$") == 1


def test_leer_una_molecula_sin_nombre_la_llama_por_su_posicion(biblioteca):
    assert visor.leer_molecula(str(biblioteca), 2)["nombre"] == "Molécula nº 2"


@pytest.mark.parametrize("posicion", [0, 4, -1])
def test_una_posicion_que_no_existe_es_un_error(biblioteca, posicion):
    with pytest.raises(visor.PosicionInexistente):
        visor.leer_molecula(str(biblioteca), posicion)


def test_una_biblioteca_sin_posicion_es_un_error(biblioteca):
    """Sin posicion se leeria el fichero entero: con varias moleculas hay que elegir una."""
    with pytest.raises(visor.FaltaPosicion):
        visor.leer_molecula(str(biblioteca))


def test_un_sdf_de_una_molecula_se_lee_entero(tmp_path):
    ruta = tmp_path / "etanol.sdf"
    ruta.write_bytes((ETANOL).encode("utf-8"))

    datos = visor.leer_molecula(str(ruta))

    assert datos["nombre"] == "etanol"
    assert datos["posicion"] is None
    assert datos["dibujable"] is True


def test_un_pdb_se_lee_entero_y_se_llama_como_el_fichero(tmp_path):
    ruta = tmp_path / "receptor_1hsg.pdb"
    ruta.write_bytes((PDB_PROTEINA).encode("utf-8"))

    datos = visor.leer_molecula(str(ruta))

    assert set(datos) == CLAVES_MOLECULA
    assert datos["nombre"] == "receptor_1hsg"
    assert datos["es_proteina"] is True
    assert datos["formato"] == "pdb"
    assert datos["contenido"] == PDB_PROTEINA


def test_un_xyz_avisa_de_los_enlaces(tmp_path):
    ruta = tmp_path / "agua.xyz"
    ruta.write_bytes((AGUA_XYZ).encode("utf-8"))

    datos = visor.leer_molecula(str(ruta))

    assert set(datos) == CLAVES_MOLECULA
    assert datos["sin_enlaces"] is True


def test_un_fichero_que_no_es_de_moleculas_no_se_puede_dibujar(tmp_path):
    ruta = tmp_path / "ranking_e9.csv"
    ruta.write_bytes(("posicion,nombre,score\n1,a,0.9\n").encode("utf-8"))

    datos = visor.leer_molecula(str(ruta))

    assert set(datos) == CLAVES_MOLECULA
    assert datos["dibujable"] is False
    _sin_jerga(datos["motivo"])


def test_lo_que_devuelve_el_visor_cumple_sus_esquemas(biblioteca, tmp_path):
    """
    Los esquemas de respuesta (app/schemas.py) y las funciones del visor
    tienen que ir a la par: si una gana o pierde una clave, esto falla antes
    que el endpoint.
    """
    from app import schemas

    ruta_pdb = tmp_path / "r.pdb"
    ruta_pdb.write_bytes(PDB_PROTEINA.encode("utf-8"))

    for datos in (visor.leer_molecula(str(biblioteca), 1), visor.leer_molecula(str(ruta_pdb))):
        assert schemas.MoleculaVisor(**datos).model_dump() == datos
    pagina = visor.pagina_de_moleculas(str(biblioteca), "", 0, 50)
    assert schemas.PaginaMoleculas(**pagina).model_dump() == pagina


def test_descargar_una_molecula_de_una_biblioteca(biblioteca):
    contenido, nombre = visor.preparar_descarga(str(biblioteca), 3)

    assert nombre == "lote_etanol_n3.sdf"
    assert contenido.startswith(b"etanol\n")
    assert contenido.count(b"$$$$") == 1
    assert b"> <afinidad>" in contenido


def test_descargar_una_molecula_sin_nombre(biblioteca):
    _, nombre = visor.preparar_descarga(str(biblioteca), 2)

    assert nombre == "lote_molecula_2.sdf"


def test_descargar_un_fichero_entero_es_el_original(tmp_path):
    ruta = tmp_path / "receptor.pdb"
    ruta.write_bytes(PDB_PROTEINA.encode("utf-8"))

    # None: se entrega el fichero tal cual, con su nombre.
    assert visor.preparar_descarga(str(ruta), None) == (None, "receptor.pdb")


def test_descargar_una_biblioteca_sin_posicion_es_un_error(biblioteca):
    with pytest.raises(visor.FaltaPosicion):
        visor.preparar_descarga(str(biblioteca), None)


@pytest.mark.parametrize("posicion", [0, 4])
def test_descargar_una_posicion_que_no_existe_es_un_error(biblioteca, posicion):
    with pytest.raises(visor.PosicionInexistente):
        visor.preparar_descarga(str(biblioteca), posicion)


# ---------------------------------------------------------------------------
# Rapidez con 100 000 registros (T21, RNF-1). Lenta: genera ~60 MB.
# Se lanza expresamente con:
#   TFG_PRUEBAS_LENTAS=1 EXECUTION_MODE=local venv/Scripts/python -m pytest tests/test_visor.py -k rapidez -s
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not __import__("os").environ.get("TFG_PRUEBAS_LENTAS"),
                    reason="prueba lenta: se lanza con TFG_PRUEBAS_LENTAS=1")
def test_rapidez_con_una_biblioteca_de_100000(tmp_path):
    """
    RNF-1: tras construir el mapa (la primera apertura puede tardar mas), la
    primera pagina en menos de 2 s y una molecula en menos de 3. Se mide el
    servidor; la red de la universidad suma poco a respuestas de unos KB.
    """
    import time

    ruta = tmp_path / "grande.sdf"
    cuerpo = ETANOL.split("\n", 1)[1]
    with open(ruta, "wb") as f:
        for i in range(100_000):
            f.write("CHEMBL{}\n{}".format(i + 1, cuerpo).encode("utf-8"))

    inicio = time.perf_counter()
    visor.pagina_de_moleculas(str(ruta), "", 0, 50)
    construir = time.perf_counter() - inicio

    tiempos = {}
    for nombre, operacion in (
        ("primera pagina", lambda: visor.pagina_de_moleculas(str(ruta), "", 0, 50)),
        ("busqueda por nombre", lambda: visor.pagina_de_moleculas(str(ruta), "chembl9999", 0, 50)),
        ("busqueda numerica", lambda: visor.pagina_de_moleculas(str(ruta), "50000", 0, 50)),
        ("molecula del medio", lambda: visor.leer_molecula(str(ruta), 50_000)),
        ("ultima molecula", lambda: visor.leer_molecula(str(ruta), 100_000)),
    ):
        inicio = time.perf_counter()
        operacion()
        tiempos[nombre] = time.perf_counter() - inicio

    print("\nconstruir el mapa (primera apertura): {:.2f} s".format(construir))
    for nombre, segundos in tiempos.items():
        print("{}: {:.3f} s".format(nombre, segundos))

    assert max(tiempos["primera pagina"], tiempos["busqueda por nombre"], tiempos["busqueda numerica"]) < 2
    assert max(tiempos["molecula del medio"], tiempos["ultima molecula"]) < 3


def test_pagina_de_moleculas_lee_el_mapa_del_fichero(biblioteca):
    resultado = visor.pagina_de_moleculas(str(biblioteca), "etanol", 0, 50)

    assert resultado["total"] == 3
    # Nombres repetidos: se distinguen por la posicion.
    assert [c["posicion"] for c in resultado["coincidencias"]] == [1, 3]
