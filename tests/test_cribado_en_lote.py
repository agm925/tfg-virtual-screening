"""
Tests del camino en lote del cribado (app/workflow_executor.py).

Lo que se fija aqui es la DECISION: cuando el bloque entero puede irse en un
solo job array y cuando hay que seguir molecula a molecula. Importa porque el
array corre todas sus tareas a la vez, asi que un grafo con dos algoritmos
encadenados no cabe en uno: el segundo necesita la salida del primero y se
encontraria el fichero sin escribir.

El motor de workflows no se toca en estos tests --hace falta base de datos y
catalogo-- sino que se sustituye por un grafo de mentira que solo hace lo
unico que importa aqui: llamar al ejecutor N veces.
"""
import json

import pytest

from app import workflow_executor
from app.ejecutor import ejecutar_algoritmo
from app.workflow_executor import BatchWorkflowExecutor


class GrafoFalso:
    """
    Doble de WorkflowExecutor: al ejecutarse llama al ejecutor de algoritmos
    tantas veces como invocaciones se le hayan dado.
    """

    def __init__(self, invocaciones):
        self._invocaciones = invocaciones
        self.archivos_generados = ["salida.json"]

    def ejecutar(self):
        resultados = [ejecutar_algoritmo(ruta, *archivos, flags=flags)
                      for ruta, archivos, flags in self._invocaciones]
        return {
            "exito":      all(r.get("exito") for r in resultados),
            "errores":    [],
            "resultados": {},
        }


@pytest.fixture()
def lote(monkeypatch, tmp_path):
    """
    (BatchWorkflowExecutor listo, moleculas, registro de lotes pedidos).

    `invocaciones_por_molecula` decide la forma del grafo: una sola invocacion
    es el cribado tipico --un Tanimoto, un Lipinski-- y dos son dos algoritmos
    encadenados.
    """

    def _construir(n_moleculas=2, invocaciones_por_molecula=1):
        moleculas = []
        for i in range(n_moleculas):
            fichero = tmp_path / "mol{}.sdf".format(i)
            fichero.write_bytes(b"molecula")
            moleculas.append({"nombre": "MOL{}".format(i), "indice": i,
                              "ruta": str(fichero)})

        ejecutor = BatchWorkflowExecutor({"nodes": []}, usuario_id=1)

        def preparar(mol_info, _nodo_bd_id):
            return GrafoFalso([
                (str(tmp_path / "algo.py"),
                 [mol_info["ruta"], str(tmp_path / "salida_{}_{}.json".format(mol_info["indice"], k))],
                 [])
                for k in range(invocaciones_por_molecula)
            ])

        monkeypatch.setattr(ejecutor, "_preparar_molecula", preparar)

        lotes_pedidos = []

        def lote_falso(invocaciones):
            invocaciones = list(invocaciones)
            lotes_pedidos.append(invocaciones)
            return [{"exito": True, "log": "", "error": None} for _ in invocaciones]

        monkeypatch.setattr(workflow_executor, "ejecutar_algoritmos_en_lote", lote_falso)
        return ejecutor, moleculas, lotes_pedidos

    return _construir


def test_un_grafo_de_un_solo_algoritmo_va_entero_en_un_lote(lote):
    """
    El caso del cribado de verdad: N moleculas, el mismo algoritmo, y una sola
    peticion al cluster en vez de N.
    """
    ejecutor, moleculas, lotes_pedidos = lote(n_moleculas=4)

    resultados = ejecutor._procesar_en_array(moleculas, "nodo_bd")

    assert [r["exito"] for r in resultados] == [True] * 4
    assert [r["nombre"] for r in resultados] == ["MOL0", "MOL1", "MOL2", "MOL3"]
    assert len(lotes_pedidos) == 1, "deberia haber UNA peticion en lote"
    assert len(lotes_pedidos[0]) == 4, "con las cuatro moleculas dentro"


