"""
Spec 009: copias de seguridad (scripts/copias.py).

El script corre en su propio contenedor (postgres:16 + python3) y solo usa la
biblioteca estandar, asi que se prueba aqui directamente, sobre carpetas
temporales y con pg_dump/pg_restore simulados: sin Docker ni Postgres.
"""
from datetime import datetime

from scripts import copias


# --- Nombres y conservacion (R3, R4) ------------------------------------------

def test_el_nombre_de_una_copia_es_su_fecha():
    assert copias.nombre_copia(datetime(2026, 10, 12, 3, 0)) == "2026-10-12_0300"


def _nombres(*fechas):
    return [copias.nombre_copia(f) for f in fechas]


def test_se_quedan_la_ultima_y_la_del_ultimo_domingo():
    # 11/10/2026 es domingo.
    nombres = _nombres(
        datetime(2026, 10, 4, 3),    # domingo anterior
        datetime(2026, 10, 10, 3),
        datetime(2026, 10, 11, 3),   # ultimo domingo
        datetime(2026, 10, 12, 3),   # la ultima
    )
    assert sorted(copias.copias_a_borrar(nombres)) == ["2026-10-04_0300", "2026-10-10_0300"]


def test_un_domingo_cuenta_como_las_dos():
    nombres = _nombres(datetime(2026, 10, 4, 3), datetime(2026, 10, 10, 3), datetime(2026, 10, 11, 3))
    assert sorted(copias.copias_a_borrar(nombres)) == ["2026-10-04_0300", "2026-10-10_0300"]


def test_sin_domingo_solo_queda_la_ultima():
    nombres = _nombres(datetime(2026, 10, 12, 3), datetime(2026, 10, 13, 3))
    assert copias.copias_a_borrar(nombres) == ["2026-10-12_0300"]


def test_nunca_se_borra_la_unica_copia():
    assert copias.copias_a_borrar(_nombres(datetime(2026, 10, 12, 3))) == []
    assert copias.copias_a_borrar([]) == []


def test_lo_que_no_es_una_copia_terminada_no_cuenta_ni_se_borra():
    # Una .parcial es una copia a medias o de un intento fallido, y lo que no
    # tiene nombre de fecha no lo ha creado el script: no se toca.
    nombres = _nombres(datetime(2026, 10, 12, 3)) + [
        "2026-10-13_0300.parcial", "notas.txt", "estado.json",
    ]
    assert copias.copias_a_borrar(nombres) == []


# --- Ficheros con enlaces duros (R2) ------------------------------------------

def _escribir(ruta, contenido):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)


def _origen(tmp_path):
    uploads = tmp_path / "uploads"
    _escribir(uploads / "biblioteca.sdf", b"mol\n$$$$\n")
    _escribir(uploads / "resultado.csv", b"a,b\n")
    _escribir(uploads / ".indices" / "biblioteca.sdf.idx", b"cache")
    return uploads


def test_copia_los_ficheros_y_salta_los_indices(tmp_path):
    uploads = _origen(tmp_path)
    destino = tmp_path / "copia1" / "uploads"

    ficheros, octetos = copias.copiar_ficheros(uploads, destino, anterior=None, excluir={".indices"})

    assert (destino / "biblioteca.sdf").read_bytes() == b"mol\n$$$$\n"
    assert (destino / "resultado.csv").exists()
    # Los indices se regeneran solos: copiarlos solo gasta espacio.
    assert not (destino / ".indices").exists()
    assert (ficheros, octetos) == (2, len(b"mol\n$$$$\n") + len(b"a,b\n"))


