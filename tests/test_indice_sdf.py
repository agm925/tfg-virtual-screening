"""
Tests de app/indice_sdf.py: el indice de posiciones de los registros de un SDF.

Lo que se fija es que cada registro empieza y acaba donde debe, porque es lo
que decide que moleculas van en cada trozo al cluster. Un indice que se
equivoque en un byte no da error: manda moleculas que no son las del bloque.
"""
import os

import pytest

from app import indice_sdf

MOLBLOCK = "{}\n  RDKit\n\n  0  0  0  0  0  0  0  0  0  0999 V2000\nM  END\n"


def _escribir(ruta, texto, crlf=False):
    datos = texto.replace("\n", "\r\n") if crlf else texto
    ruta.write_bytes(datos.encode("utf-8"))


def _registros(ruta):
    limites = indice_sdf.construir(str(ruta))
    with open(ruta, "rb") as f:
        return [indice_sdf.leer_registro(f, limites, i) for i in range(len(limites) - 1)]


def test_cada_registro_va_de_su_titulo_a_su_separador(tmp_path):
    ruta = tmp_path / "b.sdf"
    _escribir(ruta, "".join(MOLBLOCK.format(n) + "$$$$\n" for n in ("A", "B", "C")))

    registros = _registros(ruta)

    assert [indice_sdf.titulo(r) for r in registros] == ["A", "B", "C"]
    assert all(r.endswith(b"$$$$\n") for r in registros)
    # Pegados de nuevo tienen que dar el fichero exacto: ni un byte de mas ni
    # de menos entre registros.
    assert b"".join(registros) == ruta.read_bytes()


def test_un_ultimo_registro_sin_separador_tambien_cuenta(tmp_path):
    """Asi llegan los molfiles de ChEMBL, y RDKit si los lee."""
    ruta = tmp_path / "b.sdf"
    _escribir(ruta, MOLBLOCK.format("A") + "$$$$\n" + MOLBLOCK.format("B"))

    assert [indice_sdf.titulo(r) for r in _registros(ruta)] == ["A", "B"]


def test_lo_que_hay_en_blanco_tras_el_ultimo_no_es_un_registro(tmp_path):
    ruta = tmp_path / "b.sdf"
    _escribir(ruta, MOLBLOCK.format("A") + "$$$$\n\n\n")

    assert len(_registros(ruta)) == 1


def test_un_titulo_en_blanco_es_legal(tmp_path):
    """
    La primera linea de un registro es su nombre y puede estar vacia: no hay
    que saltarla buscando la "de verdad", o el molfile quedaria descuadrado.
    """
    ruta = tmp_path / "b.sdf"
    _escribir(ruta, MOLBLOCK.format("A") + "$$$$\n" + MOLBLOCK.format("") + "$$$$\n")

    registros = _registros(ruta)

    assert [indice_sdf.titulo(r) for r in registros] == ["A", ""]
    assert registros[1].startswith(b"\n  RDKit")


def test_un_fichero_con_crlf(tmp_path):
    """Un SDF guardado en Windows: el separador es "$$$$\\r\\n"."""
    ruta = tmp_path / "b.sdf"
    _escribir(ruta, "".join(MOLBLOCK.format(n) + "$$$$\n" for n in ("A", "B")), crlf=True)

    registros = _registros(ruta)

    assert [indice_sdf.titulo(r) for r in registros] == ["A", "B"]
    # Y al cambiarle el titulo se respeta su fin de linea.
    assert indice_sdf.con_titulo(registros[0], "X").startswith(b"X\r\n")


def test_se_construye_una_vez_y_se_reutiliza(tmp_path, monkeypatch):
    ruta = tmp_path / "b.sdf"
    _escribir(ruta, MOLBLOCK.format("A") + "$$$$\n")

    indice_sdf.obtener(str(ruta))
    assert os.path.exists(indice_sdf.ruta_indice(str(ruta)))

    # Se espia construir_mapa, que es lo que recorre el fichero: obtener ya no
    # pasa por construir(), y espiar esa daria la prueba por buena siempre.
    construcciones = []
    original = indice_sdf.construir_mapa
    monkeypatch.setattr(indice_sdf, "construir_mapa",
                        lambda r: construcciones.append(r) or original(r))
    indice_sdf.obtener(str(ruta))
    indice_sdf.obtener_titulos(str(ruta))

    assert construcciones == [], "la segunda vez tiene que leerlo, no rehacerlo"


