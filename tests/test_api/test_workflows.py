"""Tests de integracion: /workflows* (app/main.py), con JWT y Celery simulado."""
import pytest

from app import models


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


def test_obtener_workflow_ajeno_devuelve_403(client, usuario_autenticado, otro_usuario_autenticado):
    workflow_id = _crear_workflow(client, usuario_autenticado["headers"])
    respuesta = client.get(f"/workflows/{workflow_id}", headers=otro_usuario_autenticado["headers"])
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


def test_actualizar_workflow_ajeno_devuelve_403(client, usuario_autenticado, otro_usuario_autenticado):
    workflow_id = _crear_workflow(client, usuario_autenticado["headers"])
    respuesta = client.put(
        f"/workflows/{workflow_id}",
        json={"nombre": "hackeado", "descripcion": "", "grafo_json": {"nodes": [], "edges": []}},
        headers=otro_usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 403


def test_listar_workflows_de_usuario_ajeno_devuelve_403(client, usuario_autenticado, otro_usuario_autenticado):
    _crear_workflow(client, usuario_autenticado["headers"])
    respuesta = client.get(
        f"/workflows/usuario/{usuario_autenticado['usuario']['id']}",
        headers=otro_usuario_autenticado["headers"],
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
    client, usuario_autenticado, otro_usuario_autenticado
):
    headers = usuario_autenticado["headers"]
    workflow_id = _crear_workflow(client, headers)

    assert client.delete(f"/workflows/{workflow_id}", headers=otro_usuario_autenticado["headers"]).status_code == 403
    assert client.delete(f"/workflows/{workflow_id}", headers=headers).status_code == 200
    assert client.get(f"/workflows/{workflow_id}", headers=headers).status_code == 404


def test_borrar_workflow_ya_ejecutado_se_lleva_sus_ficheros(
    client, db_session, usuario_autenticado
):
    """
    Borrar un workflow QUE SE HA EJECUTADO, que es el caso que fallaba.

    El test de arriba borra uno recien creado, sin ninguna ejecucion, asi que
    `ids_ejecuciones` sale vacio y no se llega a la parte rota. Con una
    ejecucion que dejo ficheros, borrar_archivos_registrados() marcaba las
    filas de `archivos` con db.delete() --que solo las encola hasta vaciar la
    sesion-- y la linea siguiente las intentaba dejar huerfanas con un
    Query.delete() que se ejecuta al instante: PostgreSQL rechazaba el borrado
    de workflow_executions por la clave ajena archivos_ejecucion_id_fkey y el
    endpoint devolvia un 500. Es decir: ningun workflow realmente usado se
    podia borrar.
    """
    import os

    from app import models

    headers = usuario_autenticado["headers"]
    workflow_id = _crear_workflow(client, headers)

    ejecucion = models.WorkflowExecution(
        workflow_id=workflow_id,
        usuario_id=usuario_autenticado["usuario"]["id"],
        estado="completado",
    )
    db_session.add(ejecucion)
    db_session.commit()
    db_session.refresh(ejecucion)
    # El id, a una variable suelta: tras el borrado el objeto queda obsoleto y
    # leerle un atributo dispararia un refresco contra una fila que ya no esta.
    ejecucion_id = ejecucion.id

    # Un fichero de salida real, registrado contra esa ejecucion: es la fila
    # que sostiene la clave ajena.
    nombre = f"test_dummy_salida_wf{workflow_id}.sdf"
    with open(os.path.join("uploads", nombre), "wb") as f:
        f.write(b"resultado\n$$$$\n")
    db_session.add(models.Archivo(
        nombre=nombre,
        visibilidad=models.VisibilidadArchivo.resultado,
        tipo=models.TipoArchivo.resultado,
        propietario_id=usuario_autenticado["usuario"]["id"],
        ejecucion_id=ejecucion_id,
    ))
    db_session.commit()

    respuesta = client.delete(f"/workflows/{workflow_id}", headers=headers)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["archivos_borrados"] == 1

    # Y no queda nada suelto: ni el workflow, ni su ejecucion, ni el fichero.
    assert client.get(f"/workflows/{workflow_id}", headers=headers).status_code == 404
    db_session.expire_all()
    assert db_session.query(models.WorkflowExecution).filter(
        models.WorkflowExecution.id == ejecucion_id).first() is None
    assert db_session.query(models.Archivo).filter(
        models.Archivo.nombre == nombre).first() is None
    assert not os.path.exists(os.path.join("uploads", nombre))


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


def test_ejecutar_workflow_ajeno_devuelve_403(client, mock_celery, usuario_autenticado, otro_usuario_autenticado):
    workflow_id = _crear_workflow(client, usuario_autenticado["headers"])
    respuesta = client.post(f"/workflows/{workflow_id}/ejecutar", headers=otro_usuario_autenticado["headers"])
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


def test_listar_ejecuciones_de_usuario_ajeno_devuelve_403(client, usuario_autenticado, otro_usuario_autenticado):
    respuesta = client.get(
        f"/ejecuciones/usuario/{usuario_autenticado['usuario']['id']}",
        headers=otro_usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 403


def test_listar_ejecuciones_de_usuario_propio(client, usuario_autenticado):
    respuesta = client.get(
        f"/ejecuciones/usuario/{usuario_autenticado['usuario']['id']}",
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 200


def test_cancelar_ejecucion_ajena_devuelve_404(
    client, mock_celery, usuario_autenticado, otro_usuario_autenticado, db_session
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
        f"/workflows/ejecuciones/{ejecucion.id}/cancelar", headers=otro_usuario_autenticado["headers"]
    )
    assert respuesta.status_code == 404


# ---------------------------------------------------------------------------
# El grafo lo manda el cliente, asi que puede nombrar CUALQUIER fichero de
# uploads/. Ser dueno del workflow no dice nada sobre las moleculas que usa.
#
# Antes el motor resolvia os.path.join("uploads", nombre) sin comprobar nada
# (app/workflow_executor.py), de modo que bastaba con poner en un nodo el
# nombre del resultado de otro usuario --enumerables: docking_<nodo>_e<id>.sdf--
# para que la plataforma lo leyera y devolviera su contenido como resultado
# propio. La comprobacion vive ahora en app/permisos.py y la aplican tanto el
# endpoint que encola como la tarea del worker.
# ---------------------------------------------------------------------------

def _registrar_archivo(db_session, nombre, propietario_id, visibilidad):
    from app import models
    db_session.add(models.Archivo(
        nombre=nombre,
        visibilidad=models.VisibilidadArchivo(visibilidad),
        propietario_id=propietario_id,
        tamano_bytes=10,
    ))
    db_session.commit()


def _workflow_con_archivo(client, headers, nombre_archivo, tipo="selectMol") -> int:
    workflow_id = _crear_workflow(client, headers)
    client.put(
        f"/workflows/{workflow_id}",
        json={
            "nombre": "Workflow con molécula ajena",
            "descripcion": "",
            "grafo_json": {
                "nodes": [{"id": "n1", "type": tipo, "data": {"nombre_archivo": nombre_archivo}}],
                "edges": [],
            },
        },
        headers=headers,
    )
    return workflow_id


def test_ejecutar_workflow_que_usa_resultado_ajeno_devuelve_403(
    client, db_session, mock_celery, usuario_autenticado, otro_usuario_autenticado
):
    nombre = "docking_n1_e99999.sdf"
    _registrar_archivo(db_session, nombre, otro_usuario_autenticado["usuario"]["id"], "resultado")

    workflow_id = _workflow_con_archivo(client, usuario_autenticado["headers"], nombre)
    respuesta = client.post(f"/workflows/{workflow_id}/ejecutar", headers=usuario_autenticado["headers"])

    assert respuesta.status_code == 403
    assert nombre in respuesta.json()["detail"]
    # Y, sobre todo, no se ha encolado nada: no llega a abrirse el fichero.
    assert len(mock_celery) == 0


def test_ejecutar_workflow_batch_que_usa_resultado_ajeno_devuelve_403(
    client, db_session, mock_celery, usuario_autenticado, otro_usuario_autenticado
):
    """La ruta batch (selectDB) resolvia el SDF por su cuenta, aparte de selectMol."""
    nombre = "cribado_ajeno_e99998.sdf"
    _registrar_archivo(db_session, nombre, otro_usuario_autenticado["usuario"]["id"], "resultado")

    workflow_id = _workflow_con_archivo(client, usuario_autenticado["headers"], nombre, tipo="selectDB")
    respuesta = client.post(f"/workflows/{workflow_id}/ejecutar", headers=usuario_autenticado["headers"])

    assert respuesta.status_code == 403
    assert len(mock_celery) == 0


def test_ejecutar_workflow_con_molecula_de_la_biblioteca_ajena_sigue_permitido(
    client, db_session, mock_celery, usuario_autenticado, otro_usuario_autenticado
):
    """
    La biblioteca es compartida a proposito --es lo que permite reutilizar una
    base de datos subida por un companero-- y esto no lo cambia. Si algun dia
    se cierra, este test es el que hay que cambiar, a la vista.
    """
    nombre = "biblioteca_compartida_test.sdf"
    _registrar_archivo(db_session, nombre, otro_usuario_autenticado["usuario"]["id"], "biblioteca")

    workflow_id = _workflow_con_archivo(client, usuario_autenticado["headers"], nombre)
    respuesta = client.post(f"/workflows/{workflow_id}/ejecutar", headers=usuario_autenticado["headers"])

    assert respuesta.status_code == 200
    assert len(mock_celery) == 1


def test_ejecutar_workflow_con_resultado_propio_sigue_permitido(
    client, db_session, mock_celery, usuario_autenticado
):
    nombre = "resultado_propio_e99997.sdf"
    _registrar_archivo(db_session, nombre, usuario_autenticado["usuario"]["id"], "resultado")

    workflow_id = _workflow_con_archivo(client, usuario_autenticado["headers"], nombre)
    respuesta = client.post(f"/workflows/{workflow_id}/ejecutar", headers=usuario_autenticado["headers"])

    assert respuesta.status_code == 200
    assert len(mock_celery) == 1


def test_admin_puede_ejecutar_un_flujo_con_resultado_ajeno(
    client, db_session, mock_celery, admin_autenticado, usuario_autenticado
):
    """El admin ya ve los ficheros de todos; el motor no es una excepcion."""
    nombre = "docking_n1_e99996.sdf"
    _registrar_archivo(db_session, nombre, usuario_autenticado["usuario"]["id"], "resultado")

    workflow_id = _workflow_con_archivo(client, admin_autenticado["headers"], nombre)
    respuesta = client.post(f"/workflows/{workflow_id}/ejecutar", headers=admin_autenticado["headers"])

    assert respuesta.status_code == 200


def test_el_inventario_del_sdf_cuenta_los_registros_ilegibles(tmp_path):
    """
    Un cribado tiene que decir cuantas moleculas se ha dejado por el camino.

    Antes solo se contaban las parseables, asi que una biblioteca con
    registros defectuosos --lo normal en ZINC o Enamine-- se cribaba a medias
    y el informe decia "N procesadas, 0 errores, exito". El total se cuenta
    por separadores ($$$$) y no por lo que itere SDMolSupplier, porque ante un
    registro malformado RDKit salta al siguiente separador y se come alguno:
    su recuento ya viene mermado y ocultaria justo lo que se quiere contar.
    """
    from app.workflow_executor import BatchWorkflowExecutor

    bueno = "mol{}\n\n\n  0  0\nM  END\n$$$$\n"
    roto = "corrupto\n  esto no es un molfile\n$$$$\n"
    sdf = tmp_path / "mezcla.sdf"
    sdf.write_text(bueno.format(1) + roto + bueno.format(2) + roto + bueno.format(3),
                   encoding="utf-8")

    indices, total = BatchWorkflowExecutor.inventario_sdf(str(sdf))

    assert total == 5, f"el fichero tiene 5 registros, se contaron {total}"
    assert len(indices) < total, "los registros corruptos no deben contar como validos"
    assert total - len(indices) > 0, "tiene que quedar constancia de los descartados"


# ---------------------------------------------------------------------------
# Cancelacion de un workflow normal, dentro de la tarea
# ---------------------------------------------------------------------------

def _workflow_con_ejecucion(db_session, usuario_id):
    workflow = models.Workflow(nombre="wf cancelable", descripcion="",
                               grafo_json={"nodes": [], "edges": []}, usuario_id=usuario_id)
    db_session.add(workflow)
    db_session.commit()
    ejecucion = models.WorkflowExecution(workflow_id=workflow.id, usuario_id=usuario_id,
                                         estado="pendiente")
    db_session.add(ejecucion)
    db_session.commit()
    return workflow, ejecucion


def test_un_workflow_cancelado_a_mitad_acaba_cancelado_y_sin_correo(
    db_session, usuario_autenticado, correos_enviados, monkeypatch
):
    """
    El endpoint deja la ejecucion en "cancelado", pero el final de la tarea lo
    sobrescribia con "completado" y mandaba el correo de un trabajo que el
    usuario habia cancelado.
    """
    from app import tasks

    usuario_id = usuario_autenticado["usuario"]["id"]
    workflow, ejecucion = _workflow_con_ejecucion(db_session, usuario_id)
    cancelado = []

    class ExecutorFalso:
        archivos_generados = []

        def __init__(self, *_a, **_kw):
            pass

        def ejecutar(self):
            cancelado.append(True)      # el usuario cancela mientras corre
            return {"estado": "completado", "exito": True, "errores": [],
                    "resultados": {}, "duracion_segundos": 1}

    monkeypatch.setattr(tasks, "WorkflowExecutor", ExecutorFalso)
    monkeypatch.setattr(tasks, "_vigia_cancelacion", lambda _id: lambda: bool(cancelado))

    tasks.ejecutar_workflow_async(workflow.id, usuario_id, ejecucion.id)

    db_session.refresh(ejecucion)
    assert ejecucion.estado == "cancelado"
    # El unico correo es el de verificacion del registro del usuario de test.
    assert not [c for c in correos_enviados if "orkflow" in c["asunto"]]


def test_un_workflow_cancelado_en_la_cola_no_llega_a_empezar(
    db_session, usuario_autenticado, monkeypatch
):
    from app import tasks

    usuario_id = usuario_autenticado["usuario"]["id"]
    workflow, ejecucion = _workflow_con_ejecucion(db_session, usuario_id)
    monkeypatch.setattr(tasks, "WorkflowExecutor",
                        lambda *a, **k: pytest.fail("no deberia ejecutarse"))
    monkeypatch.setattr(tasks, "_vigia_cancelacion", lambda _id: lambda: True)

    resultado = tasks.ejecutar_workflow_async(workflow.id, usuario_id, ejecucion.id)

    assert resultado["estado"] == "cancelado"
