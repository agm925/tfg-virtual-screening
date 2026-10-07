"""
Spec 005: la pagina a la que lleva el enlace del correo de confirmacion.

Antes era HTML escrito dentro de app/main.py, con el aspecto anterior a la
identidad de la UAL (morado, sombras, emojis), sin idioma, titulo ni ajuste
para el movil, y con un enlace ya usado solo decia «Enlace invalido», aunque la
cuenta estuviera confirmada (los servicios de correo abren los enlaces por su
cuenta para analizarlos).
"""
import re
import uuid
from pathlib import Path

import pytest

from app import email_utils, identidad

APP = Path(__file__).resolve().parents[2] / "app"


# ---------------------------------------------------------------------------
# R1: nombre y colores en un unico sitio
# ---------------------------------------------------------------------------

def test_la_identidad_define_el_nombre_y_los_colores_de_la_ual():
    assert identidad.NOMBRE == "MolServer"
    assert identidad.AZUL_UAL == "#0A4382"
    for color in ("TEXTO", "TEXTO_2", "LINEA", "VERDE_OK", "ROJO_UAL"):
        assert re.fullmatch(r"#[0-9A-F]{6}", getattr(identidad, color)), color


def test_los_correos_no_definen_colores_propios():
    # Los importan de identidad.py: si cambia el azul, cambia en todas partes.
    codigo = (APP / "email_utils.py").read_text(encoding="utf-8")
    assert not re.search(r'^[A-Z_]+\s*=\s*"#[0-9A-Fa-f]{6}"', codigo, re.M)
    assert email_utils.AZUL_UAL is identidad.AZUL_UAL


# ---------------------------------------------------------------------------
# R2, R3: las dos paginas
# ---------------------------------------------------------------------------

URL_RTX = "https://rt.hpca.ual.es/molserver"

# Pictogramas y simbolos (U+2190 en adelante) y el selector de variante de los
# emojis. Quedan permitidos acentos, «», guiones y puntos suspensivos.
EMOJI = re.compile("[\u2190-\u2bff\ufe0f\U0001f000-\U0001faff]")


@pytest.fixture()
def paginas_rtx(monkeypatch):
    from app import paginas
    monkeypatch.setattr(paginas, "PUBLIC_URL", URL_RTX)
    return {
        "confirmada": paginas.pagina_cuenta_confirmada(),
        "no_valido": paginas.pagina_enlace_no_valido(),
    }


@pytest.mark.parametrize("cual", ["confirmada", "no_valido"])
def test_es_una_pagina_completa_en_espanol(paginas_rtx, cual):
    pagina = paginas_rtx[cual]
    assert pagina.lstrip().lower().startswith("<!doctype html>")
    assert '<html lang="es">' in pagina
    assert '<meta charset="utf-8">' in pagina
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in pagina
    assert re.search(r"<title>[^<]*MolServer</title>", pagina)


@pytest.mark.parametrize("cual", ["confirmada", "no_valido"])
def test_lleva_el_escudo_y_el_boton_a_la_plataforma(paginas_rtx, cual):
    pagina = paginas_rtx[cual]
    assert f'src="{URL_RTX}/ual/escudo-ual.png"' in pagina
    assert f'href="{URL_RTX}/ual/escudo-ual.png"' in pagina   # icono de la pestaña
    assert f'href="{URL_RTX}/"' in pagina
    assert "Ir a MolServer" in pagina


@pytest.mark.parametrize("cual", ["confirmada", "no_valido"])
def test_tiene_el_aspecto_de_molserver(paginas_rtx, cual):
    pagina = paginas_rtx[cual]
    assert not EMOJI.search(pagina), EMOJI.search(pagina)
    assert identidad.AZUL_UAL in pagina
    for antiguo in ("#667eea", "box-shadow", "gradient", "localhost"):
        assert antiguo not in pagina.lower(), antiguo


def test_la_de_cuenta_confirmada_dice_que_ya_se_puede_entrar(paginas_rtx):
    pagina = paginas_rtx["confirmada"]
    assert "Cuenta confirmada" in pagina
    assert "Ya puedes iniciar sesión" in pagina


def test_la_de_enlace_no_valido_explica_que_hacer(paginas_rtx):
    pagina = paginas_rtx["no_valido"]
    assert "Este enlace ya no sirve" in pagina
    assert "solo funciona una vez" in pagina
    assert "iniciar sesión" in pagina
    assert "administrador" in pagina
    assert "reenv" not in pagina.lower()   # no existe: no se promete


def test_la_url_publica_llega_escapada(monkeypatch):
    from app import paginas
    monkeypatch.setattr(paginas, "PUBLIC_URL", 'https://x.es/"><script>')

    pagina = paginas.pagina_cuenta_confirmada()

    assert "<script>" not in pagina
    assert "&quot;&gt;&lt;script&gt;" in pagina


# ---------------------------------------------------------------------------
# R4: el endpoint solo comprueba el token y elige la pagina
# ---------------------------------------------------------------------------

def test_main_no_contiene_el_html_de_estas_paginas():
    codigo = (APP / "main.py").read_text(encoding="utf-8")
    assert "_html_verificacion" not in codigo
    assert "<html" not in codigo.lower()


def test_un_enlace_valido_confirma_la_cuenta_y_lo_dice(client, db_session):
    from app import models

    email = f"pagina_{uuid.uuid4().hex[:8]}@example.com"
    client.post("/registro", json={"email": email, "nombre": "Ana", "password_hash": "clave12345"})
    usuario = db_session.query(models.Usuario).filter(models.Usuario.email == email).first()

    respuesta = client.get("/verificar-email", params={"token": usuario.token_verificacion})

    assert respuesta.status_code == 200
    assert "text/html" in respuesta.headers["content-type"]
    assert "Cuenta confirmada" in respuesta.text
    db_session.refresh(usuario)
    assert usuario.email_verificado is True


def test_un_enlace_ya_usado_explica_que_hacer(client, db_session):
    from app import models

    email = f"pagina_{uuid.uuid4().hex[:8]}@example.com"
    client.post("/registro", json={"email": email, "nombre": "Ana", "password_hash": "clave12345"})
    token = db_session.query(models.Usuario).filter(models.Usuario.email == email).first().token_verificacion
    client.get("/verificar-email", params={"token": token})

    # Segunda vez: el enlace ya se gasto (o lo abrio antes el programa de correo).
    respuesta = client.get("/verificar-email", params={"token": token})

    assert respuesta.status_code == 400
    assert "Este enlace ya no sirve" in respuesta.text