def test_dos_algoritmos_encadenados_no_caben_en_un_array(lote):
    """
    Las tareas de un array corren a la vez, asi que el segundo algoritmo se
    encontraria la salida del primero sin escribir. Se devuelve None para que
    el bloque siga por el camino de siempre.
    """
    ejecutor, moleculas, lotes_pedidos = lote(invocaciones_por_molecula=2)

    assert ejecutor._procesar_en_array(moleculas, "nodo_bd") is None
    assert lotes_pedidos == [], "no debe mandarse nada al cluster"


def test_un_grafo_que_no_llega_a_ejecutar_nada_tampoco(lote):
    """Si la pasada en seco no anota ninguna invocacion, no hay lote que armar."""
    ejecutor, moleculas, lotes_pedidos = lote(invocaciones_por_molecula=0)

    assert ejecutor._procesar_en_array(moleculas, "nodo_bd") is None
    assert lotes_pedidos == []


def test_una_sola_molecula_no_monta_un_array(lote):
    """Un array de una tarea es toda la maquinaria para nada."""
    ejecutor, moleculas, lotes_pedidos = lote(n_moleculas=1)

    assert ejecutor._procesar_en_array(moleculas, "nodo_bd") is None
    assert lotes_pedidos == []


def test_ninguna_de_las_dos_pasadas_ejecuta_un_algoritmo_de_verdad(lote, monkeypatch):
    """
    El grafo se recorre dos veces, y ninguna de las dos debe ejecutar nada: la
    primera va en seco --solo anota que pide cada molecula-- y la segunda se
    sirve de lo que ya calculo el lote. Si alguna se escapara, el cribado
    ejecutaria dos veces lo mismo y ademas fuera del array.
    """
    from app import ejecutor as modulo_ejecutor

    ejecutor, moleculas, _ = lote(n_moleculas=3)

    ejecutados = []
    monkeypatch.setattr(modulo_ejecutor, "_ejecutar_local",
                        lambda *a, **k: ejecutados.append(a) or {"exito": False})

    ejecutor._procesar_en_array(moleculas, "nodo_bd")

    assert ejecutados == []


def test_los_ficheros_temporales_de_las_moleculas_se_borran(lote):
    """
    extraer_moleculas escribe un fichero por molecula. Con bibliotecas de
    miles, no borrarlos llena uploads/.
    """
    import os

    ejecutor, moleculas, _ = lote(n_moleculas=3)

    ejecutor._procesar_en_array(moleculas, "nodo_bd")

    for mol in moleculas:
        assert not os.path.exists(mol["ruta"]), mol["ruta"]


def test_el_progreso_se_avisa_una_vez_por_molecula(lote):
    """El indicador de avance de la interfaz cuenta moleculas, no lotes."""
    ejecutor, moleculas, _ = lote(n_moleculas=3)

    avisadas = []
    ejecutor._procesar_en_array(moleculas, "nodo_bd", on_molecula=avisadas.append)

    assert avisadas == ["MOL0", "MOL1", "MOL2"]


# ---------------------------------------------------------------------------
# El resultado del cribado es UN fichero, no uno por molecula
# ---------------------------------------------------------------------------


def _resultado(nombre, score, archivos=(), detalle=None):
    return {
        "nombre":       nombre,
        "score":        score,
        "tipo_score":   "similitud",
        "exito":        True,
        "errores_nodo": [],
        "archivos":     list(archivos),
        "detalle":      detalle or {},
    }


@pytest.fixture()
def consolidador(monkeypatch, tmp_path):
    """BatchWorkflowExecutor con un uploads/ propio donde escribir."""
    (tmp_path / "uploads").mkdir()
    monkeypatch.chdir(tmp_path)
    return BatchWorkflowExecutor({"nodes": []}, usuario_id=1, ejecucion_id=7)