def test_un_indice_de_otro_contenido_no_se_usa(tmp_path):
    """
    Si el fichero cambia, su indice viejo no da error: lee moleculas
    equivocadas. Tiene que darse por caducado y rehacerse.
    """
    ruta = tmp_path / "b.sdf"
    _escribir(ruta, MOLBLOCK.format("A") + "$$$$\n")
    assert len(indice_sdf.obtener(str(ruta))) - 1 == 1

    _escribir(ruta, "".join(MOLBLOCK.format(n) + "$$$$\n" for n in ("A", "B", "C")))

    assert indice_sdf.cargar(str(ruta)) is None
    assert len(indice_sdf.obtener(str(ruta))) - 1 == 3


def test_un_indice_ilegible_se_rehace(tmp_path):
    ruta = tmp_path / "b.sdf"
    _escribir(ruta, MOLBLOCK.format("A") + "$$$$\n")
    indice_sdf.obtener(str(ruta))
    with open(indice_sdf.ruta_indice(str(ruta)), "wb") as f:
        f.write(b"esto no es un indice")

    assert indice_sdf.cargar(str(ruta)) is None
    assert len(indice_sdf.obtener(str(ruta))) - 1 == 1


def test_borrar_quita_el_indice(tmp_path):
    ruta = tmp_path / "b.sdf"
    _escribir(ruta, MOLBLOCK.format("A") + "$$$$\n")
    indice_sdf.obtener(str(ruta))

    indice_sdf.borrar(str(ruta))

    assert not os.path.exists(indice_sdf.ruta_indice(str(ruta)))
    # Los titulos se van con el: si no, el mapa de un fichero borrado se
    # quedaria en .indices para siempre.
    assert not os.path.exists(indice_sdf.ruta_titulos(str(ruta)))
    indice_sdf.borrar(str(ruta))   # y dos veces no es un error


@pytest.mark.parametrize("registro, esperado", [
    (b"A\nM  END\n$$$$\n", b"A\nM  END\n$$$$\n"),
    (b"A\nM  END\n",       b"A\nM  END\n$$$$\n"),
    (b"A\nM  END",         b"A\nM  END\n$$$$\n"),
    (b"A\nM  END\n$$$$",   b"A\nM  END\n$$$$\n"),
])
def test_terminado_deja_siempre_un_separador(registro, esperado):
    assert indice_sdf.terminado(registro) == esperado


def test_el_inventario_numera_por_separadores(tmp_path, monkeypatch):
    """
    La numeracion que importa: un registro corrupto se queda en su sitio, sin
    ser legible, y los demas conservan su posicion en el fichero.
    """
    pytest.importorskip("rdkit")
    from app.workflow_executor import BatchWorkflowExecutor

    bueno = ("{}\n  RDKit\n\n  1  0  0  0  0  0  0  0  0  0999 V2000\n"
             "    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
             "M  END\n$$$$\n")
    roto = "{}\nbasura\n\nesto no es un molfile\n$$$$\n"
    ruta = tmp_path / "b.sdf"
    _escribir(ruta, bueno.format("A") + roto.format("B") + bueno.format("C"))

    indices, total = BatchWorkflowExecutor.inventario_sdf(str(ruta))

    assert total == 3
    assert indices == [0, 2]


# ---------------------------------------------------------------------------
# Titulos de los registros: el mapa del visor 3D (spec 002, RF-6)
#
# El visor lista y busca por nombre las moleculas de una biblioteca de hasta
# 100 000 registros sin leer el fichero entero (RNF-1). Para eso guarda, junto
# al indice de posiciones, el titulo de cada registro. Lo que se fija aqui es
# que titulo y posicion casan: un titulo desplazado un puesto no da error,
# abre en el visor una molecula que no es la que el usuario eligio.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("crlf", [False, True])
def test_los_titulos_son_la_primera_linea_de_cada_registro(tmp_path, crlf):
    ruta = tmp_path / "b.sdf"
    _escribir(ruta, "".join(MOLBLOCK.format(n) + "$$$$\n" for n in ("A", "B", "C")), crlf=crlf)

    titulos = indice_sdf.obtener_titulos(str(ruta))

    assert titulos == ["A", "B", "C"]
    # Los mismos que sacaria titulo() de cada registro leido por el indice: el
    # mapa no puede tener una idea propia de cual es el nombre.
    assert titulos == [indice_sdf.titulo(r) for r in _registros(ruta)]


