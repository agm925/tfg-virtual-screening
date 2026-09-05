"""Tests de integracion: registro, verificacion de email y login (app/main.py)."""
import uuid


def _email_unico() -> str:
    return f"test_{uuid.uuid4().hex[:10]}@example.com"


def test_registro_crea_usuario_no_verificado(client):
    email = _email_unico()
    respuesta = client.post(
        "/registro",
        json={"email": email, "nombre": "Usuario de Test", "password_hash": "clave12345"},
    )
    assert respuesta.status_code == 200


def test_registro_con_email_duplicado_devuelve_400(client):
    email = _email_unico()
    datos = {"email": email, "nombre": "Usuario de Test", "password_hash": "clave12345"}
    assert client.post("/registro", json=datos).status_code == 200
    respuesta_duplicada = client.post("/registro", json=datos)
    assert respuesta_duplicada.status_code == 400


def test_login_antes_de_verificar_email_devuelve_403(client):
    email = _email_unico()
    client.post(
        "/registro",
        json={"email": email, "nombre": "Usuario de Test", "password_hash": "clave12345"},
    )
    respuesta = client.post("/login", json={"email": email, "password_hash": "clave12345"})
    assert respuesta.status_code == 403


def test_login_con_password_incorrecta_devuelve_400(client):
    email = _email_unico()
    client.post(
        "/registro",
        json={"email": email, "nombre": "Usuario de Test", "password_hash": "clave12345"},
    )
    respuesta = client.post("/login", json={"email": email, "password_hash": "clave_erronea"})
    assert respuesta.status_code == 400


def test_verificar_email_con_token_invalido_devuelve_400(client):
    respuesta = client.get("/verificar-email", params={"token": "token-que-no-existe"})
    assert respuesta.status_code == 400


def test_ciclo_completo_registro_verificacion_login(client, db_session):
    from app import models

    email = _email_unico()
    client.post(
        "/registro",
        json={"email": email, "nombre": "Usuario de Test", "password_hash": "clave12345"},
    )

    usuario = db_session.query(models.Usuario).filter(models.Usuario.email == email).first()
    assert usuario is not None
    assert usuario.email_verificado is False
    token = usuario.token_verificacion
    assert token

    respuesta_verificacion = client.get("/verificar-email", params={"token": token})
    assert respuesta_verificacion.status_code == 200

    respuesta_login = client.post("/login", json={"email": email, "password_hash": "clave12345"})
    assert respuesta_login.status_code == 200
    cuerpo = respuesta_login.json()
    assert cuerpo["token_type"] == "bearer"
    assert cuerpo["access_token"]
    assert cuerpo["usuario"]["email"] == email
    assert cuerpo["usuario"]["rol"] == "biologo"