def test_lo_que_no_ha_cambiado_se_enlaza_a_la_copia_anterior(tmp_path):
    uploads = _origen(tmp_path)
    primera = tmp_path / "copia1" / "uploads"
    copias.copiar_ficheros(uploads, primera, anterior=None)

    _escribir(uploads / "resultado.csv", b"a,b\n1,2\n")    # cambia
    _escribir(uploads / "nuevo.mol2", b"nuevo")             # aparece
    segunda = tmp_path / "copia2" / "uploads"
    copias.copiar_ficheros(uploads, segunda, anterior=primera)

    # Igual que ayer: el mismo fichero en disco, no ocupa otra vez.
    assert (segunda / "biblioteca.sdf").stat().st_ino == (primera / "biblioteca.sdf").stat().st_ino
    # Cambiado: copia propia, y la de ayer conserva su contenido.
    assert (segunda / "resultado.csv").stat().st_ino != (primera / "resultado.csv").stat().st_ino
    assert (segunda / "resultado.csv").read_bytes() == b"a,b\n1,2\n"
    assert (primera / "resultado.csv").read_bytes() == b"a,b\n"
    assert (segunda / "nuevo.mol2").read_bytes() == b"nuevo"


def test_si_no_se_puede_enlazar_se_copia_entero(tmp_path, monkeypatch):
    # Docker Desktop en Windows puede no admitir enlaces duros en una carpeta
    # montada: la copia tiene que salir igual, aunque ocupe mas.
    uploads = _origen(tmp_path)
    primera = tmp_path / "copia1" / "uploads"
    copias.copiar_ficheros(uploads, primera, anterior=None)

    def sin_enlaces(*args, **kwargs):
        raise OSError("enlaces no admitidos")
    monkeypatch.setattr(copias.os, "link", sin_enlaces)

    segunda = tmp_path / "copia2" / "uploads"
    copias.copiar_ficheros(uploads, segunda, anterior=primera)
    assert (segunda / "biblioteca.sdf").read_bytes() == b"mol\n$$$$\n"
    assert (segunda / "biblioteca.sdf").stat().st_ino != (primera / "biblioteca.sdf").stat().st_ino


def test_un_origen_que_no_existe_no_copia_nada(tmp_path):
    assert copias.copiar_ficheros(tmp_path / "no_hay", tmp_path / "d", anterior=None) == (0, 0)


# --- Copia completa, fallo y estado (R2, R3, R7) ------------------------------

import json  # noqa: E402

import pytest  # noqa: E402


def _volcado_bueno(ruta):
    ruta.write_bytes(b"PGDMP volcado de prueba")


def _volcado_roto(ruta):
    ruta.write_bytes(b"a medias")
    raise RuntimeError("pg_dump ha fallado: no se puede conectar con la base")


def _plataforma(tmp_path):
    uploads = _origen(tmp_path)
    algoritmos = tmp_path / "algoritmos"
    _escribir(algoritmos / "tanimoto.py", b"print('hola')")
    return {"uploads": uploads, "algoritmos": algoritmos}


def _copiar(tmp_path, cuando, volcar=_volcado_bueno):
    return copias.hacer_copia(
        tmp_path / "copias", _plataforma(tmp_path), cuando,
        volcar_base=volcar, ruta_estado=tmp_path / "estado" / "estado.json",
    )


def test_una_copia_buena_lo_lleva_todo_y_su_manifiesto(tmp_path):
    nombre = _copiar(tmp_path, datetime(2026, 10, 12, 3))
    copia = tmp_path / "copias" / nombre

    assert nombre == "2026-10-12_0300"
    assert (copia / "base.dump").read_bytes() == b"PGDMP volcado de prueba"
    assert (copia / "uploads" / "biblioteca.sdf").exists()
    assert not (copia / "uploads" / ".indices").exists()
    assert (copia / "algoritmos" / "tanimoto.py").exists()
    assert not list((tmp_path / "copias").glob("*.parcial"))

    manifiesto = json.loads((copia / "manifiesto.json").read_text(encoding="utf-8"))
    assert manifiesto["copia"] == nombre
    assert manifiesto["ficheros"] == 3
    assert manifiesto["volcado_bytes"] == len(b"PGDMP volcado de prueba")

    estado = json.loads((tmp_path / "estado" / "estado.json").read_text(encoding="utf-8"))
    assert estado["ok"] is True and estado["error"] is None
    assert estado["ultima_buena"]["copia"] == nombre


