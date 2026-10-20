"""
Spec 014, R7: los errores de la API llegan en el idioma que pide el frontend
con `Accept-Language`, y sin la cabecera, igual que siempre.
"""
from app import main
from app.banco_pruebas import ResultadoPrueba


def test_el_login_fallido_llega_en_ingles_con_accept_language(client):
    datos = {"email": "nadie@ejemplo.com", "password_hash": "x" * 10}
    en = client.post("/login", json=datos, headers={"Accept-Language": "en"})
    es = client.post("/login", json=datos)
    assert en.status_code == es.status_code == 400
    assert en.json()["detail"] == "Incorrect credentials"
    assert es.json()["detail"] == "Credenciales incorrectas"


def test_el_rechazo_del_banco_se_traduce_menos_la_salida(client, usuario_autenticado, monkeypatch):
    """El detail de 422 del banco es un diccionario: se traduce cada texto, no `salida` ni `detalle`."""
    rechazo = ResultadoPrueba()
    rechazo.motivo = ("El algoritmo terminó con error al ejecutarlo sobre las moléculas de "
                      "referencia. Se ejecutó así: a.py Molécula salida.sdf")
    rechazo.detalle = "Traceback: nada"
    rechazo.log = "Salida en español del script"
    monkeypatch.setattr(main, "probar_algoritmo", lambda *a, **k: rechazo)

    resp = client.post(
        "/algoritmos",
        data={"nombre": "x", "descripcion": "x", "tipo": "preprocesado", "es_publico": "true"},
        files={"archivo": ("idioma_banco.py", b"print(1)\n", "text/x-python")},
        headers={**usuario_autenticado["headers"], "Accept-Language": "en"},
    )
    assert resp.status_code == 422
    detalle = resp.json()["detail"]
    assert detalle["mensaje"] == "The algorithm did not pass the validation test."
    assert detalle["motivo"].startswith("The algorithm finished with an error")
    assert detalle["motivo"].endswith("a.py Molécula salida.sdf")
    assert detalle["salida"] == "Salida en español del script"
    assert detalle["detalle"] == "Traceback: nada"


def test_los_errores_de_una_ejecucion_llegan_en_ingles(client, usuario_autenticado, db_session):
    """El panel de resultados del Constructor enseña `resultados_json.errores` tal cual."""
    from app import models

    usuario_id = usuario_autenticado["usuario"]["id"]
    workflow = models.Workflow(nombre="idioma", grafo_json={"nodes": [], "edges": []}, usuario_id=usuario_id)
    db_session.add(workflow)
    db_session.commit()
    errores = ["Error en nodo UPLOAD upload_1: Nodo upload_1: no se ha subido ninguna molécula",
               "Un error que nadie ha traducido"]
    ejecucion = models.WorkflowExecution(workflow_id=workflow.id, usuario_id=usuario_id, estado="error",
                                         resultados_json={"estado": "error", "errores": list(errores)})
    db_session.add(ejecucion)
    db_session.commit()

    ruta = f"/workflows/ejecuciones/{ejecucion.id}"
    en = client.get(ruta, headers={**usuario_autenticado["headers"], "Accept-Language": "en"}).json()
    es = client.get(ruta, headers=usuario_autenticado["headers"]).json()
    assert en["resultados_json"]["errores"] == [
        "Error in node UPLOAD upload_1: Node upload_1: no molecule has been uploaded",
        "Un error que nadie ha traducido",
    ]
    assert es["resultados_json"]["errores"] == errores
