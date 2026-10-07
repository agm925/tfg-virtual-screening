"""
Paginas HTML que sirve el propio backend, fuera de la aplicacion React
(spec 005). Hoy solo hay una: la del enlace del correo de confirmacion, que se
abre desde el programa de correo y muchas veces en el movil.

Antes estaba escrita dentro de app/main.py, con el aspecto anterior a la
identidad de la UAL (morado, sombras, emojis), y sin idioma, titulo ni ajuste
para el movil. El nombre y los colores salen de app/identidad.py, los mismos
que los correos.

Ninguna lleva datos del usuario. La unica variable es PUBLIC_URL, la direccion
de la plataforma (spec 004), y se escapa igualmente.
"""
import html

from app.config import PUBLIC_URL
from app.identidad import NOMBRE, AZUL_UAL, TEXTO, TEXTO_2, LINEA, GRIS_UAL, VERDE_OK, ROJO_UAL, CIAN_UAL


def _pagina(pestana: str, titulo: str, color: str, parrafos: list) -> str:
    """La pagina comun: cabecera con el escudo, un panel con el mensaje y el
    boton para entrar en la plataforma. `parrafos` son texto fijo, sin datos
    del usuario."""
    base = html.escape(PUBLIC_URL, quote=True)
    escudo = f"{base}/ual/escudo-ual.png"
    cuerpo = "\n".join(f"      <p>{p}</p>" for p in parrafos)
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{pestana} — {NOMBRE}</title>
  <link rel="icon" type="image/png" href="{escudo}">
  <style>
    body {{ margin: 0; background: {GRIS_UAL}; color: {TEXTO};
           font-family: "Segoe UI", system-ui, -apple-system, Arial, sans-serif; }}
    .cabecera {{ background: {AZUL_UAL}; color: #FFFFFF; }}
    .cabecera div {{ max-width: 560px; margin: 0 auto; padding: 14px 16px;
                    display: flex; align-items: center; gap: 12px;
                    font-size: 20px; font-weight: 700; }}
    .cabecera img {{ width: 40px; height: 40px; }}
    main {{ max-width: 560px; margin: 32px auto; padding: 0 16px; }}
    .panel {{ background: #FFFFFF; border: 1px solid {LINEA}; border-radius: 2px;
             padding: 28px 24px; }}
    h1 {{ margin: 0 0 16px; font-size: 24px; color: {color}; }}
    p {{ margin: 0 0 14px; line-height: 1.6; }}
    .boton {{ display: inline-block; margin-top: 12px; padding: 12px 24px;
             background: {AZUL_UAL}; color: #FFFFFF; border-radius: 2px;
             font-weight: 700; text-decoration: none; }}
    .boton:focus-visible {{ outline: 3px solid {CIAN_UAL}; outline-offset: 2px; }}
    footer {{ max-width: 560px; margin: 0 auto 32px; padding: 0 16px;
             font-size: 13px; color: {TEXTO_2}; }}
  </style>
</head>
<body>
  <header class="cabecera"><div><img src="{escudo}" alt="">{NOMBRE}</div></header>
  <main>
    <div class="panel">
      <h1>{titulo}</h1>
{cuerpo}
      <a class="boton" href="{base}/">Ir a {NOMBRE}</a>
    </div>
  </main>
  <footer>{NOMBRE} · Universidad de Almería</footer>
</body>
</html>
"""


def pagina_cuenta_confirmada() -> str:
    return _pagina(
        "Cuenta confirmada", "Cuenta confirmada", VERDE_OK,
        [f"Tu cuenta está confirmada. Ya puedes iniciar sesión en {NOMBRE}."],
    )


def pagina_enlace_no_valido() -> str:
    # El enlace se borra al usarse, y hay servicios de correo que lo abren
    # por su cuenta para analizarlo antes de que el usuario lo pulse: la cuenta
    # queda confirmada, pero el usuario llega aqui. Por eso no basta con decir
    # que el enlace no vale. No se ofrece reenviar el correo porque no existe:
    # un administrador activa la cuenta a mano (decision de la spec 005).
    return _pagina(
        "Enlace no válido", "Este enlace ya no sirve", ROJO_UAL,
        ["El enlace de confirmación solo funciona una vez.",
         "Si ya lo pulsaste antes, o tu programa de correo lo abrió por ti, lo más probable "
         "es que tu cuenta ya esté confirmada: prueba a iniciar sesión.",
         "Si no puedes entrar, pide a un administrador de la plataforma que active tu cuenta."],
    )
