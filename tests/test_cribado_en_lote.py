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
import os

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
#
# Aqui si hay ficheros de verdad: el trozo se construye copiando bytes del SDF
# con su indice (app/indice_sdf.py), asi que hace falta una biblioteca en
# disco. Lo que se sustituye es el algoritmo --por uno que cuenta lo que ve y
# responde como filtroLipinski-- y el grafo, por uno de un solo nodo.

_MOLBLOCK = (
    "{titulo}\n  RDKit          3D\n\n"
    "  1  0  0  0  0  0  0  0  0  0999 V2000\n"
    "    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "M  END\n"
)


def _biblioteca(ruta, titulos, separador_final=True):
    registros = [_MOLBLOCK.format(titulo=t) + "$$$$\n" for t in titulos]
    if not separador_final:
        registros[-1] = registros[-1][: -len("$$$$\n")]
    ruta.write_text("".join(registros), encoding="utf-8")


def _titulos_del_sdf(ruta):
    """El titulo de cada registro, en orden: la primera linea tras cada $$$$."""
    with open(ruta, encoding="utf-8") as f:
        texto = f.read()
    registros = [r for r in texto.split("$$$$\n") if r.strip()]
    return [r.split("\n", 1)[0] for r in registros]


class GrafoDeUnNodo:
    """
    Doble de WorkflowExecutor con un unico nodo de algoritmo, como el de un
    cribado con filtroLipinski: la molecula, `extras` y la salida.
    """

    def __init__(self, mol_info, salida_ext, extras, invocaciones):
        self._mol = mol_info
        self._salida = os.path.join(
            "uploads", "salida_m{}{}".format(mol_info["indice"], salida_ext))
        self._extras = extras
        self._invocaciones = invocaciones
        self.archivos_generados = []

    def ejecutar(self):
        from app.ejecutor import ejecutar_algoritmo as ejecutar

        exito = True
        for _ in range(self._invocaciones):
            r = ejecutar("uploads/algo.py", self._mol["ruta"], *self._extras,
                         self._salida, flags=[])
            exito = exito and r.get("exito", False)

        datos = None
        if os.path.exists(self._salida):
            self.archivos_generados.append(os.path.basename(self._salida))
            with open(self._salida, encoding="utf-8") as f:
                datos = json.load(f)
        return {
            "exito": exito,
            "errores": [],
            "resultados": {
                "sel_1":  {"tipo": "selectMol", "estado": "exito"},
                "prep_1": {"tipo": "preprocesado", "clave_score": "moleculas.MW",
                           "archivo_salida": self._salida, "resultado_json": datos},
            },
        }


@pytest.fixture()
def trozo(monkeypatch, tmp_path):
    """
    (ejecutor, indices, algoritmo) para un bloque sobre una biblioteca real.

    `algoritmo` es un dict que los tests ajustan y en el que el algoritmo de
    mentira anota lo que ha visto:
      devolver         "todas", "una" o un indice que se salta
      nombres_propios  si ignora los titulos y numera el mismo, como hace
                       filtroLipinski con las moleculas sin nombre
    """
    from app import ejecutor as modulo_ejecutor

    def _construir(titulos=("MOL0", "MOL1", "MOL2", "MOL3"), salida=".json",
                   extras=(), invocaciones=1, separador_final=True):
        (tmp_path / "uploads").mkdir()
        monkeypatch.chdir(tmp_path)
        _biblioteca(tmp_path / "uploads" / "biblio.sdf", list(titulos), separador_final)

        algoritmo = {"llamadas": 0, "vistos": None, "btmp_durante": None,
                     "devolver": "todas", "nombres_propios": False}

        def falso(ruta, *archivos, flags=()):
            algoritmo["llamadas"] += 1
            algoritmo["vistos"] = _titulos_del_sdf(archivos[0])
            algoritmo["btmp_durante"] = [n for n in os.listdir("uploads")
                                         if n.startswith("_btmp_")]
            entradas = []
            for i, titulo in enumerate(algoritmo["vistos"]):
                if algoritmo["devolver"] == "una" and i > 0:
                    break
                if algoritmo["devolver"] == i:
                    continue
                nombre = "mol_{}".format(i + 1) if algoritmo["nombres_propios"] else titulo
                entradas.append({"nombre": nombre, "MW": 100.0 + i, "estado": "PASS"})
            with open(archivos[-1], "w", encoding="utf-8") as f:
                json.dump({"exito": True, "total": len(entradas), "pass": len(entradas),
                           "fail": 0, "moleculas": entradas}, f)
            return {"exito": True, "log": "ok", "error": None}

        monkeypatch.setattr(modulo_ejecutor, "EXECUTION_MODE", "local")
        monkeypatch.setattr(modulo_ejecutor, "_ejecutar_local", falso)

        ejecutor = BatchWorkflowExecutor({"nodes": []}, usuario_id=1, ejecucion_id=9)
        monkeypatch.setattr(
            ejecutor, "_preparar_molecula",
            lambda mol, _nodo: GrafoDeUnNodo(mol, salida, list(extras), invocaciones))
        return ejecutor, list(range(len(titulos))), algoritmo

    return _construir


def _procesar(ejecutor, indices, **kw):
    return ejecutor._procesar_en_trozo("uploads/biblio.sdf", indices, "nodo_bd", **kw)


def test_el_bloque_entero_va_en_un_solo_job(trozo):
    """
    Lo que justifica el troceado: una ejecucion del algoritmo para todas las
    moleculas del bloque, que es lo que hace una peticion suelta sobre una
    biblioteca.
    """
    ejecutor, indices, algoritmo = trozo()

    resultados = _procesar(ejecutor, indices)

    assert algoritmo["llamadas"] == 1, "una sola ejecucion real para las cuatro"
    assert [r["nombre"] for r in resultados] == ["MOL0", "MOL1", "MOL2", "MOL3"]
    assert all(r["exito"] for r in resultados)
    # El score sale de la parte de cada molecula, no de la primera del trozo.
    assert [r["score"] for r in resultados] == [100.0, 101.0, 102.0, 103.0]


