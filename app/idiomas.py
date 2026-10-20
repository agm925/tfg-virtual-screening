"""
Los mensajes de la API en el idioma de la interfaz (spec 014, R7).

El código escribe sus mensajes en español, como siempre (principio 6), y aquí
se traducen al salir: el frontend manda `Accept-Language: en` cuando la
interfaz está en inglés y el manejador de HTTPException de main.py pasa el
`detail` por `traducir`. Así ninguna de las ~90 llamadas que lanzan un error
tiene que saber nada de idiomas, y en español la respuesta no cambia.

Cada entrada del catálogo es una plantilla con huecos ({nombre}); un mensaje
se traduce si encaja ENTERO con una plantilla, y lo que cae en cada hueco se
traduce a su vez (un motivo del banco dentro de «Con las opciones … marcadas:
{motivo}»). Lo que no encaja se deja tal cual: mejor un mensaje en español
que uno inventado. tests/test_idiomas.py comprueba que cada mensaje del
código tiene su plantilla.
"""
import re
from functools import lru_cache

IDIOMAS = ("es", "en")

CATALOGO = [
    # --- Sesión y cuentas (auth.py, rate_limit.py, main.py) ---
    ("No autenticado. Falta la cabecera Authorization: Bearer <token>.",
     "Not authenticated. The Authorization: Bearer <token> header is missing."),
    ("Usuario no encontrado.", "User not found."),
    ("Usuario no encontrado", "User not found"),
    ("La sesión ha caducado. Vuelve a iniciar sesión.", "Your session has expired. Please sign in again."),
    ("Token de sesión inválido.", "Invalid session token."),
    ("La contraseña ha cambiado. Vuelve a iniciar sesión.", "The password has changed. Please sign in again."),
    ("Esta operación requiere el rol: {roles}.", "This operation requires the role: {roles}."),
    ("Esta cuenta está desactivada. Contacta con un administrador.",
     "This account is deactivated. Contact an administrator."),
    ("Demasiados intentos de inicio de sesión fallidos. Cuenta bloqueada temporalmente, "
     "vuelve a intentarlo en {segundos}s.",
     "Too many failed sign-in attempts. The account is temporarily locked, try again in {segundos}s."),
    ("Has pedido demasiados enlaces para este correo. Vuelve a intentarlo dentro de {minutos} min.",
     "You have requested too many links for this email. Try again in {minutos} min."),
    ("Credenciales incorrectas", "Incorrect credentials"),
    ("Debes confirmar tu correo electrónico antes de iniciar sesión. Revisa tu bandeja de entrada.",
     "You must confirm your email before signing in. Check your inbox."),
    ("El email ya está registrado", "That email is already registered"),
    ("No existe ningún usuario con ese correo.", "There is no user with that email."),
    ("No se ha podido enviar el correo. Inténtalo más tarde.", "The email could not be sent. Try again later."),
    ("El enlace no es válido o ha caducado. Pide uno nuevo.", "The link is not valid or has expired. Request a new one."),
    ("Rol no válido. Debe ser uno de: {roles}.", "Invalid role. It must be one of: {roles}."),
    ("No puedes retirarte a ti mismo el rol de administrador.", "You cannot remove the administrator role from yourself."),
    ("No puedes desactivar tu propia cuenta.", "You cannot deactivate your own account."),

    # --- Ficheros y moléculas ---
    ("Demasiados archivos con ese nombre.", "Too many files with that name."),
    ("Demasiados algoritmos con ese nombre.", "Too many algorithms with that name."),
    ("Nombre de archivo no válido", "Invalid file name"),
    ("El archivo supera el tamaño máximo permitido ({mb} MB).", "The file exceeds the maximum allowed size ({mb} MB)."),
    ("El archivo debe ser una molécula en uno de estos formatos: {formatos}.",
     "The file must be a molecule in one of these formats: {formatos}."),
    ("El tipo debe ser 'molecula' o 'base_de_datos'", "The type must be 'molecula' or 'base_de_datos'"),
    ("Formato no soportado. Usa: {formatos}", "Unsupported format. Use: {formatos}"),
    ("Las bases de datos deben estar en formato SDF (.sdf)", "Libraries must be in SDF format (.sdf)"),
    ("Archivo no encontrado", "File not found"),
    ("No tienes permiso para ver las moléculas de otro usuario", "You are not allowed to see another user's molecules"),
    ("Ese fichero no existe o no tienes acceso a él.", "That file does not exist or you do not have access to it."),
    ("Este fichero es privado: solo lo puede usar quien lo subió.",
     "This file is private: only the person who uploaded it can use it."),
    ("Este archivo es el resultado de una ejecución de otro usuario.", "This file is the result of another user's run."),
    ("Solo el propietario puede borrar este archivo.", "Only the owner can delete this file."),
    ("El archivo físico no se encuentra en el servidor", "The file cannot be found on the server"),

    # --- Peticiones, workflows y ejecuciones ---
    ("Petición no encontrada", "Request not found"),
    ("No tienes permiso para descargar este resultado", "You are not allowed to download this result"),
    ("El resultado aún no está listo o la petición falló", "The result is not ready yet or the request failed"),
    ("No tienes permiso para ver este historial", "You are not allowed to see this history"),
    ("No tienes permiso para ver esta petición", "You are not allowed to see this request"),
    ("No tienes permiso para borrar esta petición", "You are not allowed to delete this request"),
    ("No tienes permiso para ver estos workflows", "You are not allowed to see these workflows"),
    ("Workflow no encontrado", "Workflow not found"),
    ("No tienes permiso sobre este workflow", "You do not have permission on this workflow"),
    ("El flujo usa '{fichero}', que no es tuyo: {motivo}", "The workflow uses '{fichero}', which is not yours: {motivo}"),
    ("Ejecución no encontrada", "Run not found"),
    ("No se puede cancelar una ejecución en estado '{estado}'", "A run in state '{estado}' cannot be cancelled"),
    ("No tienes permiso para ver esta ejecución", "You are not allowed to see this run"),
    ("No tienes permiso para borrar esta ejecución", "You are not allowed to delete this run"),
    ("Esta ejecución sigue en marcha. Cancélala antes de borrarla.",
     "This run is still in progress. Cancel it before deleting it."),

    # --- Algoritmos ---
    ("El archivo debe ser un script de Python (.py)", "The file must be a Python script (.py)"),
    ("El tipo debe ser uno de: {tipos}", "The type must be one of: {tipos}"),
    ("El script supera el tamaño máximo permitido ({kb} KB).", "The script exceeds the maximum allowed size ({kb} KB)."),
    ("El script está vacío.", "The script is empty."),
    ("Tipo de algoritmo desconocido: '{tipo}'.", "Unknown algorithm type: '{tipo}'."),
    ("El algoritmo indicado no existe.", "The given algorithm does not exist."),
    ("Este algoritmo ha sido desactivado por un administrador y no puede ejecutarse.",
     "This algorithm has been deactivated by an administrator and cannot be run."),
    ("Este algoritmo es privado de otro usuario.", "This algorithm is private to another user."),
    ("Algoritmo no encontrado", "Algorithm not found"),
    ("La interfaz del algoritmo no es válida: {motivo}", "The algorithm interface is not valid: {motivo}"),
    ("Interfaz no válida: {motivo}", "Invalid interface: {motivo}"),

    # --- Interfaz de un algoritmo (banco_pruebas.validar_interfaz) ---
    ("La interfaz del algoritmo no tiene el formato esperado.", "The algorithm interface does not have the expected format."),
    ("La interfaz lleva campos que no se conocen: {campos}.", "The interface has unknown fields: {campos}."),
    ("El algoritmo debe tener entre 1 y {n} entradas.", "The algorithm must have between 1 and {n} inputs."),
    ("El algoritmo puede tener como mucho {n} opciones.", "The algorithm can have at most {n} options."),
    ("Entrada {n}: la clase debe ser molécula o proteína.", "Input {n}: the kind must be molecule or protein."),
    ("Opción {n}: no tiene el formato esperado.", "Option {n}: it does not have the expected format."),
    ("Opción {n}: «{opcion}» está repetida.", "Option {n}: «{opcion}» is repeated."),
    ("{que}: falta el nombre.", "{que}: the name is missing."),
    ("{que}: el nombre no puede estar vacío.", "{que}: the name cannot be empty."),
    ("{que}: el nombre no puede pasar de {n} caracteres.", "{que}: the name cannot be longer than {n} characters."),
    ("{que}: el nombre no puede llevar saltos de línea ni caracteres de control.",
     "{que}: the name cannot contain line breaks or control characters."),
    ("{que}: «{opcion}» no es una opción válida (por ejemplo -o o --all).",
     "{que}: «{opcion}» is not a valid option (for example -o or --all)."),
    ("Entrada {n}", "Input {n}"),
    ("Opción {n}", "Option {n}"),

    # --- Banco de pruebas ---
    ("El algoritmo no ha superado la prueba de validación.", "The algorithm did not pass the validation test."),
    ("El algoritmo se ejecuta sobre moléculas de referencia antes de aceptarlo, con la llamada que se ve "
     "arriba. Comprueba que coincide con la que espera tu script --sus entradas, cómo recibe la salida y "
     "sus opciones-- y que termina con código 0.",
     "The algorithm is run on reference molecules before it is accepted, with the call shown above. Check "
     "that it matches the one your script expects --its inputs, how it receives the output and its "
     "options-- and that it ends with exit code 0."),
    ("El servicio de validación de algoritmos no está disponible, así que no se puede comprobar el "
     "algoritmo antes de aceptarlo. Inténtalo de nuevo en unos minutos.",
     "The algorithm validation service is not available, so the algorithm cannot be checked before "
     "accepting it. Try again in a few minutes."),
    ("El servicio de validación de algoritmos respondió con un error ({codigo}).",
     "The algorithm validation service answered with an error ({codigo})."),
    ("Faltan las moléculas de referencia del banco de pruebas ({fichero}). Es un problema de la "
     "instalación, no de tu algoritmo.",
     "The reference molecules of the test bench are missing ({fichero}). It is a problem with the "
     "installation, not with your algorithm."),
    ("Con las opciones {opciones} marcadas: {motivo}", "With the options {opciones} ticked: {motivo}"),
    ("El algoritmo no terminó en {segundos} segundos sobre una molécula pequeña de referencia. Revisa si "
     "entra en un bucle infinito o espera una entrada por teclado.",
     "The algorithm did not finish in {segundos} seconds on a small reference molecule. Check whether it "
     "enters an infinite loop or waits for keyboard input."),
    ("No se pudo ejecutar el script: {error}", "The script could not be run: {error}"),
    ("El algoritmo terminó con error al ejecutarlo sobre las moléculas de referencia. Se ejecutó así: {llamada}",
     "The algorithm finished with an error when run on the reference molecules. It was run like this: {llamada}"),
    ("El algoritmo terminó correctamente pero no escribió ningún fichero de salida. Comprueba que escribe "
     "la salida en la ruta que recibe. Se ejecutó así: {llamada}",
     "The algorithm finished correctly but did not write any output file. Check that it writes the output "
     "to the path it receives. It was run like this: {llamada}"),
    ("El algoritmo devolvió un resultado de error sobre las moléculas de referencia.",
     "The algorithm returned an error result on the reference molecules."),
    ("El algoritmo devolvió un JSON sin ningún valor numérico. El cribado por lotes necesita una "
     "puntuación para poder ordenar el ranking.",
     "The algorithm returned a JSON without any numerical value. Batch screening needs a score to sort "
     "the ranking."),
    ("El fichero de salida tiene extensión de molécula pero no contiene ninguna que se pueda leer.",
     "The output file has a molecule extension but does not contain any readable molecule."),

    # --- Errores de una ejecución (workflow_executor.py) ---
    # Los de los nodos que cita el tutorial y la forma en que se envuelven; el
    # resto suele llevar la salida del algoritmo y se enseña tal cual. Los
    # traduce GET /workflows/ejecuciones/{id} al responder.
    ("Error en nodo {nodo}: {motivo}", "Error in node {nodo}: {motivo}"),
    ("Error ejecutando nodo {nodo}: {motivo}", "Error running node {nodo}: {motivo}"),
    ("Nodo {nodo}: no se ha subido ninguna molécula", "Node {nodo}: no molecule has been uploaded"),
    ("Nodo {nodo}: sin entrada de molécula", "Node {nodo}: no molecule input"),
    ("Nodo {nodo}: faltan las dos moléculas de entrada", "Node {nodo}: both input molecules are missing"),
    ("Nodo {nodo}: se necesitan ligando y receptor", "Node {nodo}: a ligand and a receptor are needed"),
    ("Nodo {nodo}: no se ha elegido ninguna biblioteca", "Node {nodo}: no library has been chosen"),
    ("Elegir molécula: no se ha elegido ninguna molécula. Abre el nodo y elige una de la lista.",
     "Choose molecule: no molecule has been chosen. Open the node and choose one from the list."),
    ("El workflow no tiene ningún nodo «Elegir biblioteca».", "The workflow has no «Choose library» node."),
    ("El nodo «Elegir biblioteca» no tiene ninguna biblioteca elegida.",
     "The «Choose library» node has no library chosen."),

    # --- Visor 3D (visor.py y sus endpoints) ---
    ("Este fichero no es una biblioteca: se abre entero, sin lista.",
     "This file is not a library: it opens whole, without a list."),
    ("Este fichero tiene varias moléculas: elige una de la lista.",
     "This file has several molecules: choose one from the list."),
    ("Esa molécula no existe en el fichero.", "That molecule does not exist in the file."),
    ("Esta molécula está dañada en el fichero y no se puede dibujar. Si viene de una biblioteca, puedes "
     "limpiarla con un workflow de preparación.",
     "This molecule is damaged in the file and cannot be drawn. If it comes from a library, you can clean "
     "it with a preparation workflow."),
    ("Este registro no tiene átomos, así que no hay nada que dibujar.",
     "This record has no atoms, so there is nothing to draw."),
    ("Este fichero describe la molécula sin coordenadas 3D (formato SMILES), así que no se puede dibujar. "
     "Puedes generar su 3D con un workflow de preparación y abrir el resultado aquí.",
     "This file describes the molecule without 3D coordinates (SMILES format), so it cannot be drawn. "
     "You can generate its 3D structure with a preparation workflow and open the result here."),
    ("Este fichero no contiene moléculas que se puedan dibujar.", "This file does not contain molecules that can be drawn."),
    ("Molécula nº {n}", "Molecule no. {n}"),
]

