import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM


def correo_verificacion(nombre: str, email: str, token: str, base_url: str = "http://localhost:8000") -> None:
    enlace = f"{base_url}/verificar-email?token={token}"
    enviar_correo(
        destinatario=email,
        asunto="✅ Confirma tu cuenta — VirtualScreening",
        cuerpo_html=f"""
        <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto">
          <h2 style="color:#667eea">Bienvenido a VirtualScreening, {nombre}</h2>
          <p>Gracias por registrarte. Para activar tu cuenta y poder iniciar sesión,
             confirma tu dirección de correo haciendo clic en el botón:</p>
          <div style="text-align:center;margin:32px 0">
            <a href="{enlace}"
               style="background:#667eea;color:white;padding:14px 28px;border-radius:8px;
                      text-decoration:none;font-weight:bold;font-size:15px">
              Confirmar mi cuenta
            </a>
          </div>
          <p style="font-size:12px;color:#999">
            Si el botón no funciona, copia y pega este enlace en tu navegador:<br>
            <a href="{enlace}" style="color:#667eea">{enlace}</a>
          </p>
          <p style="font-size:12px;color:#999">
            Si no creaste esta cuenta, ignora este correo.
          </p>
          <hr style="border:none;border-top:1px solid #eee;margin:24px 0">
          <p style="font-size:12px;color:#999">VirtualScreening TFG &mdash; notificación automática</p>
        </div>
        """,
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
        asunto=f"✅ Tu petición #{peticion_id} ha finalizado — VirtualScreening",
        cuerpo_html=f"""
        <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto">
          <h2 style="color:#27ae60">¡Tu análisis ha terminado!</h2>
          <p>Hola <strong>{nombre}</strong>,</p>
          <p>La petición <strong>#{peticion_id}</strong> con el algoritmo
             <strong>{algoritmo}</strong> se ha completado con éxito.</p>
          <p>Entra en la plataforma y pulsa <em>Descargar</em> para obtener el resultado.</p>
          <hr style="border:none;border-top:1px solid #eee;margin:24px 0">
          <p style="font-size:12px;color:#999">VirtualScreening TFG &mdash; notificación automática</p>
        </div>
        """,
    )


def correo_workflow_completado(nombre: str, email: str, workflow_nombre: str, duracion: float) -> None:
    enviar_correo(
        destinatario=email,
        asunto=f"✅ Workflow '{workflow_nombre}' completado — VirtualScreening",
        cuerpo_html=f"""
        <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto">
          <h2 style="color:#27ae60">¡Tu workflow ha terminado!</h2>
          <p>Hola <strong>{nombre}</strong>,</p>
          <p>El workflow <strong>{workflow_nombre}</strong> se ha completado correctamente
             en <strong>{duracion:.1f} segundos</strong>.</p>
          <p>Entra en el KNIME Builder para ver los resultados y descargar los archivos.</p>
          <hr style="border:none;border-top:1px solid #eee;margin:24px 0">
          <p style="font-size:12px;color:#999">VirtualScreening TFG &mdash; notificación automática</p>
        </div>
        """,
    )


def correo_workflow_error(nombre: str, email: str, workflow_nombre: str, errores: list) -> None:
    lista_errores = "".join(f"<li>{e}</li>" for e in errores[:5])
    enviar_correo(
        destinatario=email,
        asunto=f"❌ Error en workflow '{workflow_nombre}' — VirtualScreening",
        cuerpo_html=f"""
        <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto">
          <h2 style="color:#e74c3c">El workflow ha encontrado errores</h2>
          <p>Hola <strong>{nombre}</strong>,</p>
          <p>El workflow <strong>{workflow_nombre}</strong> ha finalizado con errores:</p>
          <ul style="background:#fdf2f0;padding:12px 24px;border-radius:6px">{lista_errores}</ul>
          <p>Revisa la configuración de los nodos y vuelve a intentarlo.</p>
          <hr style="border:none;border-top:1px solid #eee;margin:24px 0">
          <p style="font-size:12px;color:#999">VirtualScreening TFG &mdash; notificación automática</p>
        </div>
        """,
    )


def correo_error(nombre: str, email: str, peticion_id: int, algoritmo: str, detalle: str) -> None:
    enviar_correo(
        destinatario=email,
        asunto=f"❌ Error en la petición #{peticion_id} — VirtualScreening",
        cuerpo_html=f"""
        <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto">
          <h2 style="color:#e74c3c">Se produjo un error en tu análisis</h2>
          <p>Hola <strong>{nombre}</strong>,</p>
          <p>La petición <strong>#{peticion_id}</strong> con el algoritmo
             <strong>{algoritmo}</strong> ha fallado.</p>
          <p><strong>Detalle:</strong> <code style="background:#f0f0f0;padding:2px 6px">{detalle}</code></p>
          <p>Contacta con el administrador si el error persiste.</p>
          <hr style="border:none;border-top:1px solid #eee;margin:24px 0">
          <p style="font-size:12px;color:#999">VirtualScreening TFG &mdash; notificación automática</p>
        </div>
        """,
    )
