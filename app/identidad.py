"""
Nombre y colores de la plataforma para lo que genera el backend: los correos
(app/email_utils.py) y las paginas que sirve el propio backend, como la de
confirmar la cuenta (app/paginas.py). Specs 004 y 005.

Son los de frontend/src/styles/tokens.css. Ni un cliente de correo ni una
pagina suelta del backend cargan esa hoja de estilo, asi que se repiten aqui,
en un unico sitio: si cambia el azul de la UAL, se cambia en tokens.css y aqui.
"""

NOMBRE = "MolServer"

AZUL_UAL = "#0A4382"   # cabecera y botones
TEXTO    = "#323232"
TEXTO_2  = "#5B6770"   # texto secundario: 5.6:1 sobre blanco
LINEA    = "#D5D9DE"
GRIS_UAL = "#ECEDEF"   # fondo de pagina
VERDE_OK = "#1F7A55"   # titulos de algo que ha ido bien
ROJO_UAL = "#CA143F"   # titulos de algo que ha fallado
CIAN_UAL = "#02BEFF"   # foco del teclado, como en la aplicacion
