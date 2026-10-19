"""
Tests de integracion de «¿Has olvidado tu contraseña?» (spec 011).

El correo no sale: el fixture `correos_enviados` lo intercepta y guarda su
cuerpo, de donde se saca el token igual que lo haria el usuario.
"""
import hashlib
import re
import uuid
from datetime import datetime, timedelta

from app import models
from app.config import PUBLIC_URL

PASSWORD = "clave12345"
NO_EXISTE = "No existe ningún usuario con ese correo."


def _registrar(client) -> str:
    """Registra una cuenta (queda SIN confirmar) y devuelve su correo."""
    email = f"test_{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/registro", json={"email": email, "nombre": "Usuario de Test", "password_hash": PASSWORD})
    assert r.status_code == 200, r.text
    return email


def _usuario(db_session, email) -> models.Usuario:
    # expire_all: los endpoints escriben con su propia sesion, y esta podria
    # devolver la fila que ya tenia en memoria.
    db_session.expire_all()
    return db_session.query(models.Usuario).filter(models.Usuario.email == email).first()


def _correos_de_restablecer(correos_enviados) -> list:
    return [c for c in correos_enviados if c["asunto"].startswith("Restablece tu contraseña")]


def _token_del_correo(correo) -> str:
    encontrado = re.search(r"#restablecer=([A-Za-z0-9_-]+)", correo["cuerpo_html"])
    assert encontrado, "el correo no lleva el enlace de restablecer"
    return encontrado.group(1)


def _pedir_enlace(client, correos_enviados, email) -> str:
    r = client.post("/recuperar-contrasena", json={"email": email})
    assert r.status_code == 200, r.text
    return _token_del_correo(_correos_de_restablecer(correos_enviados)[-1])


# --- Pedir el enlace (R2, R3) ------------------------------------------------

def test_cuenta_existente_recibe_el_enlace(client, db_session, correos_enviados):
    """CA1. Vale tambien para una cuenta sin confirmar."""
    email = _registrar(client)

    r = client.post("/recuperar-contrasena", json={"email": email})

    assert r.status_code == 200, r.text
    correos = _correos_de_restablecer(correos_enviados)
    assert len(correos) == 1
    assert correos[0]["destinatario"] == email
    assert f"{PUBLIC_URL}/#restablecer=" in correos[0]["cuerpo_html"]

    usuario = _usuario(db_session, email)
    assert usuario.token_restablecer
    margen = usuario.token_restablecer_expira - datetime.utcnow()
    assert timedelta(minutes=58) < margen <= timedelta(hours=1)


def test_correo_sin_cuenta_dice_que_no_existe(client, correos_enviados):
    """CA2."""
    r = client.post("/recuperar-contrasena", json={"email": f"nadie_{uuid.uuid4().hex[:8]}@example.com"})

    assert r.status_code == 404
    assert r.json()["detail"] == NO_EXISTE
    assert _correos_de_restablecer(correos_enviados) == []


def test_cuenta_desactivada_se_trata_como_inexistente(client, db_session, correos_enviados):
    """CA2."""
    email = _registrar(client)
    usuario = _usuario(db_session, email)
    usuario.activo = False
    db_session.commit()

    r = client.post("/recuperar-contrasena", json={"email": email})

    assert r.status_code == 404
    assert r.json()["detail"] == NO_EXISTE
    assert _correos_de_restablecer(correos_enviados) == []


def test_correo_mal_escrito_da_422(client):
    assert client.post("/recuperar-contrasena", json={"email": "no-es-un-correo"}).status_code == 422


def test_en_la_base_solo_esta_el_hash_del_token(client, db_session, correos_enviados):
    """CA4. Una copia de la base no debe contener enlaces que funcionen."""
    email = _registrar(client)
    token = _pedir_enlace(client, correos_enviados, email)

    guardado = _usuario(db_session, email).token_restablecer
    assert guardado != token
    assert guardado == hashlib.sha256(token.encode()).hexdigest()


def test_si_el_correo_no_sale_responde_503(client, db_session, monkeypatch):
    """CA5. No se dice que se ha enviado algo que no ha salido."""
    email = _registrar(client)
    monkeypatch.setattr("app.email_utils.enviar_correo", lambda *a, **k: False)

    r = client.post("/recuperar-contrasena", json={"email": email})

    assert r.status_code == 503
    assert r.json()["detail"] == "No se ha podido enviar el correo. Inténtalo más tarde."


class _RedisFalso:
    """Lo justo de Redis para el limitador: sin el, la prueba se saltaria en
    cualquier maquina sin Redis levantado, que es lo normal en Windows."""
    def __init__(self):
        self.valores, self.caducidad = {}, {}

    def get(self, clave):
        return self.valores.get(clave)

    def incr(self, clave):
        self.valores[clave] = int(self.valores.get(clave, 0)) + 1
        return self.valores[clave]

    def expire(self, clave, segundos):
        self.caducidad[clave] = segundos

    def ttl(self, clave):
        return self.caducidad.get(clave, -1)

    def delete(self, clave):
        self.valores.pop(clave, None)