def test_ni_un_fichero_por_molecula(trozo):
    """
    Escribir, leer y borrar un fichero por molecula en uploads/ era casi todo
    el coste de un cribado: el trozo se construye copiando bytes del SDF y los
    resultados se reparten en memoria.
    """
    ejecutor, indices, algoritmo = trozo()

    _procesar(ejecutor, indices)

    assert algoritmo["btmp_durante"] == [], "no debe haber temporales por molecula"


def test_no_queda_nada_en_uploads(trozo, tmp_path):
    ejecutor, indices, _ = trozo()

    _procesar(ejecutor, indices)

    assert sorted(os.listdir(tmp_path / "uploads")) == [".indices", "biblio.sdf"]


def test_cada_molecula_viaja_etiquetada_y_vuelve_con_su_nombre(trozo):
    """
    Dentro del trozo cada registro lleva una etiqueta unica en vez de su nombre,
    para emparejar sin ambiguedad; fuera, en los resultados, la etiqueta no
    puede asomar.
    """
    ejecutor, indices, algoritmo = trozo()

    resultados = _procesar(ejecutor, indices)

    assert algoritmo["vistos"] == ["TFGMOL_0", "TFGMOL_1", "TFGMOL_2", "TFGMOL_3"]
    for r in resultados:
        datos = r["detalle"]["prep_1"]["datos"]
        assert datos["moleculas"][0]["nombre"] == r["nombre"]
        assert datos["total"] == 1


def test_nombres_repetidos_o_vacios_no_confunden_el_reparto(trozo):
    """
    Con nombres repetidos, emparejar por nombre daria a las dos moleculas el
    resultado de la primera; con nombres vacios, filtroLipinski numera por
    posicion. La etiqueta hace que ninguna de las dos cosas importe.
    """
    ejecutor, indices, _ = trozo(titulos=("DUP", "DUP", "", "OTRA"))

    resultados = _procesar(ejecutor, indices)

    assert [r["nombre"] for r in resultados] == ["DUP", "DUP", "mol_3", "OTRA"]
    assert [r["score"] for r in resultados] == [100.0, 101.0, 102.0, 103.0]


def test_un_algoritmo_de_una_sola_molecula_no_vale(trozo, tmp_path):
    """
    Una entrada para varias moleculas es la firma de un algoritmo que solo mira
    la primera. El bloque vuelve entonces por el camino de una tarea por
    molecula, y sin dejar nada atras.
    """
    ejecutor, indices, algoritmo = trozo()
    algoritmo["devolver"] = "una"

    assert _procesar(ejecutor, indices) is None
    assert sorted(os.listdir(tmp_path / "uploads")) == [".indices", "biblio.sdf"]


def test_si_falta_una_molecula_solo_falla_esa(trozo):
    """
    Una molecula que el algoritmo no consigue procesar no puede mandar el
    bloque entero por el camino lento: falla ella sola, con su motivo.
    """
    ejecutor, indices, algoritmo = trozo()
    algoritmo["devolver"] = 2

    resultados = _procesar(ejecutor, indices)

    assert [r["exito"] for r in resultados] == [True, True, False, True]
    assert "no devolvio resultado" in resultados[2]["errores_nodo"][0]
    assert resultados[3]["score"] == 103.0, "las demas no se corren de sitio"


def test_si_el_algoritmo_pone_sus_nombres_se_empareja_por_orden(trozo):
    ejecutor, indices, algoritmo = trozo()
    algoritmo["nombres_propios"] = True

    resultados = _procesar(ejecutor, indices)

    assert [r["nombre"] for r in resultados] == ["MOL0", "MOL1", "MOL2", "MOL3"]
    assert [r["score"] for r in resultados] == [100.0, 101.0, 102.0, 103.0]


def test_una_salida_que_no_es_json_no_se_trocea(trozo):
    """De un SDF de vuelta no se puede repartir lo que le toca a cada una."""
    ejecutor, indices, algoritmo = trozo(salida=".sdf")

    assert _procesar(ejecutor, indices) is None
    assert algoritmo["llamadas"] == 0, "se ve en seco, sin ejecutar nada"


def test_dos_algoritmos_encadenados_no_se_trocean(trozo):
    ejecutor, indices, algoritmo = trozo(invocaciones=2)

    assert _procesar(ejecutor, indices) is None
    assert algoritmo["llamadas"] == 0


def test_una_referencia_comun_viaja_tal_cual(trozo):
    """El cribado por similitud: la misma referencia para todo el bloque."""
    ejecutor, indices, algoritmo = trozo(extras=("uploads/referencia.sdf",))

    assert _procesar(ejecutor, indices) is not None
    assert algoritmo["llamadas"] == 1


def test_una_biblioteca_sin_separador_final(trozo):
    """
    Los molfiles de ChEMBL llegan sin $$$$. Sin anadirselo al copiarlo, el
    ultimo registro y lo que viniera detras se leerian como uno solo.
    """
    ejecutor, indices, algoritmo = trozo(separador_final=False)

    resultados = _procesar(ejecutor, indices)

    assert len(algoritmo["vistos"]) == 4
    assert len(resultados) == 4


def test_el_avance_se_anuncia_una_vez_por_molecula(trozo):
    ejecutor, indices, _ = trozo()

    avisadas = []
    _procesar(ejecutor, indices, on_molecula=avisadas.append)

    assert avisadas == ["MOL0", "MOL1", "MOL2", "MOL3"]
