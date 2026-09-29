"""
Tests del registro de propiedad de ficheros (tabla `archivos`).

Cubren los tres defectos que compartian la misma raiz --que uploads/ fuera un
cajon plano sin dueno-- y que se cerraron juntos:

  S2  los resultados de un workflow no constaban en ninguna tabla, asi que
      caian en el "deposito compartido" y CUALQUIER usuario autenticado podia
      descargarlos y borrarlos.
  S3  dos subidas con el mismo nombre se pisaban en silencio, de modo que la
      peticion pendiente del primer usuario pasaba a ejecutarse sobre los
      datos del segundo.
  C5  los nombres de salida se derivaban solo del id del nodo, constante para
      un workflow dado, asi que dos ejecuciones concurrentes se sobrescribian.
"""
import os

from app import models


CONTENIDO_MOL2_DUMMY = b"@<TRIPOS>MOLECULE\ndummy\n1 0 0 0 0\nSMALL\nNO_CHARGES\n"


def _subir(client, headers, nombre):
    return client.post(
        "/moleculas/subir",
        data={"tipo": "molecula"},
        files={"archivo": (nombre, CONTENIDO_MOL2_DUMMY, "chemical/x-mol2")},
        headers=headers,
    )


# --------------------------------------------------------------------- S3
def test_dos_subidas_con_el_mismo_nombre_no_se_pisan(
    client, usuario_autenticado, otro_usuario_autenticado
):
    nombre = "test_dummy_colision.mol2"

    primera = _subir(client, usuario_autenticado["headers"], nombre)
    assert primera.status_code == 200
    assert primera.json()["nombre"] == nombre

    segunda = _subir(client, otro_usuario_autenticado["headers"], nombre)
    assert segunda.status_code == 200
    nombre_2 = segunda.json()["nombre"]

    # Lo esencial: la segunda subida NO se llama igual que la primera, asi que
    # el fichero del primer usuario sigue intacto.
    assert nombre_2 != nombre, "la segunda subida sobrescribio a la primera"
    assert os.path.exists(os.path.join("uploads", nombre))
    assert os.path.exists(os.path.join("uploads", nombre_2))


# --------------------------------------------------------------------- S2
def test_el_resultado_de_otro_usuario_no_se_puede_descargar(
    client, db_session, usuario_autenticado, otro_usuario_autenticado
):
    """Un fichero marcado como resultado es privado de su propietario."""
    nombre = "test_dummy_resultado_ajeno.sdf"
    ruta = os.path.join("uploads", nombre)
    with open(ruta, "wb") as f:
        f.write(b"resultado de un workflow\n")

    db_session.add(models.Archivo(
        nombre=nombre,
        visibilidad=models.VisibilidadArchivo.resultado,
        propietario_id=usuario_autenticado["usuario"]["id"],
        tamano_bytes=os.path.getsize(ruta),
    ))
    db_session.commit()

    ajeno = client.get(f"/uploads/{nombre}", headers=otro_usuario_autenticado["headers"])
    assert ajeno.status_code == 403, "un resultado ajeno no debe ser descargable"

    propio = client.get(f"/uploads/{nombre}", headers=usuario_autenticado["headers"])
    assert propio.status_code == 200


def test_el_resultado_de_otro_usuario_no_se_puede_borrar(
    client, db_session, usuario_autenticado, otro_usuario_autenticado
):
    nombre = "test_dummy_resultado_borrado.sdf"
    ruta = os.path.join("uploads", nombre)
    with open(ruta, "wb") as f:
        f.write(b"resultado de un workflow\n")

    db_session.add(models.Archivo(
        nombre=nombre,
        visibilidad=models.VisibilidadArchivo.resultado,
        propietario_id=usuario_autenticado["usuario"]["id"],
    ))
    db_session.commit()

    ajeno = client.delete(f"/moleculas/{nombre}", headers=otro_usuario_autenticado["headers"])
    assert ajeno.status_code == 403
    assert os.path.exists(ruta), "el fichero se borro pese al 403"


def test_el_resultado_de_otro_usuario_no_aparece_en_el_listado(
    client, db_session, usuario_autenticado, otro_usuario_autenticado
):
    nombre = "test_dummy_resultado_oculto.sdf"
    with open(os.path.join("uploads", nombre), "wb") as f:
        f.write(b"privado\n")
    db_session.add(models.Archivo(
        nombre=nombre,
        visibilidad=models.VisibilidadArchivo.resultado,
        propietario_id=usuario_autenticado["usuario"]["id"],
    ))
    db_session.commit()

    ajeno = client.get("/moleculas?limit=500", headers=otro_usuario_autenticado["headers"])
    assert ajeno.status_code == 200
    assert nombre not in [m["nombre"] for m in ajeno.json()]

    propio = client.get("/moleculas?limit=500", headers=usuario_autenticado["headers"])
    assert nombre in [m["nombre"] for m in propio.json()]


def test_la_biblioteca_sigue_siendo_compartida(
    client, usuario_autenticado, otro_usuario_autenticado
):
    """
    Cerrar S2 no debe romper el caso de uso legitimo: reutilizar una base de
    datos que subio un companero.
    """
    subida = _subir(client, usuario_autenticado["headers"], "test_dummy_compartida.mol2")
    nombre = subida.json()["nombre"]

    ajeno = client.get(f"/uploads/{nombre}", headers=otro_usuario_autenticado["headers"])
    assert ajeno.status_code == 200, "la biblioteca debe seguir siendo compartida"

    listado = client.get("/moleculas?limit=500", headers=otro_usuario_autenticado["headers"])
    assert nombre in [m["nombre"] for m in listado.json()]


def test_solo_el_propietario_borra_su_fichero_de_biblioteca(
    client, usuario_autenticado, otro_usuario_autenticado
):
    subida = _subir(client, usuario_autenticado["headers"], "test_dummy_biblio_borrado.mol2")
    nombre = subida.json()["nombre"]

    ajeno = client.delete(f"/moleculas/{nombre}", headers=otro_usuario_autenticado["headers"])
    assert ajeno.status_code == 403

    propio = client.delete(f"/moleculas/{nombre}", headers=usuario_autenticado["headers"])
    assert propio.status_code == 200


# --------------------------------------------------------------------- C5
def test_dos_ejecuciones_del_mismo_flujo_no_comparten_nombres_de_salida():
    """
    Los nombres de salida incorporan el id de la ejecucion. Antes se derivaban
    solo del id del nodo --constante para un workflow dado--, asi que dos
    ejecuciones simultaneas escribian sobre el mismo fichero.
    """
    from app.workflow_executor import WorkflowExecutor

    grafo = {"nodes": [], "edges": []}
    a = WorkflowExecutor(grafo, usuario_id=1, ejecucion_id=11)
    b = WorkflowExecutor(grafo, usuario_id=1, ejecucion_id=12)

    assert a.token != b.token
    assert f"comparacion_nodo1{a.token}.json" != f"comparacion_nodo1{b.token}.json"


def test_en_lote_cada_molecula_tiene_su_propio_sufijo():
    """
    Dentro de una misma ejecucion las N moleculas recorren los MISMOS nodos,
    asi que el id de ejecucion por si solo no basta para distinguirlas.
    """
    from app.workflow_executor import WorkflowExecutor

    grafo = {"nodes": [], "edges": []}
    tokens = {
        WorkflowExecutor(grafo, 1, ejecucion_id=7, sufijo_extra=f"m{i}").token
        for i in range(5)
    }
    assert len(tokens) == 5, "las moleculas de un lote comparten nombre de salida"
