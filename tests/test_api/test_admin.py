"""
Tests de integracion: los endpoints /admin (app/main.py) y el efecto real de
la desactivacion.

Lo que se prueba aqui no es que un PATCH devuelva 200 --eso seria comprobar
que SQLAlchemy sabe escribir un booleano-- sino que desactivar SURTE EFECTO en
los caminos por los que se entra a la plataforma y por los que se ejecuta un
algoritmo. Una desactivacion que se guarda pero no impide nada es exactamente
el fallo silencioso que hace inutil un panel de administracion.
"""
import uuid

from app import models

# Mismo doble que usa test_peticiones.py: cumple el contrato del catalogo, de
# modo que el banco de pruebas lo acepta al subirlo.
SCRIPT_DUMMY = b"""# TIPO_ALGORITMO: preprocesado
import shutil
import sys

entrada, salida = sys.argv[1], sys.argv[-1]
shutil.copyfile(entrada, salida)
print("dummy: copiada la entrada a la salida")
"""
CONTENIDO_MOL2_DUMMY = b"@<TRIPOS>MOLECULE\ndummy\n1 0 0 0 0\nSMALL\nNO_CHARGES\n"


def _subir_algoritmo(client, sesion) -> int:
    respuesta = client.post(
        "/algoritmos",
        # es_publico como lo manda el frontend real (Algoritmos.jsx): estos
        # tests van de retirar y publicar algoritmos, no de su visibilidad,
        # y con el valor por defecto (privado) resolver_algoritmo los
        # rechazaria por un motivo que no es el que se esta probando.
        data={"nombre": f"Dummy admin {uuid.uuid4().hex[:6]}",
              "descripcion": "Para tests de administracion", "tipo": "preprocesado",
              "es_publico": "true"},
        files={"archivo": (f"test_admin_{uuid.uuid4().hex[:8]}.py", SCRIPT_DUMMY, "text/x-python")},
        headers=sesion["headers"],
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["id"]


# --- Acceso al panel -------------------------------------------------------

def test_biologo_no_accede_a_los_endpoints_de_administracion(client, usuario_autenticado):
    cabeceras = usuario_autenticado["headers"]
    assert client.get("/admin/usuarios", headers=cabeceras).status_code == 403
    assert client.get("/admin/moleculas", headers=cabeceras).status_code == 403
    assert client.patch("/admin/usuarios/1", json={"activo": False}, headers=cabeceras).status_code == 403
    assert client.patch("/admin/algoritmos/1", json={"activo": False}, headers=cabeceras).status_code == 403


def test_sin_token_los_endpoints_de_administracion_devuelven_401(client):
    assert client.get("/admin/usuarios").status_code == 401
    assert client.get("/admin/moleculas").status_code == 401


def test_admin_lista_usuarios_con_su_carga_de_trabajo(client, admin_autenticado, usuario_autenticado):
    respuesta = client.get("/admin/usuarios?limit=500", headers=admin_autenticado["headers"])
    assert respuesta.status_code == 200, respuesta.text
    por_id = {u["id"]: u for u in respuesta.json()}

    yo = por_id[admin_autenticado["usuario"]["id"]]
    assert yo["rol"] == "admin"
    assert yo["activo"] is True

    otro = por_id[usuario_autenticado["usuario"]["id"]]
    assert otro["rol"] == "biologo"
    # Los recuentos existen y son coherentes; el valor exacto depende de lo que
    # haya hecho el resto de la bateria sobre la misma base de datos.
    assert otro["n_algoritmos"] >= 0 and otro["n_peticiones"] >= 0


# --- Desactivacion de usuarios ---------------------------------------------

def test_desactivar_usuario_invalida_su_token_en_curso(client, admin_autenticado, usuario_autenticado):
    """
    El caso que justifica comprobar `activo` en obtener_usuario_actual y no
    solo en el login: el token del usuario YA esta emitido y sigue siendo
    criptograficamente valido durante horas.
    """
    cabeceras_victima = usuario_autenticado["headers"]
    assert client.get("/algoritmos", headers=cabeceras_victima).status_code == 200

    respuesta = client.patch(
        f"/admin/usuarios/{usuario_autenticado['usuario']['id']}",
        json={"activo": False},
        headers=admin_autenticado["headers"],
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["activo"] is False

    # Mismo token de antes, sin volver a iniciar sesion.
    posterior = client.get("/algoritmos", headers=cabeceras_victima)
    assert posterior.status_code == 403
    assert "desactivada" in posterior.json()["detail"].lower()


def test_usuario_desactivado_no_puede_iniciar_sesion_y_recupera_al_reactivarlo(
    client, db_session, admin_autenticado
):
    email = f"test_desactivado_{uuid.uuid4().hex[:8]}@example.com"
    password = "clave12345"
    client.post("/registro", json={"email": email, "nombre": "Desactivable", "password_hash": password})
    fila = db_session.query(models.Usuario).filter(models.Usuario.email == email).first()
    fila.email_verificado = True
    db_session.commit()

    assert client.post("/login", json={"email": email, "password_hash": password}).status_code == 200

    client.patch(f"/admin/usuarios/{fila.id}", json={"activo": False},
                 headers=admin_autenticado["headers"])
    rechazado = client.post("/login", json={"email": email, "password_hash": password})
    assert rechazado.status_code == 403
    assert "desactivada" in rechazado.json()["detail"].lower()

    # Con la contraseña mal se sigue respondiendo "credenciales incorrectas", y
    # no "cuenta desactivada": lo contrario confirmaria a un tercero que ese
    # correo existe en la plataforma.
    con_clave_mala = client.post("/login", json={"email": email, "password_hash": "otra_clave_12345"})
    assert con_clave_mala.status_code == 400

    client.patch(f"/admin/usuarios/{fila.id}", json={"activo": True},
                 headers=admin_autenticado["headers"])
    assert client.post("/login", json={"email": email, "password_hash": password}).status_code == 200


def test_admin_no_puede_desactivarse_ni_degradarse_a_si_mismo(client, admin_autenticado):
    """
    Las dos comprobaciones que garantizan que siempre queda un administrador
    operativo: quien ejecuta la operacion es por fuerza un admin activo, y no
    puede ser su propio objetivo.
    """
    mi_id = admin_autenticado["usuario"]["id"]
    cabeceras = admin_autenticado["headers"]

    desactivarme = client.patch(f"/admin/usuarios/{mi_id}", json={"activo": False}, headers=cabeceras)
    assert desactivarme.status_code == 409

    degradarme = client.patch(f"/admin/usuarios/{mi_id}", json={"rol": "biologo"}, headers=cabeceras)
    assert degradarme.status_code == 409

    # Y sigo siendo admin activo despues de los dos intentos.
    yo = client.get(f"/admin/usuarios?limit=500", headers=cabeceras).json()
    assert next(u for u in yo if u["id"] == mi_id)["rol"] == "admin"


def test_rol_invalido_devuelve_400(client, admin_autenticado, usuario_autenticado):
    respuesta = client.patch(
        f"/admin/usuarios/{usuario_autenticado['usuario']['id']}",
        json={"rol": "superusuario"},
        headers=admin_autenticado["headers"],
    )
    assert respuesta.status_code == 400


def test_admin_puede_verificar_un_correo_a_mano(client, db_session, admin_autenticado):
    """El registro no bloquea si falla el envio del correo, asi que hace falta
    poder desbloquear la cuenta desde el panel."""
    email = f"test_sinverificar_{uuid.uuid4().hex[:8]}@example.com"
    client.post("/registro", json={"email": email, "nombre": "Sin verificar", "password_hash": "clave12345"})
    fila = db_session.query(models.Usuario).filter(models.Usuario.email == email).first()
    assert fila.email_verificado is False

    respuesta = client.patch(f"/admin/usuarios/{fila.id}", json={"email_verificado": True},
                             headers=admin_autenticado["headers"])
    assert respuesta.status_code == 200
    assert respuesta.json()["email_verificado"] is True
    assert client.post("/login", json={"email": email, "password_hash": "clave12345"}).status_code == 200


def test_usuario_inexistente_devuelve_404(client, admin_autenticado):
    assert client.patch("/admin/usuarios/999999", json={"activo": False},
                        headers=admin_autenticado["headers"]).status_code == 404
    assert client.patch("/admin/algoritmos/999999", json={"activo": False},
                        headers=admin_autenticado["headers"]).status_code == 404


# --- Retirada de algoritmos ------------------------------------------------

def test_algoritmo_desactivado_desaparece_del_catalogo_pero_lo_ve_el_admin(
    client, admin_autenticado, usuario_autenticado
):
    algoritmo_id = _subir_algoritmo(client, usuario_autenticado)

    catalogo = client.get("/algoritmos?limit=500", headers=usuario_autenticado["headers"]).json()
    assert algoritmo_id in [a["id"] for a in catalogo]

    client.patch(f"/admin/algoritmos/{algoritmo_id}", json={"activo": False},
                 headers=admin_autenticado["headers"])

    catalogo = client.get("/algoritmos?limit=500", headers=usuario_autenticado["headers"]).json()
    assert algoritmo_id not in [a["id"] for a in catalogo]

    # El panel si tiene que verlo, o no habria forma de reactivarlo.
    con_inactivos = client.get("/algoritmos?limit=500&incluir_inactivos=true",
                               headers=admin_autenticado["headers"]).json()
    assert algoritmo_id in [a["id"] for a in con_inactivos]


def test_incluir_inactivos_no_sirve_de_nada_a_un_biologo(client, admin_autenticado, usuario_autenticado):
    """El parametro existe para el panel; pedirlo sin ser admin no desvela nada."""
    algoritmo_id = _subir_algoritmo(client, usuario_autenticado)
    client.patch(f"/admin/algoritmos/{algoritmo_id}", json={"activo": False},
                 headers=admin_autenticado["headers"])

    catalogo = client.get("/algoritmos?limit=500&incluir_inactivos=true",
                          headers=usuario_autenticado["headers"]).json()
    assert algoritmo_id not in [a["id"] for a in catalogo]


def test_no_se_puede_crear_una_peticion_con_un_algoritmo_retirado(
    client, mock_celery, admin_autenticado, usuario_autenticado
):
    """La razon de ser de todo esto: que el algoritmo retirado deje de ejecutarse."""
    algoritmo_id = _subir_algoritmo(client, usuario_autenticado)
    client.patch(f"/admin/algoritmos/{algoritmo_id}", json={"activo": False},
                 headers=admin_autenticado["headers"])

    respuesta = client.post(
        "/peticiones",
        data={"algoritmo_id": str(algoritmo_id)},
        files={"archivo_mol": ("test_admin_retirado.mol2", CONTENIDO_MOL2_DUMMY, "chemical/x-mol2")},
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 409
    assert "desactivado" in respuesta.json()["detail"].lower()
    assert len(mock_celery) == 0


def test_peticion_con_algoritmo_inexistente_devuelve_404(client, mock_celery, usuario_autenticado):
    """Antes se aceptaba, se encolaba, y fallaba despues en el worker dejando
    el fichero del usuario escrito en uploads/ para nada."""
    respuesta = client.post(
        "/peticiones",
        data={"algoritmo_id": "999999"},
        files={"archivo_mol": ("test_admin_inexistente.mol2", CONTENIDO_MOL2_DUMMY, "chemical/x-mol2")},
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 404
    assert len(mock_celery) == 0


def test_reactivar_un_algoritmo_lo_devuelve_al_catalogo(client, admin_autenticado, usuario_autenticado):
    algoritmo_id = _subir_algoritmo(client, usuario_autenticado)
    cabeceras = admin_autenticado["headers"]

    client.patch(f"/admin/algoritmos/{algoritmo_id}", json={"activo": False}, headers=cabeceras)
    respuesta = client.patch(f"/admin/algoritmos/{algoritmo_id}", json={"activo": True}, headers=cabeceras)
    assert respuesta.status_code == 200
    assert respuesta.json()["activo"] is True

    catalogo = client.get("/algoritmos?limit=500", headers=usuario_autenticado["headers"]).json()
    assert algoritmo_id in [a["id"] for a in catalogo]


def test_el_workflow_no_ejecuta_un_algoritmo_retirado(client, admin_autenticado, usuario_autenticado, db_session):
    """
    Los nodos del grafo referencian el algoritmo por el NOMBRE de su fichero,
    no por su id, asi que un workflow guardado seguiria usando indefinidamente
    el algoritmo que el administrador acaba de retirar si no se comprobara
    tambien ahi (ver resolver_algoritmo en app/workflow_executor.py).
    """
    from app.workflow_executor import resolver_algoritmo

    algoritmo_id = _subir_algoritmo(client, usuario_autenticado)
    fila = db_session.query(models.Algoritmo).filter(models.Algoritmo.id == algoritmo_id).first()
    nombre_base = fila.ruta_archivo[:-3]  # sin el ".py"

    # Activo: se resuelve con normalidad.
    assert resolver_algoritmo(nombre_base).endswith(fila.ruta_archivo)

    client.patch(f"/admin/algoritmos/{algoritmo_id}", json={"activo": False},
                 headers=admin_autenticado["headers"])

    try:
        resolver_algoritmo(nombre_base)
        assert False, "resolver_algoritmo deberia rechazar un algoritmo retirado"
    except ValueError as e:
        assert "desactivado" in str(e).lower()


def test_un_py_del_catalogo_sin_fila_en_la_base_se_sigue_aceptando(tmp_path):
    """
    La comprobacion bloquea una retirada EXPLICITA, no exige estar registrado:
    los algoritmos que vienen con el repositorio no tienen fila asociada y
    deben seguir ejecutandose igual.
    """
    from app.workflow_executor import resolver_algoritmo

    assert resolver_algoritmo("centerMol").endswith("centerMol.py")


# --- Listado de moleculas --------------------------------------------------

def test_admin_ve_los_ficheros_de_todos_con_su_propietario(
    client, admin_autenticado, usuario_autenticado
):
    subida = client.post(
        "/moleculas/subir",
        files={"archivo": (f"test_admin_{uuid.uuid4().hex[:8]}.sdf", b"dummy\n", "chemical/x-mdl-sdfile")},
        headers=usuario_autenticado["headers"],
    )
    assert subida.status_code == 200, subida.text
    nombre = subida.json().get("nombre") or subida.json().get("archivo")

    listado = client.get("/admin/moleculas?limit=500", headers=admin_autenticado["headers"])
    assert listado.status_code == 200, listado.text
    fila = next((m for m in listado.json() if m["nombre"] == nombre), None)
    assert fila is not None, "el fichero recien subido deberia aparecer en el listado de administracion"
    assert fila["propietario_email"] == usuario_autenticado["usuario"]["email"]
