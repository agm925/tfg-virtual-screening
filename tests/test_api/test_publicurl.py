"""
Spec 004, R4: los enlaces que el backend escribe para el usuario salen de
PUBLIC_URL, la direccion con la que se abre la plataforma
(https://rt.hpca.ual.es/molserver en el servidor RTX).

Antes, el correo de verificacion enlazaba a http://localhost:8000 y la pagina
de cuenta confirmada a http://localhost:5173: en un servidor, nadie podia
activar su cuenta.
"""
import pytest

from app import config, email_utils, paginas

URL_RTX = "https://rt.hpca.ual.es/molserver"


@pytest.fixture()
def cuerpos(monkeypatch):
    """Cuerpo HTML de cada correo que se habria enviado."""
    enviados = []
    monkeypatch.setattr(email_utils, "enviar_correo",
                        lambda destinatario, asunto, cuerpo_html: enviados.append(cuerpo_html) or True)
    return enviados


def test_el_enlace_del_correo_va_por_la_api_de_la_url_publica(monkeypatch, cuerpos):
    monkeypatch.setattr(email_utils, "PUBLIC_URL", URL_RTX)

    email_utils.correo_verificacion("Ana", "ana@ual.es", "tok-123")

    assert f"{URL_RTX}/api/verificar-email?token=tok-123" in cuerpos[0]
    assert "localhost" not in cuerpos[0]


def test_por_defecto_el_enlace_no_va_al_puerto_del_backend(cuerpos):
    # En un servidor el puerto 8000 no se publica: el enlace va por el
    # frontend, que reenvia /api/ al backend.
    email_utils.correo_verificacion("Ana", "ana@ual.es", "tok-123")

    assert ":8000" not in cuerpos[0]
    assert "/api/verificar-email?token=tok-123" in cuerpos[0]


@pytest.mark.parametrize("pagina_de", ["pagina_cuenta_confirmada", "pagina_enlace_no_valido"])
def test_la_pagina_de_verificacion_vuelve_a_la_url_publica(monkeypatch, pagina_de):
    # Las paginas viven en app/paginas.py desde la spec 005.
    monkeypatch.setattr(paginas, "PUBLIC_URL", URL_RTX)

    pagina = getattr(paginas, pagina_de)()

    assert f'href="{URL_RTX}/"' in pagina
    assert "localhost" not in pagina


def test_el_endpoint_de_verificacion_usa_la_url_publica(client, monkeypatch):
    monkeypatch.setattr(paginas, "PUBLIC_URL", URL_RTX)

    respuesta = client.get("/verificar-email", params={"token": "no-existe"})

    assert respuesta.status_code == 400
    assert f'href="{URL_RTX}/"' in respuesta.text


@pytest.mark.parametrize("valor, esperado", [
    (URL_RTX, URL_RTX),
    (URL_RTX + "/", URL_RTX),
    ("  " + URL_RTX + "//  ", URL_RTX),
    ("", "http://localhost:5173"),
    (None, "http://localhost:5173"),
])
def test_la_url_publica_se_normaliza(valor, esperado):
    # Sin barra final: los enlaces le anaden la suya ("/api/...", "/").
    assert config.normalizar_url_publica(valor) == esperado