def test_un_registro_sin_titulo_da_cadena_vacia(tmp_path):
    """El visor lo enseñara como "Molecula nº N"; aqui solo tiene que quedar vacio."""
    ruta = tmp_path / "b.sdf"
    _escribir(ruta, MOLBLOCK.format("A") + "$$$$\n" + MOLBLOCK.format("") + "$$$$\n")

    assert indice_sdf.obtener_titulos(str(ruta)) == ["A", ""]


def test_el_ultimo_registro_sin_separador_tiene_su_titulo(tmp_path):
    """Como los molfiles de ChEMBL: si el indice lo cuenta, el mapa tambien."""
    ruta = tmp_path / "b.sdf"
    _escribir(ruta, MOLBLOCK.format("A") + "$$$$\n" + MOLBLOCK.format("B"))

    assert indice_sdf.obtener_titulos(str(ruta)) == ["A", "B"]


def test_un_titulo_que_no_es_utf8_no_rompe_el_mapa(tmp_path):
    """
    Un SDF exportado en Latin-1 trae los acentos como bytes sueltos. El titulo
    se lee con un caracter de reemplazo, igual que titulo(), y los siguientes
    siguen en su sitio.
    """
    ruta = tmp_path / "b.sdf"
    # MOLBLOCK con titulo vacio empieza por "\n": delante va el titulo en bytes.
    ruta.write_bytes(b"Caf\xe9" + MOLBLOCK.format("").encode() + b"$$$$\n"
                     + MOLBLOCK.format("B").encode() + b"$$$$\n")

    assert indice_sdf.obtener_titulos(str(ruta)) == ["Caf�", "B"]


def test_los_titulos_van_alineados_con_el_indice(tmp_path):
    """
    Un registro roto se queda en su posicion, con su titulo, como en el
    inventario del cribado: la posicion N del visor es el registro N del
    indice.
    """
    roto = "{}\nbasura\n\nesto no es un molfile\n$$$$\n"
    ruta = tmp_path / "b.sdf"
    _escribir(ruta, MOLBLOCK.format("A") + "$$$$\n" + roto.format("B") + MOLBLOCK.format("C") + "$$$$\n")

    titulos = indice_sdf.obtener_titulos(str(ruta))

    assert titulos == ["A", "B", "C"]
    assert len(titulos) == len(indice_sdf.obtener(str(ruta))) - 1


def test_los_titulos_de_otro_contenido_no_se_usan(tmp_path):
    """
    Como el indice: si el fichero cambia, sus titulos viejos no dan error,
    ponen a cada molecula el nombre de otra. Se dan por caducados y se rehacen.
    """
    ruta = tmp_path / "b.sdf"
    _escribir(ruta, MOLBLOCK.format("A") + "$$$$\n")
    assert indice_sdf.obtener_titulos(str(ruta)) == ["A"]

    _escribir(ruta, "".join(MOLBLOCK.format(n) + "$$$$\n" for n in ("X", "Y")))

    assert indice_sdf.cargar_titulos(str(ruta)) is None
    assert indice_sdf.obtener_titulos(str(ruta)) == ["X", "Y"]


def test_mismo_tamano_pero_otra_fecha_tambien_caduca(tmp_path):
    """
    Renombrar una molecula sin cambiar la longitud deja el fichero del mismo
    tamano: es la fecha la que delata el cambio. Se fuerza una fecha distinta
    porque dos escrituras seguidas pueden caer en el mismo instante del reloj.
    """
    ruta = tmp_path / "b.sdf"
    _escribir(ruta, MOLBLOCK.format("A") + "$$$$\n")
    indice_sdf.obtener_titulos(str(ruta))
    antes = os.stat(ruta).st_mtime_ns

    _escribir(ruta, MOLBLOCK.format("B") + "$$$$\n")
    os.utime(ruta, ns=(antes + 10**9, antes + 10**9))

    assert indice_sdf.obtener_titulos(str(ruta)) == ["B"]


def test_unos_titulos_ilegibles_se_rehacen(tmp_path):
    ruta = tmp_path / "b.sdf"
    _escribir(ruta, MOLBLOCK.format("A") + "$$$$\n")
    indice_sdf.obtener_titulos(str(ruta))
    with open(indice_sdf.ruta_titulos(str(ruta)), "wb") as f:
        f.write(b"esto no son titulos")

    assert indice_sdf.cargar_titulos(str(ruta)) is None
    assert indice_sdf.obtener_titulos(str(ruta)) == ["A"]