def test_el_cribado_deja_un_json_con_todas_las_moleculas(consolidador, tmp_path):
    """
    El CSV es el ranking --posicion, nombre, score-- y en la base de datos solo
    caben las 25 primeras. Los numeros de cada molecula tienen que estar en
    algun sitio, y ese sitio es un fichero, no mil.
    """
    resultados = [
        _resultado(
            "MOL{}".format(i), 0.5 - i / 100.0,
            detalle={"comp_1": {"tipo": "comparacion",
                                "datos": {"tanimoto": 0.5 - i / 100.0, "MW": 300 + i}}})
        for i in range(30)
    ]

    salida = consolidador.consolidar(resultados, "biblioteca.sdf", 30, 12.0)

    fichero = tmp_path / "uploads" / salida["json_resultados"]
    assert fichero.exists()

    contenido = json.loads(fichero.read_text(encoding="utf-8"))
    assert len(contenido["moleculas"]) == 30, "deben estar todas, no solo el top-25"
    assert contenido["resumen"]["total_exito"] == 30
    assert contenido["resumen"]["base_de_datos"] == "biblioteca.sdf"
    # Y con los valores que calculo cada nodo dentro.
    assert contenido["moleculas"][0]["detalle"]["comp_1"]["datos"]["MW"] == 300


def test_los_json_por_molecula_se_borran_al_consolidar(consolidador, tmp_path):
    """
    Su contenido acaba de copiarse al fichero consolidado. Conservarlos era
    tener la misma cifra en dos sitios y, en una biblioteca de verdad, un
    fichero y una fila en `archivos` por molecula.
    """
    uploads = tmp_path / "uploads"
    for i in range(3):
        (uploads / "comparacion_m{}.json".format(i)).write_text("{}", encoding="utf-8")

    salida = consolidador.consolidar(
        [_resultado("MOL{}".format(i), 0.5, ["comparacion_m{}.json".format(i)])
         for i in range(3)],
        "biblioteca.sdf", 3, 1.0)

    for i in range(3):
        assert not (uploads / "comparacion_m{}.json".format(i)).exists()
    # Y dejan de figurar como resultados descargables.
    assert all(m["archivos"] == [] for m in salida["ranking"])


def test_las_poses_y_alineaciones_si_se_conservan(consolidador, tmp_path):
    """
    Una estructura no cabe dentro de un JSON de numeros: es el resultado en si,
    no una forma de consultarlo. El JSON de energias que dockingSmina escribe
    aparte si sobra, porque sus cifras ya van dentro.
    """
    uploads = tmp_path / "uploads"
    (uploads / "poses_m0.sdf").write_text("estructura", encoding="utf-8")
    (uploads / "docking_m0_energias.json").write_text("{}", encoding="utf-8")

    salida = consolidador.consolidar(
        [_resultado("MOL0", -9.1, ["poses_m0.sdf", "docking_m0_energias.json"])],
        "biblioteca.sdf", 1, 1.0)

    assert (uploads / "poses_m0.sdf").exists()
    assert not (uploads / "docking_m0_energias.json").exists()
    assert salida["ranking"][0]["archivos"] == ["poses_m0.sdf"]


# ---------------------------------------------------------------------------
# Troceado: UN job para el bloque entero
# ---------------------------------------------------------------------------


