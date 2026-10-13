"""Tests de integracion: GET /sistema/estado (solo admin)."""


def test_estado_sistema_sin_token_devuelve_401(client):
    assert client.get("/sistema/estado").status_code == 401


def test_estado_sistema_con_rol_no_admin_devuelve_403(client, usuario_autenticado):
    respuesta = client.get("/sistema/estado", headers=usuario_autenticado["headers"])
    assert respuesta.status_code == 403


def test_estado_sistema_admin_devuelve_estructura_esperada(client, admin_autenticado):
    respuesta = client.get("/sistema/estado", headers=admin_autenticado["headers"])
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()

    assert set(cuerpo.keys()) == {"servidor", "cola", "peticiones", "workflows", "usuarios", "copias"}
    assert "modo_ejecucion" in cuerpo["servidor"]
    assert "workers_conectados" in cuerpo["cola"]
    assert cuerpo["peticiones"]["total"] >= 0
    assert cuerpo["usuarios"]["total"] >= 1  # al menos el propio admin
    assert cuerpo["usuarios"]["verificados"] >= 1


def test_estado_sistema_incluye_las_copias(client, admin_autenticado, tmp_path, monkeypatch):
    # Spec 009, R7. Sin estado.json (ninguna copia todavia): sin_copias.
    from app import copias_estado
    monkeypatch.setattr(copias_estado, "RUTA_ESTADO", tmp_path / "estado.json")
    cuerpo = client.get("/sistema/estado", headers=admin_autenticado["headers"]).json()
    assert cuerpo["copias"]["estado"] == "sin_copias"