def test_limite_de_solicitudes_por_correo(client, correos_enviados, monkeypatch):
    """CA3."""
    from app import rate_limit
    monkeypatch.setattr(rate_limit, "_redis", _RedisFalso())

    email = _registrar(client)
    for _ in range(rate_limit.MAX_SOLICITUDES_RESTABLECER):
        assert client.post("/recuperar-contrasena", json={"email": email}).status_code == 200

    bloqueado = client.post("/recuperar-contrasena", json={"email": email})
    assert bloqueado.status_code == 429
    assert bloqueado.headers["Retry-After"] == str(rate_limit.VENTANA_RESTABLECER_SEGUNDOS)
    assert len(_correos_de_restablecer(correos_enviados)) == rate_limit.MAX_SOLICITUDES_RESTABLECER

    # Otro correo no se ve afectado, y el login de este tampoco.
    assert client.post("/recuperar-contrasena", json={"email": _registrar(client)}).status_code == 200
    rate_limit.verificar_no_bloqueado(email)


def test_correo_de_restablecer(correos_enviados):
    """R3: enlace en el fragmento, caducidad dicha y nombre escapado."""
    from app.email_utils import correo_restablecer

    assert correo_restablecer("<b>Ana</b>", "ana@example.com", "tok_123-abc") is True

    correo = correos_enviados[-1]
    assert correo["destinatario"] == "ana@example.com"
    assert correo["asunto"] == "Restablece tu contraseña — MolServer"
    cuerpo = correo["cuerpo_html"]
    assert f"{PUBLIC_URL}/#restablecer=tok_123-abc" in cuerpo
    # En la consulta (?) el token acabaria en los registros de acceso de nginx.
    assert "?restablecer" not in cuerpo
    assert "1 hora" in cuerpo
    assert "&lt;b&gt;Ana" in cuerpo and "<b>Ana" not in cuerpo


# --- Cambiar la contraseña (R4) ---------------------------------------------

NO_VALE = "El enlace no es válido o ha caducado. Pide uno nuevo."


def _cambiar(client, token, password="nueva12345"):
    return client.post("/restablecer-contrasena", json={"token": token, "password": password})


def test_el_enlace_cambia_la_contrasena_y_confirma_la_cuenta(client, db_session, correos_enviados):
    """CA6. La cuenta estaba sin confirmar: abrir el enlace demuestra que el correo es suyo."""
    email = _registrar(client)
    token = _pedir_enlace(client, correos_enviados, email)

    r = _cambiar(client, token)

    assert r.status_code == 200, r.text
    usuario = _usuario(db_session, email)
    assert usuario.email_verificado is True
    assert usuario.token_verificacion is None
    assert usuario.token_restablecer is None and usuario.token_restablecer_expira is None
    assert client.post("/login", json={"email": email, "password_hash": "nueva12345"}).status_code == 200
    assert client.post("/login", json={"email": email, "password_hash": PASSWORD}).status_code == 400
    # Un solo uso.
    reusado = _cambiar(client, token, "otra123456")
    assert reusado.status_code == 400
    assert reusado.json()["detail"] == NO_VALE


def test_token_inventado_no_vale(client):
    """CA7."""
    r = _cambiar(client, "token-que-no-existe")
    assert r.status_code == 400
    assert r.json()["detail"] == NO_VALE


def test_pedir_otro_enlace_anula_el_anterior(client, correos_enviados):
    """CA7."""
    email = _registrar(client)
    viejo = _pedir_enlace(client, correos_enviados, email)
    nuevo = _pedir_enlace(client, correos_enviados, email)

    assert _cambiar(client, viejo).status_code == 400
    assert _cambiar(client, nuevo).status_code == 200


def test_enlace_caducado_no_vale(client, db_session, correos_enviados):
    """CA7."""
    email = _registrar(client)
    token = _pedir_enlace(client, correos_enviados, email)
    usuario = _usuario(db_session, email)
    usuario.token_restablecer_expira = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()

    assert _cambiar(client, token).status_code == 400


def test_cuenta_desactivada_despues_de_pedir_el_enlace(client, db_session, correos_enviados):
    """CA7. Un administrador puede desactivarla mientras el enlace sigue vivo."""
    email = _registrar(client)
    token = _pedir_enlace(client, correos_enviados, email)
    usuario = _usuario(db_session, email)
    usuario.activo = False
    db_session.commit()

    assert _cambiar(client, token).status_code == 400


def test_contrasena_corta_da_422(client, correos_enviados):
    """CA7. Mismas reglas que el registro; el token no se gasta."""
    email = _registrar(client)
    token = _pedir_enlace(client, correos_enviados, email)

    assert _cambiar(client, token, "corta").status_code == 422
    assert _cambiar(client, token).status_code == 200


# --- Sesiones anteriores (R5) -----------------------------------------------

def test_cambiar_la_contrasena_cierra_las_sesiones_anteriores(client, usuario_autenticado, correos_enviados):
    """CA8. Todo ocurre en el mismo segundo: la comparación no puede ser a segundos enteros."""
    email = usuario_autenticado["usuario"]["email"]
    sesion_vieja = usuario_autenticado["headers"]
    assert client.get("/algoritmos", headers=sesion_vieja).status_code == 200

    assert _cambiar(client, _pedir_enlace(client, correos_enviados, email)).status_code == 200

    r = client.get("/algoritmos", headers=sesion_vieja)
    assert r.status_code == 401
    assert r.json()["detail"] == "La contraseña ha cambiado. Vuelve a iniciar sesión."

    login = client.post("/login", json={"email": email, "password_hash": "nueva12345"})
    sesion_nueva = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/algoritmos", headers=sesion_nueva).status_code == 200
