"""
Tests de seguridad: inyeccion SQL, rate limiting de /login y path traversal.

Todo el acceso a base de datos del proyecto pasa por el ORM de SQLAlchemy
(`db.query(Modelo).filter(Modelo.columna == valor)`), que parametriza los
valores automaticamente -- no hay ni un solo `db.execute(text(f"..."))` con
un valor interpolado en app/*.py (verificado por separado con grep). Estos
tests no "prueban que SQLAlchemy funciona", sino que ejercitan los
endpoints reales con payloads de inyeccion clasicos para detectar una
regresion futura si alguien añadiera una consulta cruda sin parametrizar.
"""
import time
import uuid

import pytest

from app import models


PAYLOADS_SQLI = [
    "' OR '1'='1",
    "'; DROP TABLE usuarios; --",
    "' OR 1=1 --",
    "admin'--",
    "' UNION SELECT * FROM usuarios --",
]


def test_login_con_payloads_sqli_nunca_autentica(client):
    for payload in PAYLOADS_SQLI:
        respuesta = client.post(
            "/login",
            json={"email": f"noexiste_{uuid.uuid4().hex[:6]}@example.com", "password_hash": payload},
        )
        # Ni 200 (autenticado) ni 500 (la inyeccion rompio la consulta):
        # solo 400 (credenciales invalidas) es un resultado aceptable aqui.
        assert respuesta.status_code == 400, f"payload {payload!r} dio {respuesta.status_code}"


def test_login_con_email_payload_sqli_no_autentica_ni_rompe(client):
    # EmailStr (Seccion de validacion, schemas.py) ya rechaza esto con 422
    # antes de tocar la base de datos -- se comprueba igualmente que no
    # cuela como 200 ni como 500.
    for payload in PAYLOADS_SQLI:
        respuesta = client.post("/login", json={"email": payload, "password_hash": "loquesea"})
        assert respuesta.status_code in (400, 422), f"payload {payload!r} dio {respuesta.status_code}"


def test_registro_con_payload_sqli_en_nombre_se_guarda_como_texto_literal(client, db_session):
    email = f"test_sqli_{uuid.uuid4().hex[:8]}@example.com"
    payload_nombre = "Robert'); DROP TABLE usuarios; --"

    respuesta = client.post(
        "/registro",
        json={"email": email, "nombre": payload_nombre, "password_hash": "clave12345"},
    )
    assert respuesta.status_code == 200

    # La tabla usuarios sigue existiendo y consultable -- si la inyeccion
    # hubiera funcionado, esta misma consulta fallaria con un error de BD.
    usuario = db_session.query(models.Usuario).filter(models.Usuario.email == email).first()
    assert usuario is not None
    # El payload se guarda tal cual, como dato inerte, no como SQL ejecutado.
    assert usuario.nombre == payload_nombre

    # Prueba independiente de que la tabla sigue intacta: cuenta filas.
    assert db_session.query(models.Usuario).count() >= 1


