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

    construcciones = []
    original = indice_sdf.construir
    monkeypatch.setattr(indice_sdf, "construir",
                        lambda r: construcciones.append(r) or original(r))
    indice_sdf.obtener(str(ruta))

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
