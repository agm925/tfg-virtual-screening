"""Tests de integracion: mecanica del JWT (app/auth.py) sobre un endpoint protegido cualquiera."""
from datetime import datetime, timedelta, timezone

import jwt

from app.config import JWT_ALGORITHM, JWT_SECRET_KEY


def test_endpoint_protegido_sin_cabecera_authorization_devuelve_401(client):
    respuesta = client.get("/workflows/usuario/1")
    assert respuesta.status_code == 401


def test_endpoint_protegido_con_token_malformado_devuelve_401(client):
    respuesta = client.get("/workflows/usuario/1", headers={"Authorization": "Bearer esto-no-es-un-jwt"})
    assert respuesta.status_code == 401


def test_endpoint_protegido_con_firma_invalida_devuelve_401(client, usuario_autenticado):
    token_real = usuario_autenticado["headers"]["Authorization"].split(" ")[1]
    # Se reconstruye el mismo payload pero firmado con una clave distinta.
    payload = jwt.decode(token_real, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    token_falsificado = jwt.encode(payload, "clave-incorrecta", algorithm=JWT_ALGORITHM)

    respuesta = client.get(
        f"/workflows/usuario/{usuario_autenticado['usuario']['id']}",
        headers={"Authorization": f"Bearer {token_falsificado}"},
    )
    assert respuesta.status_code == 401


def test_endpoint_protegido_con_token_caducado_devuelve_401(client, usuario_autenticado):
    usuario_id = usuario_autenticado["usuario"]["id"]
    ahora = datetime.now(timezone.utc)
    payload_caducado = {
        "sub": str(usuario_id),
        "email": usuario_autenticado["usuario"]["email"],
        "rol": usuario_autenticado["usuario"]["rol"],
        "iat": ahora - timedelta(hours=2),
        "exp": ahora - timedelta(hours=1),  # caducado hace una hora
    }
    token_caducado = jwt.encode(payload_caducado, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    respuesta = client.get(
        f"/workflows/usuario/{usuario_id}", headers={"Authorization": f"Bearer {token_caducado}"}
    )
    assert respuesta.status_code == 401
    assert "caducado" in respuesta.json()["detail"].lower()


def test_token_valido_permite_acceder_a_recurso_propio(client, usuario_autenticado):
    respuesta = client.get(
        f"/workflows/usuario/{usuario_autenticado['usuario']['id']}",
        headers=usuario_autenticado["headers"],
    )
    assert respuesta.status_code == 200