@pytest.fixture()
def bloque_troceable(monkeypatch, tmp_path):
    """
    Un bloque listo para trocear, con un uploads/ propio.

    `salida` y `entradas_extra` permiten romper a proposito las condiciones que
    el troceado exige: que la salida sea un JSON y que lo unico que cambie de
    una molecula a otra sea su fichero.
    """

    def _construir(n_moleculas=3, salida=".json", entradas_extra=None):
        (tmp_path / "uploads").mkdir()
        monkeypatch.chdir(tmp_path)

        moleculas = []
        for i in range(n_moleculas):
            fichero = tmp_path / "mol{}.sdf".format(i)
            # Un SDF de una molecula tal como lo escribe RDKit: acaba en $$$$.
            fichero.write_text("MOL{}\n\n\n  0  0\nM  END\n$$$$\n".format(i),
                               encoding="utf-8")
            moleculas.append({"nombre": "MOL{}".format(i), "indice": i,
                              "ruta": str(fichero)})

        ejecutor = BatchWorkflowExecutor({"nodes": []}, usuario_id=1, ejecucion_id=9)

        def preparar(mol_info, _nodo_bd_id):
            archivos = [mol_info["ruta"]]
            if entradas_extra is not None:
                archivos.append(entradas_extra(mol_info))
            archivos.append(str(tmp_path / "salida_m{}{}".format(mol_info["indice"], salida)))
            return GrafoFalso([(str(tmp_path / "algo.py"), archivos, [])])

        monkeypatch.setattr(ejecutor, "_preparar_molecula", preparar)
        return ejecutor, moleculas

    return _construir


def _algoritmo_de_mentira(monkeypatch, moleculas_devueltas):
    """
    Sustituye el ejecutor por un algoritmo que escribe en su salida una lista de
    `moleculas_devueltas` entradas, contando los nombres que encuentra en el SDF
    de entrada. Devuelve la lista de llamadas.
    """
    llamadas = []

    def falso(ruta_algoritmo, *archivos, flags=()):
        llamadas.append({"algoritmo": ruta_algoritmo, "archivos": list(archivos),
                         "flags": list(flags)})
        entrada, salida = archivos[0], archivos[-1]
        with open(entrada, encoding="utf-8") as f:
            nombres = [l.strip() for l in f if l.startswith("MOL")]
        llamadas[-1]["moleculas_vistas"] = len(nombres)
        with open(salida, "w", encoding="utf-8") as f:
            json.dump({
                "exito": True,
                "total": len(nombres),
                "pass": len(nombres),
                "fail": 0,
                "moleculas": [{"nombre": n, "MW": 300.0 + i, "estado": "PASS"}
                              for i, n in enumerate(nombres[:moleculas_devueltas])],
            }, f)
        return {"exito": True, "log": "procesadas {}".format(len(nombres)), "error": None}

    monkeypatch.setattr(workflow_executor, "ejecutar_algoritmo", falso)
    return llamadas


def test_el_bloque_entero_va_en_un_solo_job(bloque_troceable, monkeypatch, tmp_path):
    """
    Lo que justifica el troceado: una transferencia y un job para las N
    moleculas, que es lo que hace una peticion suelta sobre una biblioteca.
    """
    ejecutor, moleculas = bloque_troceable(n_moleculas=3)
    llamadas = _algoritmo_de_mentira(monkeypatch, moleculas_devueltas=3)

    resultados = ejecutor._procesar_en_trozo(moleculas, "nodo_bd")

    assert resultados is not None
    assert len(llamadas) == 1, "una sola llamada al algoritmo para las tres"
    assert [r["nombre"] for r in resultados] == ["MOL0", "MOL1", "MOL2"]


def test_el_trozo_lleva_las_moleculas_con_su_separador(bloque_troceable, monkeypatch):
    """
    Si el SDF del trozo no trae los $$$$, RDKit lee todo como un unico registro
    roto y el algoritmo devuelve una molecula en vez de N.
    """
    ejecutor, moleculas = bloque_troceable(n_moleculas=4)
    llamadas = _algoritmo_de_mentira(monkeypatch, moleculas_devueltas=4)

    ejecutor._procesar_en_trozo(moleculas, "nodo_bd")

    # El fichero del trozo ya se ha borrado, pero el algoritmo de mentira conto
    # sus moleculas al leerlo: sin los separadores no habria encontrado cuatro.
    assert len(llamadas) == 1
    assert llamadas[0]["moleculas_vistas"] == 4


