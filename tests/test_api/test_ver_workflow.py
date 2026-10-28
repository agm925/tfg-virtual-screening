"""
Tests de integracion de la spec 012: la copia del grafo que guarda cada
ejecucion, el borrado logico de workflows y el borrado de una ejecucion.
"""
import pytest

from app import models

GRAFO_A = {"nodes": [{"id": "selectMol_0", "type": "selectMol",
                      "data": {"nombre_archivo": "a.mol2"}}], "edges": []}
GRAFO_B = {"nodes": [{"id": "selectMol_0", "type": "selectMol",
                      "data": {"nombre_archivo": "b.mol2"}}], "edges": []}


def _workflow(client, headers, grafo=GRAFO_A) -> int:
    r = client.post("/workflows", data={"nombre": "wf 012", "descripcion": ""}, headers=headers)
    assert r.status_code == 200, r.text
    wid = r.json()["id"]
    _guardar(client, headers, wid, grafo)
    return wid


def _guardar(client, headers, workflow_id, grafo):
    r = client.put(f"/workflows/{workflow_id}",
                   json={"nombre": "wf 012", "descripcion": "", "grafo_json": grafo}, headers=headers)
    assert r.status_code == 200, r.text


def _ejecutar(client, headers, workflow_id) -> int:
    r = client.post(f"/workflows/{workflow_id}/ejecutar", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["ejecucion_id"]


# --- R1. Copia del grafo -----------------------------------------------------

def test_ejecutar_guarda_una_copia_que_no_cambia_al_editar(client, mock_celery, usuario_autenticado):
    """CA1 y CA3."""
    headers = usuario_autenticado["headers"]
    wid = _workflow(client, headers)
    eid = _ejecutar(client, headers, wid)

    _guardar(client, headers, wid, GRAFO_B)

    r = client.get(f"/workflows/ejecuciones/{eid}", headers=headers)
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["grafo_json"] == GRAFO_A
    assert datos["copia_exacta"] is True
    assert datos["workflow_borrado"] is False


def test_la_ejecucion_ajena_no_se_puede_ver(client, mock_celery, usuario_autenticado, otro_usuario_autenticado):
    """CA3."""
    headers = usuario_autenticado["headers"]
    eid = _ejecutar(client, headers, _workflow(client, headers))

    r = client.get(f"/workflows/ejecuciones/{eid}", headers=otro_usuario_autenticado["headers"])
    assert r.status_code == 403


def test_una_ejecucion_sin_copia_devuelve_el_grafo_del_workflow(
    client, db_session, mock_celery, usuario_autenticado
):
    """CA4: las ejecuciones de antes del cambio no tienen copia."""
    headers = usuario_autenticado["headers"]
    wid = _workflow(client, headers)
    eid = _ejecutar(client, headers, wid)
    ejecucion = db_session.get(models.WorkflowExecution, eid)
    ejecucion.grafo_json = None
    db_session.commit()
    _guardar(client, headers, wid, GRAFO_B)

    datos = client.get(f"/workflows/ejecuciones/{eid}", headers=headers).json()
    assert datos["grafo_json"] == GRAFO_B
    assert datos["copia_exacta"] is False


def test_el_modo_en_lote_se_decide_con_la_copia(client, db_session, mock_celery, usuario_autenticado):
    """R1: la decision se toma sobre lo mismo que se va a ejecutar."""
    headers = usuario_autenticado["headers"]
    grafo_lote = {"nodes": [{"id": "selectDB_0", "type": "selectDB",
                             "data": {"nombre_archivo": "biblioteca.sdf"}}],
                  "edges": [{"source": "selectDB_0", "target": "descargar_0"}]}
    wid = _workflow(client, headers, grafo_lote)

    r = client.post(f"/workflows/{wid}/ejecutar", headers=headers)

    assert r.json()["modo"] == "batch"
    db_session.expire_all()
    assert db_session.get(models.WorkflowExecution, r.json()["ejecucion_id"]).grafo_json == grafo_lote


# --- R1. Las tareas ejecutan la copia (CA2) ----------------------------------

COPIA = {"nodes": [], "edges": [], "version": "la que se lanzo"}
EDITADO = {"nodes": [], "edges": [], "version": "editada despues"}


def _ejecucion_con_copia(db_session, usuario_id):
    """Un workflow lanzado con COPIA y editado a EDITADO mientras esperaba en la cola."""
    workflow = models.Workflow(nombre="wf copia", descripcion="", grafo_json=COPIA, usuario_id=usuario_id)
    db_session.add(workflow)
    db_session.commit()
    ejecucion = models.WorkflowExecution(workflow_id=workflow.id, usuario_id=usuario_id,
                                         estado="pendiente", grafo_json=COPIA)
    db_session.add(ejecucion)
    workflow.grafo_json = EDITADO
    db_session.commit()
    return workflow, ejecucion


def _executor_espia(grafos):
    """Anota con que grafo se crea el ejecutor."""
    class Espia:
        archivos_generados = []

        def __init__(self, grafo, *_a, **_kw):
            grafos.append(grafo)

        def ejecutar(self):
            return {"estado": "completado", "exito": True, "errores": [],
                    "resultados": {}, "duracion_segundos": 0}

        def localizar_base_de_datos(self):
            raise RuntimeError("basta con saber el grafo")

        def consolidar(self, *_a, **_kw):
            return {"estado": "completado", "exito": True, "duracion_segundos": 0}
    return Espia


def test_la_ejecucion_normal_usa_la_copia(db_session, usuario_autenticado, monkeypatch):
    from app import tasks
    workflow, ejecucion = _ejecucion_con_copia(db_session, usuario_autenticado["usuario"]["id"])
    grafos = []
    monkeypatch.setattr(tasks, "WorkflowExecutor", _executor_espia(grafos))
    monkeypatch.setattr(tasks, "_vigia_cancelacion", lambda _id: lambda: False)

    tasks.ejecutar_workflow_async(workflow.id, workflow.usuario_id, ejecucion.id)

    assert grafos == [COPIA]


def test_el_reparto_en_lote_usa_la_copia(db_session, usuario_autenticado, monkeypatch):
    from app import tasks
    workflow, ejecucion = _ejecucion_con_copia(db_session, usuario_autenticado["usuario"]["id"])
    grafos = []
    monkeypatch.setattr(tasks, "BatchWorkflowExecutor", _executor_espia(grafos))

    # El espia corta en localizar_base_de_datos, y el coordinador deja la
    # ejecucion en error y vuelve a lanzar la excepcion.
    with pytest.raises(RuntimeError):
        tasks.ejecutar_workflow_batch_async(workflow.id, workflow.usuario_id, ejecucion.id)

    assert grafos == [COPIA]


def test_la_consolidacion_usa_la_copia(db_session, usuario_autenticado, monkeypatch):
    """Antes releia el workflow al terminar: si se editaba durante el cribado, los
    bloques y la consolidacion usaban grafos distintos."""
    import time

    from app import tasks
    workflow, ejecucion = _ejecucion_con_copia(db_session, usuario_autenticado["usuario"]["id"])
    grafos = []
    monkeypatch.setattr(tasks, "BatchWorkflowExecutor", _executor_espia(grafos))
    monkeypatch.setattr(tasks, "_redis", lambda: None)

    tasks.consolidar_batch([], workflow.id, workflow.usuario_id, ejecucion.id, "biblio.sdf", 0, time.time())

    assert grafos == [COPIA]


def test_sin_copia_las_tareas_usan_el_workflow(db_session, usuario_autenticado, monkeypatch):
    """CA4: lo encolado antes del despliegue sigue funcionando."""
    from app import tasks
    workflow, ejecucion = _ejecucion_con_copia(db_session, usuario_autenticado["usuario"]["id"])
    ejecucion.grafo_json = None
    db_session.commit()
    grafos = []
    monkeypatch.setattr(tasks, "WorkflowExecutor", _executor_espia(grafos))
    monkeypatch.setattr(tasks, "_vigia_cancelacion", lambda _id: lambda: False)

    tasks.ejecutar_workflow_async(workflow.id, workflow.usuario_id, ejecucion.id)

    assert grafos == [EDITADO]


# --- R2. Borrar un workflow no borra sus resultados (CA5) --------------------

def _fichero_de_resultado(db_session, usuario_id, ejecucion_id, nombre):
    import os
    with open(os.path.join("uploads", nombre), "wb") as f:
        f.write(b"resultado\n$$$$\n")
    db_session.add(models.Archivo(
        nombre=nombre, visibilidad=models.VisibilidadArchivo.resultado,
        tipo=models.TipoArchivo.resultado, propietario_id=usuario_id, ejecucion_id=ejecucion_id,
    ))
    db_session.commit()


def test_borrar_un_workflow_lo_quita_del_constructor(client, mock_celery, usuario_autenticado):
    headers = usuario_autenticado["headers"]
    wid = _workflow(client, headers)
    _ejecutar(client, headers, wid)

    assert client.delete(f"/workflows/{wid}", headers=headers).status_code == 200

    uid = usuario_autenticado["usuario"]["id"]
    assert wid not in [w["id"] for w in client.get(f"/workflows/usuario/{uid}", headers=headers).json()]
    assert client.get(f"/workflows/{wid}", headers=headers).status_code == 404
    assert client.put(f"/workflows/{wid}", json={"nombre": "x", "descripcion": "", "grafo_json": GRAFO_B},
                      headers=headers).status_code == 404
    assert client.post(f"/workflows/{wid}/ejecutar", headers=headers).status_code == 404
    assert client.get(f"/workflows/{wid}/ejecuciones", headers=headers).status_code == 404
    assert client.delete(f"/workflows/{wid}", headers=headers).status_code == 404


def test_borrar_un_workflow_conserva_sus_resultados(client, db_session, mock_celery, usuario_autenticado):
    headers = usuario_autenticado["headers"]
    uid = usuario_autenticado["usuario"]["id"]
    wid = _workflow(client, headers)
    eid = _ejecutar(client, headers, wid)
    nombre = f"test_salida_012_e{eid}.sdf"
    _fichero_de_resultado(db_session, uid, eid, nombre)

    assert client.delete(f"/workflows/{wid}", headers=headers).status_code == 200

    fila = next(e for e in client.get(f"/ejecuciones/usuario/{uid}", headers=headers).json() if e["id"] == eid)
    assert fila["workflow_nombre"] == "wf 012"
    assert fila["workflow_borrado"] is True
    assert client.get(f"/uploads/{nombre}", headers=headers).status_code == 200
    datos = client.get(f"/workflows/ejecuciones/{eid}", headers=headers).json()
    assert datos["grafo_json"] == GRAFO_A
    assert datos["workflow_borrado"] is True


def test_una_ejecucion_en_marcha_de_un_workflow_borrado_termina(db_session, usuario_autenticado, monkeypatch):
    from datetime import datetime

    from app import tasks
    workflow, ejecucion = _ejecucion_con_copia(db_session, usuario_autenticado["usuario"]["id"])
    workflow.borrado_en = datetime.utcnow()
    db_session.commit()
    grafos = []
    monkeypatch.setattr(tasks, "WorkflowExecutor", _executor_espia(grafos))
    monkeypatch.setattr(tasks, "_vigia_cancelacion", lambda _id: lambda: False)

    tasks.ejecutar_workflow_async(workflow.id, workflow.usuario_id, ejecucion.id)

    db_session.refresh(ejecucion)
    assert grafos == [COPIA]
    assert ejecucion.estado == "completado"


def test_sistema_no_cuenta_los_workflows_borrados(client, usuario_autenticado, admin_autenticado):
    def total():
        r = client.get("/sistema/estado", headers=admin_autenticado["headers"])
        assert r.status_code == 200, r.text
        return r.json()["workflows"]["total"]

    antes = total()
    wid = _workflow(client, usuario_autenticado["headers"])
    assert total() == antes + 1
    client.delete(f"/workflows/{wid}", headers=usuario_autenticado["headers"])
    assert total() == antes


# --- R3. Borrar los resultados de una ejecucion (CA6) ------------------------

def _terminada(db_session, ejecucion_id):
    ejecucion = db_session.get(models.WorkflowExecution, ejecucion_id)
    ejecucion.estado = "completado"
    db_session.commit()


def test_borrar_una_ejecucion_se_lleva_sus_ficheros(client, db_session, mock_celery, usuario_autenticado):
    """
    Con ficheros registrados contra la ejecucion, que es el caso delicado:
    borrar_archivos_registrados() solo MARCA sus filas (db.delete) y, sin un
    flush antes de borrar la ejecucion, PostgreSQL rechazaba el borrado por la
    clave ajena archivos_ejecucion_id_fkey (paso con el borrado de workflows).
    """
    import os
    headers = usuario_autenticado["headers"]
    uid = usuario_autenticado["usuario"]["id"]
    wid = _workflow(client, headers)
    eid = _ejecutar(client, headers, wid)
    _terminada(db_session, eid)
    nombre = f"test_salida_012_borrar_e{eid}.sdf"
    _fichero_de_resultado(db_session, uid, eid, nombre)

    r = client.delete(f"/workflows/ejecuciones/{eid}", headers=headers)

    assert r.status_code == 200, r.text
    assert client.get(f"/workflows/ejecuciones/{eid}", headers=headers).status_code == 404
    assert eid not in [e["id"] for e in client.get(f"/ejecuciones/usuario/{uid}", headers=headers).json()]
    db_session.expire_all()
    assert db_session.query(models.Archivo).filter(models.Archivo.nombre == nombre).first() is None
    assert not os.path.exists(os.path.join("uploads", nombre))
    # El workflow no estaba borrado: sigue ahi.
    assert client.get(f"/workflows/{wid}", headers=headers).status_code == 200


def test_no_se_borra_la_ejecucion_de_otro(client, db_session, mock_celery, usuario_autenticado,
                                          otro_usuario_autenticado):
    headers = usuario_autenticado["headers"]
    eid = _ejecutar(client, headers, _workflow(client, headers))
    _terminada(db_session, eid)

    assert client.delete(f"/workflows/ejecuciones/{eid}",
                         headers=otro_usuario_autenticado["headers"]).status_code == 403
    assert client.delete("/workflows/ejecuciones/999999", headers=headers).status_code == 404
    assert client.get(f"/workflows/ejecuciones/{eid}", headers=headers).status_code == 200


def test_no_se_borra_una_ejecucion_en_marcha(client, mock_celery, usuario_autenticado):
    headers = usuario_autenticado["headers"]
    eid = _ejecutar(client, headers, _workflow(client, headers))   # queda "pendiente"

    r = client.delete(f"/workflows/ejecuciones/{eid}", headers=headers)

    assert r.status_code == 409
    assert r.json()["detail"] == "Esta ejecución sigue en marcha. Cancélala antes de borrarla."


def test_la_ultima_ejecucion_de_un_workflow_borrado_se_lo_lleva(
    client, db_session, mock_celery, usuario_autenticado
):
    headers = usuario_autenticado["headers"]
    wid = _workflow(client, headers)
    primera, segunda = _ejecutar(client, headers, wid), _ejecutar(client, headers, wid)
    _terminada(db_session, primera)
    _terminada(db_session, segunda)
    client.delete(f"/workflows/{wid}", headers=headers)

    assert client.delete(f"/workflows/ejecuciones/{primera}", headers=headers).status_code == 200
    db_session.expire_all()
    assert db_session.get(models.Workflow, wid) is not None   # le queda una

    assert client.delete(f"/workflows/ejecuciones/{segunda}", headers=headers).status_code == 200
    db_session.expire_all()
    assert db_session.get(models.Workflow, wid) is None
