"""
Tests del cribado en lote repartido (chord de Celery).

Antes el lote era UNA sola tarea que recorria las N moleculas en un bucle, de
modo que `--scale worker=N` no aceleraba el caso de uso principal de la
plataforma: los demas workers quedaban ociosos. Ahora el trabajo se divide en
bloques que se procesan en paralelo y un callback consolida el ranking.

Estos tests cubren las piezas puras --division en bloques, extraccion selectiva
y consolidacion-- sin necesidad de levantar Celery. El reparto efectivo entre
varios workers se comprobo por separado contra el despliegue real.
"""
import os

from app.config import BATCH_TAMANO_BLOQUE
from app.workflow_executor import BatchWorkflowExecutor


GRAFO_MINIMO = {
    "nodes": [{"id": "db1", "type": "selectDB", "data": {"nombre_archivo": "x.sdf"}}],
    "edges": [],
}


def _sdf_de_prueba(tmp_path, cuantas):
    from rdkit import Chem
    from rdkit.Chem import AllChem

    ruta = tmp_path / "biblioteca.sdf"
    writer = Chem.SDWriter(str(ruta))
    for i, smiles in enumerate(["CCO", "CCCO", "c1ccccc1", "CC(=O)O",
                                "CCN", "CCCN", "c1ccncc1", "CCCCO"][:cuantas]):
        mol = Chem.MolFromSmiles(smiles)
        mol.SetProp("_Name", f"mol{i}")
        AllChem.Compute2DCoords(mol)
        writer.write(mol)
    writer.close()
    return str(ruta)


def test_contar_moleculas_no_escribe_nada_en_disco(tmp_path):
    """
    El reparto necesita saber CUANTAS moleculas hay antes de procesar ninguna.
    El metodo anterior escribia un fichero temporal por molecula solo para
    contarlas, de modo que un SDF de 100.000 compuestos creaba 100.000
    ficheros de golpe.
    """
    ruta = _sdf_de_prueba(tmp_path, 8)
    antes = set(os.listdir("uploads"))

    indices = BatchWorkflowExecutor.indices_validos(ruta)

    assert indices == list(range(8))
    assert set(os.listdir("uploads")) == antes, "contar no debe materializar nada"


def test_solo_se_extraen_las_moleculas_del_bloque(tmp_path):
    """Cada subtarea extrae unicamente su bloque, no la biblioteca entera."""
    ruta = _sdf_de_prueba(tmp_path, 8)
    executor = BatchWorkflowExecutor(GRAFO_MINIMO, usuario_id=1, ejecucion_id=99)

    extraidas = executor.extraer_moleculas(ruta, [2, 5])
    try:
        assert [m["indice"] for m in extraidas] == [2, 5]
        assert [m["nombre"] for m in extraidas] == ["mol2", "mol5"]
        for m in extraidas:
            assert os.path.exists(m["ruta"])
            # El id de ejecucion en el temporal evita que dos ejecuciones
            # concurrentes del mismo flujo se pisen.
            assert "e99" in os.path.basename(m["ruta"])
    finally:
        for m in extraidas:
            if os.path.exists(m["ruta"]):
                os.remove(m["ruta"])


def test_el_lote_se_divide_en_bloques_del_tamano_configurado():
    indices = list(range(10))
    tam = 3
    bloques = [indices[i:i + tam] for i in range(0, len(indices), tam)]

    assert bloques == [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]
    # Ninguna molecula se pierde ni se duplica al repartir.
    assert sorted(i for b in bloques for i in b) == indices
    assert BATCH_TAMANO_BLOQUE >= 1


def test_consolidar_ordena_y_separa_las_moleculas_sin_score():
    """
    El callback recibe los resultados de todos los bloques y arma el ranking.
    Las moleculas sin score --por ejemplo un docking que no encontro ninguna
    pose-- deben caer al final SIN posicion, no contarse como exito.
    """
    executor = BatchWorkflowExecutor(GRAFO_MINIMO, usuario_id=1, ejecucion_id=1)
    resultados = [
        {"nombre": "a", "score": 0.9, "tipo_score": "similitud", "exito": True, "errores_nodo": []},
        {"nombre": "b", "score": 0.5, "tipo_score": "similitud", "exito": True, "errores_nodo": []},
        {"nombre": "c", "score": None, "tipo_score": None, "exito": False, "errores_nodo": ["fallo"]},
    ]

    resumen = executor.consolidar(resultados, "bd.sdf", total_moleculas=3, duracion=1.0)
    try:
        # similitud: mayor es mejor
        assert [r["nombre"] for r in resumen["ranking"][:2]] == ["a", "b"]
        assert resumen["ranking"][0]["posicion"] == 1
        assert resumen["ranking"][-1]["nombre"] == "c"
        assert resumen["ranking"][-1]["posicion"] is None
        assert resumen["total_exito"] == 2
        assert resumen["total_error"] == 1
        assert resumen["tipo_score"] == "similitud"
    finally:
        csv = os.path.join("uploads", resumen["csv_ranking"])
        if os.path.exists(csv):
            os.remove(csv)


def test_el_csv_de_ranking_lleva_el_id_de_ejecucion():
    """Dos ejecuciones concurrentes no deben escribir sobre el mismo CSV."""
    resumenes = []
    for ejec in (41, 42):
        executor = BatchWorkflowExecutor(GRAFO_MINIMO, usuario_id=1, ejecucion_id=ejec)
        resumenes.append(executor.consolidar(
            [{"nombre": "a", "score": 1.0, "tipo_score": "similitud",
              "exito": True, "errores_nodo": []}],
            "bd.sdf", total_moleculas=1, duracion=0.1))
    try:
        nombres = [r["csv_ranking"] for r in resumenes]
        assert "e41" in nombres[0] and "e42" in nombres[1]
        assert nombres[0] != nombres[1]
    finally:
        for r in resumenes:
            csv = os.path.join("uploads", r["csv_ranking"])
            if os.path.exists(csv):
                os.remove(csv)
