"""
Spec 007: al subir una molecula o una biblioteca se elige si es publica o
privada. Una privada solo la ve su autor, NI SIQUIERA un administrador
(decision del usuario, 09/10/2026), y en ninguna parte: Moleculas, visor,
descarga, borrado, workflows ni panel de Administracion.
"""
import uuid

import pytest

SDF_DOS = b"mol1\n\n\n  0  0\nM  END\n$$$$\nmol2\n\n\n  0  0\nM  END\n$$$$\n"


def _subir(client, usuario, es_publico, tipo="base_de_datos"):
    nombre = f"test_dummy_visib_{uuid.uuid4().hex[:8]}.sdf"
    datos = {"tipo": tipo}
    if es_publico is not None:
        datos["es_publico"] = "true" if es_publico else "false"
    respuesta = client.post(
        "/moleculas/subir",
        files={"archivo": (nombre, SDF_DOS, "chemical/x-mdl-sdfile")},
        data=datos,
        headers=usuario["headers"],
    )
    return respuesta


def _nombre(respuesta):
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["nombre"]


def _en_moleculas(client, usuario, nombre):
    lista = client.get("/moleculas?limit=500", headers=usuario["headers"]).json()
    return next((m for m in lista if m["nombre"] == nombre), None)


def _en_visor(client, usuario, nombre):
    lista = client.get(f"/visor/ficheros?q={nombre}", headers=usuario["headers"]).json()
    return any(f["nombre"] == nombre for f in lista)


def _ejecutar_con(client, usuario, nombre):
    headers = usuario["headers"]
    creado = client.post("/workflows", data={"nombre": "w", "descripcion": ""}, headers=headers)
    workflow_id = creado.json()["id"]
    client.put(
        f"/workflows/{workflow_id}",
        json={"nombre": "w", "descripcion": "", "grafo_json": {
            "nodes": [{"id": "n1", "type": "selectDB", "data": {"nombre_archivo": nombre}}],
            "edges": [],
        }},
        headers=headers,
    )
    return client.post(f"/workflows/{workflow_id}/ejecutar", headers=headers)


# --- La subida ----------------------------------------------------------------

def test_subir_sin_elegir_visibilidad_da_422(client, usuario_autenticado):
    # Un cliente que no pregunte no publica nada sin querer (CA3).
    assert _subir(client, usuario_autenticado, None).status_code == 422


@pytest.mark.parametrize("es_publico", [True, False])
def test_la_subida_devuelve_la_visibilidad_elegida(client, usuario_autenticado, es_publico):
    respuesta = _subir(client, usuario_autenticado, es_publico)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["es_publico"] is es_publico


# --- Privada: solo el autor (CA1, CA4) ----------------------------------------

def test_el_autor_ve_y_usa_su_privada(client, mock_celery, usuario_autenticado):
    nombre = _nombre(_subir(client, usuario_autenticado, False))

    fila = _en_moleculas(client, usuario_autenticado, nombre)
    assert fila is not None and fila["es_publico"] is False
    assert _en_visor(client, usuario_autenticado, nombre)
    assert client.get(f"/uploads/{nombre}", headers=usuario_autenticado["headers"]).status_code == 200
    assert client.get(f"/visor/ficheros/{nombre}/moleculas",
                      headers=usuario_autenticado["headers"]).status_code == 200
    assert _ejecutar_con(client, usuario_autenticado, nombre).status_code == 200


@pytest.mark.parametrize("ajeno", ["otro_usuario_autenticado", "admin_autenticado"])
def test_nadie_mas_ve_ni_usa_una_privada(client, mock_celery, usuario_autenticado, ajeno, request):
    otro = request.getfixturevalue(ajeno)
    nombre = _nombre(_subir(client, usuario_autenticado, False))

    assert _en_moleculas(client, otro, nombre) is None
    assert not _en_visor(client, otro, nombre)
    assert client.get(f"/uploads/{nombre}", headers=otro["headers"]).status_code == 403
    assert client.get(f"/visor/ficheros/{nombre}/moleculas", headers=otro["headers"]).status_code == 404
    assert client.delete(f"/moleculas/{nombre}", headers=otro["headers"]).status_code == 403

    respuesta = _ejecutar_con(client, otro, nombre)
    assert respuesta.status_code == 403
    assert len(mock_celery) == 0


def test_el_admin_no_la_ve_en_su_panel(client, usuario_autenticado, admin_autenticado):
    nombre = _nombre(_subir(client, usuario_autenticado, False))
    lista = client.get("/admin/moleculas?limit=500", headers=admin_autenticado["headers"]).json()
    assert all(f["nombre"] != nombre for f in lista)


def test_el_admin_ve_su_propia_privada(client, admin_autenticado):
    nombre = _nombre(_subir(client, admin_autenticado, False))
    assert _en_moleculas(client, admin_autenticado, nombre) is not None
    lista = client.get("/admin/moleculas?limit=500", headers=admin_autenticado["headers"]).json()
    assert any(f["nombre"] == nombre for f in lista)


# --- Publica: como hasta ahora (CA2) ------------------------------------------

def test_una_publica_la_ve_y_usa_cualquiera(client, mock_celery, usuario_autenticado,
                                            otro_usuario_autenticado):
    nombre = _nombre(_subir(client, usuario_autenticado, True))
    otro = otro_usuario_autenticado

    fila = _en_moleculas(client, otro, nombre)
    assert fila is not None and fila["es_publico"] is True
    assert _en_visor(client, otro, nombre)
    assert client.get(f"/uploads/{nombre}", headers=otro["headers"]).status_code == 200
    assert _ejecutar_con(client, otro, nombre).status_code == 200
    # Borrarla sigue siendo cosa del autor o de un admin.
    assert client.delete(f"/moleculas/{nombre}", headers=otro["headers"]).status_code == 403


def test_una_publica_la_puede_borrar_un_admin(client, usuario_autenticado, admin_autenticado):
    nombre = _nombre(_subir(client, usuario_autenticado, True))
    assert client.delete(f"/moleculas/{nombre}", headers=admin_autenticado["headers"]).status_code == 200
