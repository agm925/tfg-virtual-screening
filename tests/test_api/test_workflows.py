"""Tests de integracion: /workflows* (app/main.py), con JWT y Celery simulado."""


def _crear_workflow(client, headers) -> int:
    respuesta = client.post(
        "/workflows",
        data={"nombre": "Workflow de test", "descripcion": "Creado por la suite de tests"},
        headers=headers,
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["id"]


def test_crear_workflow_sin_token_devuelve_401(client):
    respuesta = client.post("/workflows", data={"nombre": "x", "descripcion": "y"})
    assert respuesta.status_code == 401


def test_crear_y_obtener_workflow_vacio(client, usuario_autenticado):
    headers = usuario_autenticado["headers"]
    workflow_id = _crear_workflow(client, headers)
    respuesta = client.get(f"/workflows/{workflow_id}", headers=headers)
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["grafo_json"] == {"nodes": [], "edges": []}
    assert cuerpo["estado"] == "borrador"
    assert cuerpo["usuario_id"] == usuario_autenticado["usuario"]["id"]


def test_obtener_workflow_ajeno_devuelve_403(client, usuario_autenticado, desarrollador_autenticado):
    workflow_id = _crear_workflow(client, usuario_autenticado["headers"])
    respuesta = client.get(f"/workflows/{workflow_id}", headers=desarrollador_autenticado["headers"])
    assert respuesta.status_code == 403


def test_obtener_workflow_inexistente_devuelve_404(client, usuario_autenticado):
    respuesta = client.get("/workflows/999999", headers=usuario_autenticado["headers"])
    assert respuesta.status_code == 404


def test_actualizar_workflow_guarda_el_grafo(client, usuario_autenticado):
    headers = usuario_autenticado["headers"]
    workflow_id = _crear_workflow(client, headers)
    grafo = {
        "nodes": [{"id": "n1", "type": "selectMol", "data": {"nombre_archivo": "x.mol2"}}],
        "edges": [],
    }
    respuesta = client.put(
        f"/workflows/{workflow_id}",
        json={"nombre": "Workflow actualizado", "descripcion": "desc", "grafo_json": grafo},
        headers=headers,
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["grafo_json"] == grafo


def test_actualizar_workflow_ajeno_devuelve_403(client, usuario_autenticado, desarrollador_autenticado):
    workflow_id = _crear_workflow(client, usuario_autenticado["headers"])
    respuesta = client.put(
        f"/workflows/{workflow_id}",
        json={"nombre": "hackeado", "descripcion": "", "grafo_json": {"nodes": [], "edges": []}},
        headers=desarrollador_autenticado["headers"],
    )
    assert respuesta.status_code == 403


def test_listar_workflows_de_usuario_ajeno_devuelve_403(client, usuario_autenticado, desarrollador_autenticado):
    _crear_workflow(client, usuario_autenticado["headers"])
    respuesta = client.get(
        f"/workflows/usuario/{usuario_autenticado['usuario']['id']}",
        headers=desarrollador_autenticado["headers"],
    )
    assert respuesta.status_code == 403


def test_listar_workflows_de_usuario_propio(client, usuario_autenticado):
    headers = usuario_autenticado["headers"]
    workflow_id = _crear_workflow(client, headers)
    respuesta = client.get(f"/workflows/usuario/{usuario_autenticado['usuario']['id']}", headers=headers)
    assert respuesta.status_code == 200
    ids = [w["id"] for w in respuesta.json()]
    assert workflow_id in ids


def test_borrar_workflow_ajeno_devuelve_403_y_propio_funciona(
    client, usuario_autenticado, desarrollador_autenticado
):
    headers = usuario_autenticado["headers"]
    workflow_id = _crear_workflow(client, headers)

    assert client.delete(f"/workflows/{workflow_id}", headers=desarrollador_autenticado["headers"]).status_code == 403
    assert client.delete(f"/workflows/{workflow_id}", headers=headers).status_code == 200
    assert client.get(f"/workflows/{workflow_id}", headers=headers).status_code == 404


def test_ejecutar_workflow_sin_selectdb_es_modo_normal(client, mock_celery, usuario_autenticado):
    headers = usuario_autenticado["headers"]
    workflow_id = _crear_workflow(client, headers)
    client.put(
        f"/workflows/{workflow_id}",
        json={
            "nombre": "Workflow normal",
            "descripcion": "",
            "grafo_json": {
                "nodes": [{"id": "n1", "type": "selectMol", "data": {"nombre_archivo": "x.mol2"}}],
                "edges": [],
            },
        },
        headers=headers,
    )
    respuesta = client.post(f"/workflows/{workflow_id}/ejecutar", headers=headers)
    assert respuesta.status_code == 200
    assert respuesta.json()["modo"] == "normal"
    assert len(mock_celery) == 1


def test_ejecutar_workflow_con_selectdb_activa_modo_batch(client, mock_celery, usuario_autenticado):
    headers = usuario_autenticado["headers"]
    workflow_id = _crear_workflow(client, headers)
    client.put(
        f"/workflows/{workflow_id}",
        json={
            "nombre": "Workflow batch",
            "descripcion": "",
            "grafo_json": {
                "nodes": [{"id": "n1", "type": "selectDB", "data": {"nombre_archivo": "biblioteca.sdf"}}],
                "edges": [],
            },
        },
        headers=headers,
    )
    respuesta = client.post(f"/workflows/{workflow_id}/ejecutar", headers=headers)
    assert respuesta.status_code == 200
    assert respuesta.json()["modo"] == "batch"
    assert len(mock_celery) == 1


def test_ejecutar_workflow_ajeno_devuelve_403(client, mock_celery, usuario_autenticado, desarrollador_autenticado):
    workflow_id = _crear_workflow(client, usuario_autenticado["headers"])
    respuesta = client.post(f"/workflows/{workflow_id}/ejecutar", headers=desarrollador_autenticado["headers"])
    assert respuesta.status_code == 403
    assert len(mock_celery) == 0


def test_ejecutar_workflow_inexistente_devuelve_404(client, mock_celery, usuario_autenticado):
    respuesta = client.post("/workflows/999999/ejecutar", headers=usuario_autenticado["headers"])
    assert respuesta.status_code == 404


def test_cancelar_ejecucion_ya_completada_devuelve_400(client, mock_celery, usuario_autenticado, db_session):
    from app import models

    headers = usuario_autenticado["headers"]
    workflow_id = _crear_workflow(client, headers)
    ejecucion = models.WorkflowExecution(
        workflow_id=workflow_id, usuario_id=usuario_autenticado["usuario"]["id"], estado="completado"
    )
    db_session.add(ejecucion)
    db_session.commit()
    db_session.refresh(ejecucion)

    respuesta = client.post(f"/workflows/ejecuciones/{ejecucion.id}/cancelar", headers=headers)
    assert respuesta.status_code == 400


def test_listar_ejecuciones_de_usuario_ajeno_devuelve_403(client, usuario_autenticado, desarrollador_autenticado):
    respuesta = client.get(
        f"/ejecuciones/usuario/{usuario_autenticado['usuario']['id']}",
        headers=desarrollador_autenticado["headers"],
    )
    assert respuesta.status_code == 403


def test_listar_ejecuciones_de_usuario_propio(client, usuario_autenticado):
    respuesta = client.get(
        f"/ejecuciones/usuario/{usuario_autenticado['usuario']['id']}",
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 200


def test_cancelar_ejecucion_ajena_devuelve_404(
    client, mock_celery, usuario_autenticado, desarrollador_autenticado, db_session
):
    from app import models

    workflow_id = _crear_workflow(client, usuario_autenticado["headers"])
    ejecucion = models.WorkflowExecution(
        workflow_id=workflow_id, usuario_id=usuario_autenticado["usuario"]["id"], estado="pendiente"
    )
    db_session.add(ejecucion)
    db_session.commit()
    db_session.refresh(ejecucion)

    # otro usuario no admin no deberia ni poder verla (se filtra en la query, no solo 403)
    respuesta = client.post(
        f"/workflows/ejecuciones/{ejecucion.id}/cancelar", headers=desarrollador_autenticado["headers"]
    )
    assert respuesta.status_code == 404