def test_crear_workflow_con_payload_sqli_en_nombre_no_rompe_nada(client, usuario_autenticado):
    payload = "'; DROP TABLE workflows; --"
    respuesta = client.post(
        "/workflows",
        data={"nombre": payload, "descripcion": "test seguridad"},
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == payload

    # La tabla workflows sigue operativa: se puede volver a listar sin error.
    respuesta_listado = client.get(
        f"/workflows/usuario/{usuario_autenticado['usuario']['id']}",
        headers=usuario_autenticado["headers"],
    )
    assert respuesta_listado.status_code == 200


CONTENIDO_MOL2_DUMMY = b"@<TRIPOS>MOLECULE\ndummy\n1 0 0 0 0\nSMALL\nNO_CHARGES\n"


def test_uploads_sin_token_devuelve_401(client):
    assert client.get("/uploads/algo.mol2").status_code == 401


def test_uploads_de_peticion_ajena_devuelve_403(
    client, usuario_autenticado, desarrollador_autenticado, mock_celery
):
    # Endpoint hallado y arreglado en el security-review: GET /uploads/{nombre}
    # servia cualquier fichero sin comprobar propietario.
    # El doble debe escribir en el ultimo argumento: la subida lo ejecuta
    # contra las moleculas de referencia antes de aceptarlo.
    script = (b"# TIPO_ALGORITMO: preprocesado\n"
              b"import shutil, sys\n"
              b"shutil.copyfile(sys.argv[1], sys.argv[-1])\n")
    algoritmo_id = client.post(
        "/algoritmos",
        data={"nombre": "dummy", "descripcion": "dummy", "tipo": "preprocesado"},
        files={"archivo": ("test_dummy_uploads_algo.py", script, "text/x-python")},
        headers=desarrollador_autenticado["headers"],
    ).json()["id"]

    peticion = client.post(
        "/peticiones",
        data={"algoritmo_id": str(algoritmo_id)},
        files={"archivo_mol": ("test_dummy_uploads_ajeno.mol2", CONTENIDO_MOL2_DUMMY, "chemical/x-mol2")},
        headers=usuario_autenticado["headers"],
    ).json()

    respuesta_ajeno = client.get(
        f"/uploads/{peticion['ruta_mol_original']}", headers=desarrollador_autenticado["headers"]
    )
    assert respuesta_ajeno.status_code == 403

    respuesta_propio = client.get(
        f"/uploads/{peticion['ruta_mol_original']}", headers=usuario_autenticado["headers"]
    )
    assert respuesta_propio.status_code == 200


def test_uploads_de_deposito_publico_accesible_por_cualquier_autenticado(client, usuario_autenticado):
    client.post(
        "/moleculas/subir",
        data={"tipo": "molecula"},
        files={"archivo": ("test_dummy_uploads_publico.mol2", CONTENIDO_MOL2_DUMMY, "chemical/x-mol2")},
        headers=usuario_autenticado["headers"],
    )
    respuesta = client.get("/uploads/test_dummy_uploads_publico.mol2", headers=usuario_autenticado["headers"])
    assert respuesta.status_code == 200


def test_descargar_con_path_traversal_no_sale_de_uploads(client, usuario_autenticado):
    # No es inyeccion SQL, pero es la misma familia de "el cliente controla
    # una ruta que toca el sistema de archivos": GET /uploads/{nombre} debe
    # servir solo desde uploads/, nunca ficheros arbitrarios del servidor.
    # Requiere token desde el security-review (antes este endpoint era
    # publico); se usa un usuario autenticado para probar la validacion de
    # la ruta en si, no la comprobacion de autenticacion (ya cubierta en
    # test_uploads_sin_token_devuelve_401).
    respuesta = client.get(
        "/uploads/..%2F..%2F..%2Fetc%2Fpasswd", headers=usuario_autenticado["headers"]
    )
    assert respuesta.status_code in (404, 400)


def test_borrar_molecula_con_path_traversal_no_borra_fuera_de_uploads(client, usuario_autenticado):
    respuesta = client.delete(
        "/moleculas/..%2F..%2Fapp%2Fmain.py", headers=usuario_autenticado["headers"]
    )
    assert respuesta.status_code in (404, 400)


# --- Rate limiting de /login -------------------------------------------------

def test_rate_limit_login_bloquea_tras_varios_fallos(client, usuario_autenticado, redis_disponible):
    if not redis_disponible:
        pytest.skip(
            "Redis no está levantado: el limitador falla en abierto a propósito "
            "(ver app/rate_limit.py), así que no puede bloquear la cuenta."
        )

    from app.rate_limit import MAX_INTENTOS_LOGIN, limpiar_intentos

    email = usuario_autenticado["usuario"]["email"]
    limpiar_intentos(email)  # aislar este test de fallos previos de otros tests

    try:
        for _ in range(MAX_INTENTOS_LOGIN):
            r = client.post("/login", json={"email": email, "password_hash": "clave_incorrecta"})
            assert r.status_code == 400

        # El intento MAX_INTENTOS_LOGIN+1 ya no llega a comparar la contraseña:
        # se corta antes con 429, incluso probando la contraseña correcta.
        bloqueado = client.post("/login", json={"email": email, "password_hash": "clave12345"})
        assert bloqueado.status_code == 429
        assert "Retry-After" in bloqueado.headers
    finally:
        limpiar_intentos(email)