def test_unos_titulos_que_no_cuadran_con_la_cabecera_se_rehacen(tmp_path):
    """
    Cabecera valida pero un titulo de menos (un fichero cortado al escribir):
    no se puede usar, porque desde el que falta todos irian desplazados.
    """
    ruta = tmp_path / "b.sdf"
    _escribir(ruta, "".join(MOLBLOCK.format(n) + "$$$$\n" for n in ("A", "B")))
    indice_sdf.obtener_titulos(str(ruta))
    ruta_t = indice_sdf.ruta_titulos(str(ruta))
    with open(ruta_t, "rb") as f:
        cabecera = f.readline()
    with open(ruta_t, "wb") as f:
        f.write(cabecera + b'["A"]')

    assert indice_sdf.cargar_titulos(str(ruta)) is None
    assert indice_sdf.obtener_titulos(str(ruta)) == ["A", "B"]


def test_una_biblioteca_con_indice_pero_sin_titulos_los_construye(tmp_path):
    """
    Las bibliotecas indexadas antes de que existieran los titulos tienen su
    .idx pero no su .titulos: el visor tiene que poder abrirlas igual.
    """
    ruta = tmp_path / "b.sdf"
    _escribir(ruta, "".join(MOLBLOCK.format(n) + "$$$$\n" for n in ("A", "B")))
    indice_sdf.guardar(str(ruta), indice_sdf.construir(str(ruta)))
    assert not os.path.exists(indice_sdf.ruta_titulos(str(ruta)))

    assert indice_sdf.obtener_titulos(str(ruta)) == ["A", "B"]
    assert os.path.exists(indice_sdf.ruta_titulos(str(ruta)))


# ---------------------------------------------------------------------------
# Anotar registros con propiedades (el SDF que devuelve un cribado)
# ---------------------------------------------------------------------------

MOLBLOCK_CARBONO = (
    "{}\n  RDKit          3D\n\n"
    "  1  0  0  0  0  0  0  0  0  0999 V2000\n"
    "    1.5000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "M  END\n"
)


def test_las_propiedades_se_leen_como_campos_del_sdf(tmp_path):
    """Que el SDF de un cribado se abra con los valores dentro, en RDKit o KNIME."""
    from rdkit import Chem

    registro = MOLBLOCK_CARBONO.format("aspirina").encode() + b"$$$$\n"
    anotado = indice_sdf.con_propiedades(
        registro, {"MW": 180.16, "violaciones": 0, "estado_raro": "PASS",
                   "detalle": {"MW_ok": True}, "vacio": None})

    ruta = tmp_path / "anotado.sdf"
    ruta.write_bytes(anotado)
    mol = next(iter(Chem.SDMolSupplier(str(ruta))))

    assert mol.GetProp("_Name") == "aspirina"
    assert mol.GetDoubleProp("MW") == 180.16
    assert mol.GetProp("violaciones") == "0"
    # Lo que no es una sola cifra o palabra no tiene como escribirse.
    assert not mol.HasProp("detalle") and not mol.HasProp("vacio")
    # Las coordenadas no se tocan.
    assert mol.GetConformer().GetAtomPosition(0).x == pytest.approx(1.5)


def test_se_anota_aunque_falte_el_separador_final():
    registro = MOLBLOCK_CARBONO.format("sin_separador").encode()

    anotado = indice_sdf.con_propiedades(registro, {"LogP": 1.2})

    assert anotado.endswith(b"> <LogP>\n1.2\n\n$$$$\n")
    assert anotado.count(b"$$$$") == 1


def test_un_nombre_de_campo_no_rompe_el_formato():
    anotado = indice_sdf.con_propiedades(
        MOLBLOCK_CARBONO.format("m").encode(), {"a<b>\nc": 1})

    assert b"> <abc>\n1\n" in anotado


def test_registros_separa_la_salida_de_un_algoritmo():
    """gen3D o un filtro pueden dejar varias moleculas en su salida, y la
    ultima sin separador."""
    contenido = (MOLBLOCK_CARBONO.format("c1") + "$$$$\n"
                 + MOLBLOCK_CARBONO.format("c2")).encode()

    partes = indice_sdf.registros(contenido)

    assert [indice_sdf.titulo(p) for p in partes] == ["c1", "c2"]
    assert all(p.rstrip().endswith(b"$$$$") for p in partes)
    assert indice_sdf.registros(b"") == []