def test_el_trozo_y_su_salida_no_se_quedan_en_uploads(bloque_troceable, monkeypatch, tmp_path):
    ejecutor, moleculas = bloque_troceable(n_moleculas=3)
    _algoritmo_de_mentira(monkeypatch, moleculas_devueltas=3)

    ejecutor._procesar_en_trozo(moleculas, "nodo_bd")

    assert list((tmp_path / "uploads").iterdir()) == []
    for mol in moleculas:
        import os
        assert not os.path.exists(mol["ruta"])


def test_cada_molecula_recibe_su_parte_del_trozo(bloque_troceable, monkeypatch, tmp_path):
    """
    El grafo se recorre despues como siempre y cada nodo lee su fichero de
    salida: ahi tiene que estar la parte que le toca a esa molecula, con la
    misma forma que si se hubiera ejecutado sola.
    """
    ejecutor, moleculas = bloque_troceable(n_moleculas=3)
    _algoritmo_de_mentira(monkeypatch, moleculas_devueltas=3)

    ejecutor._procesar_en_trozo(moleculas, "nodo_bd")

    for i in range(3):
        contenido = json.loads(
            (tmp_path / "salida_m{}.json".format(i)).read_text(encoding="utf-8"))
        assert contenido["total"] == 1
        assert len(contenido["moleculas"]) == 1
        assert contenido["moleculas"][0]["nombre"] == "MOL{}".format(i)
        # Los recuentos del trozo se rehacen para una sola molecula.
        assert contenido["pass"] == 1


def test_un_algoritmo_que_solo_mira_la_primera_molecula_no_vale(bloque_troceable, monkeypatch):
    """
    Que el algoritmo sepa tragar varias no se puede saber de antemano: se
    comprueba contando los resultados que devuelve. Si no vienen los N, se
    vuelve por el camino de un job por molecula.
    """
    ejecutor, moleculas = bloque_troceable(n_moleculas=3)
    _algoritmo_de_mentira(monkeypatch, moleculas_devueltas=1)

    assert ejecutor._procesar_en_trozo(moleculas, "nodo_bd") is None


def test_un_algoritmo_que_devuelve_moleculas_no_se_trocea(bloque_troceable, monkeypatch):
    """
    De un SDF de vuelta no se puede repartir por nombre lo que le toca a cada
    molecula. Y no se llega ni a intentarlo: se ve en la extension.
    """
    ejecutor, moleculas = bloque_troceable(n_moleculas=3, salida=".sdf")
    llamadas = _algoritmo_de_mentira(monkeypatch, moleculas_devueltas=3)

    assert ejecutor._procesar_en_trozo(moleculas, "nodo_bd") is None
    assert llamadas == [], "no debe ejecutarse nada"


def test_una_referencia_distinta_por_molecula_impide_el_trozo(bloque_troceable, monkeypatch):
    """
    Las N van a compartir un unico job, asi que si una segunda entrada cambiara
    de una molecula a otra el trozo estaria calculando otra cosa.
    """
    ejecutor, moleculas = bloque_troceable(
        n_moleculas=3,
        entradas_extra=lambda mol: "referencia_{}.sdf".format(mol["indice"]))
    llamadas = _algoritmo_de_mentira(monkeypatch, moleculas_devueltas=3)

    assert ejecutor._procesar_en_trozo(moleculas, "nodo_bd") is None
    assert llamadas == []


def test_una_referencia_comun_si_permite_el_trozo(bloque_troceable, monkeypatch):
    """Lo habitual del cribado por similitud: la misma referencia para todas."""
    ejecutor, moleculas = bloque_troceable(
        n_moleculas=3, entradas_extra=lambda _mol: "referencia.sdf")
    llamadas = _algoritmo_de_mentira(monkeypatch, moleculas_devueltas=3)

    assert ejecutor._procesar_en_trozo(moleculas, "nodo_bd") is not None
    assert len(llamadas) == 1
    # La referencia viaja tal cual; lo que se sustituye es la molecula.
    assert llamadas[0]["archivos"][1] == "referencia.sdf"
