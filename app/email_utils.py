"""
Correos que manda la plataforma (spec 004, R7).

Todos salen de una misma plantilla, con el nombre de la plataforma (MolServer)
y los colores de la UAL, y los de resultado llevan a la seccion Resultados con
un enlace a PUBLIC_URL. Reglas:

- Nada de detalle tecnico: el mensaje de un algoritmo o del motor puede llevar
  trazas y rutas del servidor (principio 7). Los correos de error dicen que ha
  fallado y donde ver el motivo; por eso ni siquiera reciben ese texto.
- Todo lo que escribe un usuario (su nombre, el del workflow, el del
  algoritmo) se escapa antes de ir al HTML, y en el asunto se queda en una sola
  linea: un salto de linea en el nombre de un workflow podia anadir cabeceras.
"""
import html
import re
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM, PUBLIC_URL
# Nombre y colores, compartidos con las paginas del backend (spec 005).
from app.identidad import NOMBRE, AZUL_UAL, TEXTO, TEXTO_2, LINEA, VERDE_OK, ROJO_UAL


def _e(texto) -> str:
    """Texto de usuario listo para el HTML del correo."""
    return html.escape(str(texto), quote=True)


def _asunto(texto: str) -> str:
    """Una sola linea y sin caracteres de control."""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", texto).strip()


def _plantilla(titulo: str, parrafos: list, color: str = AZUL_UAL,
               boton: tuple = None, enlace_visible: str = None) -> str:
    """
    El HTML comun de todos los correos. `titulo` y `parrafos` ya vienen
    escapados por quien llama; `boton` es (texto, url).
    """
    cuerpo = "".join(f'<p style="margin:0 0 14px;line-height:1.6">{p}</p>' for p in parrafos)
    if boton:
        texto, url = boton
        cuerpo += (
            f'<p style="margin:28px 0;text-align:center">'
            f'<a href="{_e(url)}" style="background:{AZUL_UAL};color:#FFFFFF;padding:12px 24px;'
            f'border-radius:2px;text-decoration:none;font-weight:bold">{_e(texto)}</a></p>'
        )
    if enlace_visible:
        cuerpo += (
            f'<p style="font-size:13px;color:{TEXTO_2}">Si el botón no funciona, copia este enlace '
            f'en tu navegador:<br><a href="{_e(enlace_visible)}" style="color:{AZUL_UAL}">'
            f'{_e(enlace_visible)}</a></p>'
        )
    return (
        f'<div style="font-family:Segoe UI,Arial,sans-serif;max-width:560px;margin:auto;color:{TEXTO}">'
        f'<div style="background:{AZUL_UAL};color:#FFFFFF;padding:14px 20px;font-weight:bold">{NOMBRE}</div>'
        f'<div style="border:1px solid {LINEA};border-top:none;padding:20px">'
        f'<h2 style="color:{color};margin:0 0 16px;font-size:20px">{titulo}</h2>'
        f'{cuerpo}'
        f'</div>'
        f'<p style="font-size:12px;color:{TEXTO_2};margin:12px 0">'
        f'{NOMBRE} · Universidad de Almería — notificación automática</p>'
        f'</div>'
    )


def _boton_plataforma() -> tuple:
    # La aplicacion no tiene una direccion por pagina: se entra por el inicio,
    # y desde ahi esta la seccion Resultados en el menu.
    return ("Ir a MolServer", f"{PUBLIC_URL}/")


def correo_verificacion(nombre: str, email: str, token: str) -> None:
    # Por /api/ de la direccion publica, como cualquier otra llamada a la API:
    # el puerto 8000 del backend no se publica en el servidor (spec 004).
    enlace = f"{PUBLIC_URL}/api/verificar-email?token={token}"
    enviar_correo(
        destinatario=email,
        asunto=_asunto(f"Confirma tu cuenta — {NOMBRE}"),
        cuerpo_html=_plantilla(
            f"Bienvenido a {NOMBRE}, {_e(nombre)}",
            ["Gracias por registrarte. Para activar tu cuenta y poder iniciar sesión, "
             "confirma tu dirección de correo con el botón:",
             "Si no creaste esta cuenta, ignora este correo."],
            boton=("Confirmar mi cuenta", enlace),
            enlace_visible=enlace,
        ),
    )


