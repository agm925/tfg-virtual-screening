"""
Red de seguridad para que la suite nunca vuelva a enviar correo real.

Antes de este fichero, cada fixture de usuario hacia POST /registro, que llama
a correo_verificacion(); con las credenciales del .env de desarrollo, una
pasada completa enviaba del orden de 50 correos a direcciones
test_<uuid>@example.com que rebotan todas. Ademas de lento y dependiente de la
red, es el patron de envio masivo a destinatarios inexistentes por el que un
proveedor acaba restringiendo la cuenta.

tests/conftest.py lo corta por dos vias (credenciales SMTP vacias en el
entorno, y un doble autouse de enviar_correo). Estos tests comprueban que
ambas siguen en pie.
"""
import smtplib
import uuid


def test_registrarse_no_abre_ninguna_conexion_smtp(monkeypatch, client, correos_enviados):
    """El camino que mas correo generaba -- el registro -- no debe tocar la red."""
    def _smtp_prohibido(*args, **kwargs):
        raise AssertionError(
            "Se ha intentado abrir una conexion SMTP real durante los tests. "
            "Revisa el fixture correos_enviados de tests/conftest.py."
        )

    monkeypatch.setattr(smtplib, "SMTP", _smtp_prohibido)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _smtp_prohibido, raising=False)

    email = f"notif_{uuid.uuid4().hex[:8]}@example.com"
    respuesta = client.post(
        "/registro",
        json={"email": email, "nombre": "Prueba Notificaciones", "password_hash": "clave12345"},
    )
    assert respuesta.status_code == 200, respuesta.text

    # El aviso se genera igual: lo que cambia es que lo recoge el doble.
    assert len(correos_enviados) == 1
    assert correos_enviados[0]["destinatario"] == email


def test_la_configuracion_no_expone_credenciales_smtp_en_los_tests():
    """Primera barrera: enviar_correo hace no-op si no hay credenciales."""
    from app.config import SMTP_PASSWORD, SMTP_USER

    assert SMTP_USER == "", "SMTP_USER deberia estar vacio durante los tests"
    assert SMTP_PASSWORD == "", "SMTP_PASSWORD deberia estar vacio durante los tests"