_HUECO = re.compile(r"\{(\w+)\}")


def huecos(plantilla: str) -> list:
    return sorted(_HUECO.findall(plantilla))


def _patron(plantilla: str):
    """La plantilla como expresión regular: el texto fijo literal y cada hueco, un grupo."""
    partes, inicio = [], 0
    for m in _HUECO.finditer(plantilla):
        partes.append(re.escape(plantilla[inicio:m.start()]))
        partes.append(f"(?P<{m.group(1)}>.+?)")
        inicio = m.end()
    partes.append(re.escape(plantilla[inicio:]))
    return re.compile("".join(partes), re.DOTALL)


@lru_cache(maxsize=1)
def _compilado():
    return [(_patron(es), en) for es, en in CATALOGO]


def plantilla_de(texto: str):
    """La plantilla que encaja con el texto entero y sus huecos, o None. «X» vale como hueco."""
    for patron, en in _compilado():
        m = patron.fullmatch(texto)
        if m:
            return en, m.groupdict()
    return None


def traducir(texto, idioma: str):
    """El texto en `idioma`; en español, o si no hay plantilla, tal cual."""
    if idioma != "en" or not isinstance(texto, str) or not texto:
        return texto
    encontrada = plantilla_de(texto)
    if encontrada is None:
        return texto
    en, valores = encontrada
    # Lo que cae en un hueco puede ser a su vez un mensaje conocido.
    return en.format(**{k: traducir(v, idioma) for k, v in valores.items()})


def idioma_de(accept_language) -> str:
    """'en' si la cabecera Accept-Language empieza por inglés; si no, español."""
    if accept_language and accept_language.strip().lower().startswith("en"):
        return "en"
    return "es"


def traducir_detail(detail, idioma: str):
    """El `detail` de una HTTPException: un texto, o el diccionario del rechazo del banco.

    Del diccionario se traducen los textos para el usuario; `salida` y
    `detalle` son lo que escribió el script y se dejan como están.
    """
    if isinstance(detail, dict):
        return {k: (traducir(v, idioma) if k in ("mensaje", "motivo", "ayuda") else v)
                for k, v in detail.items()}
    return traducir(detail, idioma)