def enviar_correo(destinatario: str, asunto: str, cuerpo_html: str) -> bool:
    """
    Envía un correo HTML por SMTP con TLS.
    Devuelve True si se envió correctamente, False si faltaban credenciales o hubo error.
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        print("[email] SMTP no configurado — correo no enviado.")
        return False

    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = asunto
    mensaje["From"]    = EMAIL_FROM
    mensaje["To"]      = destinatario
    mensaje.attach(MIMEText(cuerpo_html, "html"))

    try:
        contexto = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as servidor:
            servidor.ehlo()
            servidor.starttls(context=contexto)
            servidor.login(SMTP_USER, SMTP_PASSWORD)
            servidor.sendmail(EMAIL_FROM, destinatario, mensaje.as_string())
        print(f"[email] Correo enviado a {destinatario}")
        return True
    except Exception as e:
        print(f"[email] Error al enviar correo: {e}")
        return False


def correo_completado(nombre: str, email: str, peticion_id: int, algoritmo: str) -> None:
    enviar_correo(
        destinatario=email,
        asunto=_asunto(f"Tu petición nº {peticion_id} ha terminado — {NOMBRE}"),
        cuerpo_html=_plantilla(
            "Tu análisis ha terminado",
            [f"Hola, {_e(nombre)}:",
             f"La petición nº {_e(peticion_id)} con el algoritmo <strong>{_e(algoritmo)}</strong> "
             f"ha terminado correctamente.",
             "Puedes ver y descargar el resultado en la sección <strong>Resultados</strong> "
             "de la plataforma."],
            color=VERDE_OK,
            boton=_boton_plataforma(),
        ),
    )


def correo_error(nombre: str, email: str, peticion_id: int, algoritmo: str) -> None:
    enviar_correo(
        destinatario=email,
        asunto=_asunto(f"La petición nº {peticion_id} no se ha completado — {NOMBRE}"),
        cuerpo_html=_plantilla(
            "Tu análisis no se ha completado",
            [f"Hola, {_e(nombre)}:",
             f"La petición nº {_e(peticion_id)} con el algoritmo <strong>{_e(algoritmo)}</strong> "
             f"ha fallado.",
             "El motivo está en la sección <strong>Resultados</strong> de la plataforma. Si no "
             "sabes cómo resolverlo, avisa al administrador."],
            color=ROJO_UAL,
            boton=_boton_plataforma(),
        ),
    )


def correo_workflow_completado(nombre: str, email: str, ejecucion_id: int,
                               workflow_nombre: str, duracion: float) -> None:
    segundos = f"{duracion:.1f}".replace(".", ",")
    enviar_correo(
        destinatario=email,
        asunto=_asunto(f"El workflow «{workflow_nombre}» ha terminado — {NOMBRE}"),
        cuerpo_html=_plantilla(
            "Tu workflow ha terminado",
            [f"Hola, {_e(nombre)}:",
             f"La ejecución nº {_e(ejecucion_id)} del workflow <strong>{_e(workflow_nombre)}</strong> "
             f"ha terminado correctamente en {segundos} segundos.",
             "Puedes ver los resultados y descargar sus ficheros en la sección "
             "<strong>Resultados</strong> de la plataforma, o en el panel de resultados del Constructor."],
            color=VERDE_OK,
            boton=_boton_plataforma(),
        ),
    )


def correo_workflow_error(nombre: str, email: str, ejecucion_id: int, workflow_nombre: str) -> None:
    enviar_correo(
        destinatario=email,
        asunto=_asunto(f"El workflow «{workflow_nombre}» ha terminado con errores — {NOMBRE}"),
        cuerpo_html=_plantilla(
            "El workflow ha terminado con errores",
            [f"Hola, {_e(nombre)}:",
             f"La ejecución nº {_e(ejecucion_id)} del workflow <strong>{_e(workflow_nombre)}</strong> "
             f"no se ha completado.",
             "El motivo está en la sección <strong>Resultados</strong> de la plataforma y en el panel "
             "de resultados del Constructor. Revisa la configuración de los nodos y vuelve a "
             "intentarlo; si no sabes cómo resolverlo, avisa al administrador."],
            color=ROJO_UAL,
            boton=_boton_plataforma(),
        ),
    )