def test_tras_copiar_se_rota(tmp_path):
    _copiar(tmp_path, datetime(2026, 10, 10, 3))
    _copiar(tmp_path, datetime(2026, 10, 11, 3))   # domingo
    _copiar(tmp_path, datetime(2026, 10, 12, 3))
    assert sorted(p.name for p in (tmp_path / "copias").iterdir()) == ["2026-10-11_0300", "2026-10-12_0300"]


def test_si_falla_el_volcado_no_queda_copia_ni_se_borra_nada(tmp_path):
    buena = _copiar(tmp_path, datetime(2026, 10, 11, 3))

    with pytest.raises(RuntimeError):
        _copiar(tmp_path, datetime(2026, 10, 12, 3), volcar=_volcado_roto)

    assert [p.name for p in (tmp_path / "copias").iterdir()] == [buena]
    estado = json.loads((tmp_path / "estado" / "estado.json").read_text(encoding="utf-8"))
    assert estado["ok"] is False
    assert "pg_dump ha fallado" in estado["error"]
    assert estado["ultimo_intento"].startswith("2026-10-12")
    # La ultima buena sigue constando: la pagina Sistema la ensena junto al aviso.
    assert estado["ultima_buena"]["copia"] == buena


# --- Restaurar y ordenes (R5, R6) ---------------------------------------------

def test_restaurar_repone_base_y_ficheros_sin_borrar_lo_que_sobra(tmp_path):
    nombre = _copiar(tmp_path, datetime(2026, 10, 12, 3))
    # Despues de la copia: se pierde un fichero, se estropea otro y aparece
    # uno nuevo.
    uploads = tmp_path / "uploads"
    (uploads / "biblioteca.sdf").unlink()
    _escribir(uploads / "resultado.csv", b"estropeado")
    _escribir(uploads / "posterior.sdf", b"de despues")
    restaurada = []

    copias.restaurar(tmp_path / "copias", nombre,
                     {"uploads": uploads, "algoritmos": tmp_path / "algoritmos"},
                     restaurar_base=restaurada.append)

    assert restaurada == [tmp_path / "copias" / nombre / "base.dump"]
    assert (uploads / "biblioteca.sdf").read_bytes() == b"mol\n$$$$\n"
    assert (uploads / "resultado.csv").read_bytes() == b"a,b\n"
    # Lo que no estaba en la copia se queda: limpiar_uploads.py lo senala.
    assert (uploads / "posterior.sdf").exists()


@pytest.mark.parametrize("nombre", ["2026-10-13_0300", "2026-10-12_0300.parcial", "../uploads"])
def test_restaurar_algo_que_no_es_una_copia_terminada_falla_claro(tmp_path, nombre):
    _copiar(tmp_path, datetime(2026, 10, 12, 3))
    (tmp_path / "copias" / "2026-10-12_0300.parcial").mkdir()
    restaurada = []
    with pytest.raises(ValueError, match="No hay ninguna copia terminada"):
        copias.restaurar(tmp_path / "copias", nombre, {"uploads": tmp_path / "uploads"},
                         restaurar_base=restaurada.append)
    assert restaurada == []


@pytest.mark.parametrize("ahora, esperada", [
    (datetime(2026, 10, 12, 1, 30), datetime(2026, 10, 12, 3, 0)),   # hoy, mas tarde
    (datetime(2026, 10, 12, 3, 0), datetime(2026, 10, 13, 3, 0)),    # justo ahora: manana
    (datetime(2026, 10, 12, 18, 0), datetime(2026, 10, 13, 3, 0)),   # ya paso: manana
])
def test_la_siguiente_copia_es_a_la_hora_pedida(ahora, esperada):
    assert copias.siguiente_copia(ahora, "03:00") == esperada
