import os
from fastapi import FastAPI, Depends, HTTPException, File, UploadFile, Form, Query, Response
from sqlalchemy import or_, func
from sqlalchemy.orm import Session, joinedload
from app.database import engine, SessionLocal
from app import models, permisos, schemas
from fastapi.responses import FileResponse, HTMLResponse
import uuid
from fastapi.middleware.cors import CORSMiddleware
from app.tasks import (FICHEROS_DEL_CRIBADO, ejecutar_peticion_async,
                       ejecutar_workflow_async, ejecutar_workflow_batch_async)
from app.email_utils import correo_verificacion
from app.auth import (
    hash_password, verify_password, crear_access_token,
    obtener_usuario_actual, requiere_rol, es_admin,
)
from app.celery_app import celery_app
from app.config import (
    CORS_ORIGINS, EXECUTION_MODE, WORKER_CONCURRENCY,
    MAX_ALGORITMO_BYTES, MAX_SUBIDA_BYTES, TAMANO_TROZO_SUBIDA,
)
from app.rate_limit import verificar_no_bloqueado, registrar_intento_fallido, limpiar_intentos
from app.logging_config import logger, configurar_logging
from app.banco_pruebas import probar_algoritmo
from app.formatos import EXTENSIONES_ENTRADA_ALGORITMO, contar_moleculas_sdf
from app import indice_sdf
from datetime import datetime, timezone
import shutil
import tempfile

configurar_logging()

# Creamos las tablas en la base de datos (si no existen)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="API Virtual Screening",
    description="Backend para ejecución de algoritmos biomoleculares",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    # Lista explícita de orígenes (ver CORS_ORIGINS en app/config.py). Con la
    # API servida bajo /api/ del mismo origen que la SPA, las peticiones del
    # frontend no son cross-origin y no pasan por aquí: esta lista solo cubre
    # despliegues donde el frontend viva en otro origen.
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],  # Permite GET, POST, PUT, DELETE...
    allow_headers=["*"],  # Permite cualquier cabecera
    expose_headers=["X-Total-Count"],  # cabecera de paginación: por defecto el navegador la oculta al JS
)

# --- DEPENDENCIA DE BASE DE DATOS ---
# Esto es una "manguera" que se abre cuando un usuario hace una petición y se cierra al terminar
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- PAGINACIÓN COMPARTIDA ---
# limit acotado a 500: sin tope, una consulta como GET /algoritmos crece sin
# límite con el catálogo y nada impide pedir de golpe toda la tabla.
class Paginacion:
    def __init__(
        self,
        limit: int = Query(100, ge=1, le=500, description="Máximo de resultados a devolver"),
        offset: int = Query(0, ge=0, description="Resultados a saltar desde el principio"),
    ):
        self.limit = limit
        self.offset = offset


# --- PROTECCIÓN CONTRA PATH TRAVERSAL ---
# Varios endpoints construyen una ruta dentro de uploads/ o algoritmos/ a
# partir de un nombre de archivo que llega directamente del cliente
# (archivo.filename de un UploadFile, o un {nombre_archivo} de la URL). Sin
# sanear ese nombre, un valor como "../../app/main.py" en el filename de una
# subida, o "..%2F..%2Fapp%2Fmain.py" en la URL, escapa del directorio
# previsto: os.path.join("uploads", "../../app/main.py") apunta fuera de
# uploads/. os.path.basename() descarta cualquier componente de directorio
# del nombre, dejando solo el nombre de archivo final.
def nombre_archivo_seguro(nombre: str) -> str:
    """Nombre base, sin componentes de ruta -- para sanear un filename antes de guardarlo."""
    return os.path.basename((nombre or "").replace("\\", "/"))


def _archivo_registrado(nombre_archivo: str, db: Session):
    """Devuelve la fila de `archivos` para este nombre, o None si no consta."""
    return permisos.archivo_registrado(nombre_archivo, db)


def exigir_acceso_a_archivo(nombre_archivo: str, db: Session, usuario: models.Usuario,
                            para_borrar: bool = False) -> None:
    """
    Comprueba que `usuario` puede leer --o borrar-- este fichero de uploads/,
    y responde 403 si no.

    Las reglas viven en app/permisos.py porque el motor de workflows necesita
    las mismas y no puede importar este módulo (importación circular vía las
    tareas de Celery). Aquí solo se traduce a HTTP.
    """
    try:
        permisos.comprobar_acceso_a_archivo(
            nombre_archivo, db, usuario.id,
            usuario_es_admin=es_admin(usuario), para_borrar=para_borrar,
        )
    except permisos.AccesoDenegado as e:
        raise HTTPException(status_code=403, detail=e.mensaje)


def registrar_archivo(db: Session, nombre: str, propietario_id, visibilidad,
                      tipo=None, tamano_bytes=None, num_moleculas=None,
                      ejecucion_id=None, peticion_id=None) -> None:
    """Da de alta un fichero en el registro, o actualiza el que ya existiera."""
    archivo = _archivo_registrado(nombre, db)
    if archivo is None:
        archivo = models.Archivo(nombre=nombre)
        db.add(archivo)
    archivo.propietario_id = propietario_id
    archivo.visibilidad = visibilidad
    if tipo is not None:
        archivo.tipo = tipo
    if tamano_bytes is not None:
        archivo.tamano_bytes = tamano_bytes
    if num_moleculas is not None:
        archivo.num_moleculas = num_moleculas
    if ejecucion_id is not None:
        archivo.ejecucion_id = ejecucion_id
    if peticion_id is not None:
        archivo.peticion_id = peticion_id


def borrar_archivos_registrados(db: Session, filtro) -> int:
    """
    Borra de disco y del registro los ficheros que cumplan `filtro`.

    Hasta ahora nada limpiaba nada: los intermedios de cada nodo y los
    resultados se acumulaban indefinidamente en uploads/ --mas de dos mil
    ficheros residuales en el entorno de desarrollo, con cadenas como
    "..._resultado_resultado_resultado.mol2"--. Con el registro, borrar una
    peticion o una ejecucion puede llevarse consigo lo que produjo.
    """
    borrados = 0
    for archivo in db.query(models.Archivo).filter(filtro).all():
        ruta = os.path.join("uploads", archivo.nombre)
        try:
            if os.path.exists(ruta):
                os.remove(ruta)
                borrados += 1
            # Un indice huerfano no hace dano --caduca por tamano y fecha--,
            # pero es basura en uploads/.indices/.
            indice_sdf.borrar(ruta)
        except OSError as e:
            logger.warning("no_se_pudo_borrar_archivo",
                           extra={"nombre": archivo.nombre, "error": str(e)})
        db.delete(archivo)
    return borrados


def nombre_libre(nombre: str, db: Session) -> str:
    """
    Devuelve un nombre que no esté ya ocupado en uploads/, anadiendo un sufijo
    numérico si hace falta.

    Antes las subidas escribían sin comprobar: si dos usuarios subían un
    `ligando.mol2`, el segundo destruía el fichero del primero, y la petición
    pendiente del primero pasaba a ejecutarse SOBRE LOS DATOS DEL SEGUNDO, sin
    ningún aviso. Renombrar en vez de sobrescribir elimina esa clase de
    corrupción por completo.
    """
    if _archivo_registrado(nombre, db) is None and not os.path.exists(os.path.join("uploads", nombre)):
        return nombre
    base, ext = os.path.splitext(nombre)
    for n in range(2, 1000):
        candidato = f"{base}_{n}{ext}"
        if _archivo_registrado(candidato, db) is None and not os.path.exists(os.path.join("uploads", candidato)):
            return candidato
    raise HTTPException(status_code=409, detail="Demasiados archivos con ese nombre.")


def nombre_algoritmo_libre(nombre: str, db: Session) -> str:
    """
    Lo mismo que `nombre_libre`, pero para el catálogo de algoritmos.

    Existía para uploads/ y no para algoritmos/, y la diferencia importaba
    mucho más aquí: `shutil.move` sobreescribía el .py sin preguntar, así que
    subir un algoritmo llamado como otro REEMPLAZABA el código del otro
    usuario. Las dos filas del catálogo seguían apuntando al mismo fichero, y
    la primera pasaba a ejecutar un script que nunca superó el banco de
    pruebas: la validación se anula sola. Renombrar en vez de sobreescribir lo
    cierra, y de paso explica el `filtroLipinski.py` duplicado que había en el
    catálogo.
    """
    def ocupado(candidato: str) -> bool:
        existe_fila = (db.query(models.Algoritmo)
                       .filter(models.Algoritmo.ruta_archivo == candidato).first() is not None)
        return existe_fila or os.path.exists(os.path.join("algoritmos", candidato))

    if not ocupado(nombre):
        return nombre
    base, ext = os.path.splitext(nombre)
    for n in range(2, 1000):
        candidato = f"{base}_{n}{ext}"
        if not ocupado(candidato):
            return candidato
    raise HTTPException(status_code=409, detail="Demasiados algoritmos con ese nombre.")


# --- ESCRITURA DE SUBIDAS CON LÍMITE DE TAMAÑO ---
# Los endpoints de subida hacían `contenido = await archivo.read()`, que carga
# el fichero ENTERO en memoria: un SDF de ChEMBL de 500 MB son 500 MB de RAM en
# el proceso web, y varias subidas simultáneas lo tumban. Comprobar el tamaño
# después de ese read() no arregla nada, porque para entonces la memoria ya se
# ha consumido: el límite solo es una defensa real si se aplica MIENTRAS se
# escribe. De ahí que el volcado se haga por trozos y se aborte en cuanto se
# supera el máximo, borrando lo escrito hasta ese momento.
async def guardar_subida(archivo: UploadFile, ruta_destino: str, max_bytes: int) -> int:
    """Vuelca un UploadFile a disco por trozos. Devuelve los bytes escritos.
    Lanza 413 si excede max_bytes, sin dejar el fichero parcial en disco."""
    escritos = 0
    try:
        with open(ruta_destino, "wb") as destino:
            while True:
                trozo = await archivo.read(TAMANO_TROZO_SUBIDA)
                if not trozo:
                    break
                escritos += len(trozo)
                if escritos > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"El archivo supera el tamaño máximo permitido "
                            f"({max_bytes // (1024 * 1024)} MB)."
                        ),
                    )
                destino.write(trozo)
    except Exception:
        # Un fichero a medio escribir es peor que ninguno: lo dejaríamos en
        # uploads/ como si fuera una molécula válida.
        if os.path.exists(ruta_destino):
            os.remove(ruta_destino)
        raise
    return escritos


def exigir_nombre_archivo_seguro(nombre: str) -> str:
    """Como nombre_archivo_seguro, pero rechaza con 400 si el nombre recibido
    no era ya "limpio" -- para endpoints que referencian un archivo existente
    por nombre (GET/DELETE), donde un intento de path traversal debe
    rechazarse explícitamente en vez de reinterpretarse en silencio."""
    seguro = nombre_archivo_seguro(nombre)
    if not seguro or seguro != nombre:
        raise HTTPException(status_code=400, detail="Nombre de archivo no válido")
    return seguro


# --- RUTAS (ENDPOINTS) ---

@app.get("/")
def ruta_raiz():
    return {"estado": "OK", "mensaje": "¡El motor del TFG está funcionando!"}

@app.post("/registro")
def registrar_usuario(usuario: schemas.UsuarioRegistro, db: Session = Depends(get_db)):
    """
    Registra un nuevo usuario. Envía un correo de verificación antes de activar la cuenta.
    """
    usuario_existente = db.query(models.Usuario).filter(models.Usuario.email == usuario.email).first()
    if usuario_existente:
        raise HTTPException(status_code=400, detail="El email ya está registrado")

    token = str(uuid.uuid4())
    nuevo_usuario = models.Usuario(
        nombre=usuario.nombre,
        email=usuario.email,
        password_hash=hash_password(usuario.password_hash),
        rol="biologo",
        email_verificado=False,
        token_verificacion=token,
    )
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)

    try:
        correo_verificacion(nuevo_usuario.nombre, nuevo_usuario.email, token)
    except Exception:
        pass  # Si falla el correo el usuario puede pedir reenvío; no bloqueamos el registro

    logger.info("usuario_registrado", extra={"usuario_id": nuevo_usuario.id, "email": nuevo_usuario.email})
    return {"mensaje": "Registro completado. Revisa tu correo para confirmar tu cuenta."}


@app.get("/verificar-email")
def verificar_email(token: str, db: Session = Depends(get_db)):
    """Activa la cuenta del usuario cuando hace clic en el enlace del correo."""
    usuario = db.query(models.Usuario).filter(models.Usuario.token_verificacion == token).first()
    if not usuario:
        return HTMLResponse(content=_html_verificacion("error"), status_code=400)

    usuario.email_verificado   = True
    usuario.token_verificacion = None
    db.commit()
    return HTMLResponse(content=_html_verificacion("ok"))


def _html_verificacion(estado: str) -> str:
    if estado == "ok":
        return """
        <html><body style="font-family:Arial,sans-serif;text-align:center;padding:60px;background:#f8f9fa">
          <div style="max-width:480px;margin:auto;background:white;border-radius:16px;padding:40px;
                      box-shadow:0 4px 20px rgba(0,0,0,0.08)">
            <div style="font-size:3rem">✅</div>
            <h2 style="color:#27ae60">¡Cuenta confirmada!</h2>
            <p style="color:#555">Tu dirección de correo ha sido verificada correctamente.
               Ya puedes iniciar sesión en la plataforma.</p>
            <a href="http://localhost:5173"
               style="display:inline-block;margin-top:20px;background:#667eea;color:white;
                      padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold">
              Ir a la plataforma →
            </a>
          </div>
        </body></html>
        """
    return """
    <html><body style="font-family:Arial,sans-serif;text-align:center;padding:60px;background:#f8f9fa">
      <div style="max-width:480px;margin:auto;background:white;border-radius:16px;padding:40px;
                  box-shadow:0 4px 20px rgba(0,0,0,0.08)">
        <div style="font-size:3rem">❌</div>
        <h2 style="color:#e74c3c">Enlace inválido</h2>
        <p style="color:#555">Este enlace de verificación no es válido o ya fue utilizado.</p>
        <a href="http://localhost:5173"
           style="display:inline-block;margin-top:20px;background:#667eea;color:white;
                  padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold">
          Volver a la plataforma →
        </a>
      </div>
    </body></html>
    """

@app.post("/algoritmos", response_model=schemas.AlgoritmoRespuesta)
async def subir_algoritmo(
    nombre: str = Form(...),
    descripcion: str = Form(...),
    tipo: str = Form(...),                 # Campo tipo obligatorio desde el formulario
    es_publico: bool = Form(False),        # Añadido: Para aprovechar tu campo es_publico
    archivo: UploadFile = File(...),       # Lo llamamos "archivo" para no confundirlo con la ruta
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    """
    Sube un script de Python (.py) y lo registra en la base de datos.
    El tipo lo declara el propio formulario (parámetro `tipo`); ya no hace
    falta que el script lo repita en un comentario `# TIPO_ALGORITMO`, porque
    quien de verdad decide si se acepta es el banco de pruebas: ejecuta el
    script invocándolo como corresponde a ese tipo --una molécula, dos, o
    ligando más receptor-- y lo rechaza si no cumple el contrato (ver
    app/banco_pruebas.py). Cualquier usuario autenticado puede subir
    algoritmos al catálogo. El autor se toma del usuario autenticado, nunca
    de un campo del formulario.
    """
    autor_id = usuario_actual.id
    # 0. Saneamos el nombre de archivo (protección contra path traversal)
    nombre_fichero = nombre_archivo_seguro(archivo.filename)
    if not nombre_fichero:
        raise HTTPException(status_code=400, detail="Nombre de archivo no válido")

    # 1. Validamos que sea un script de Python
    if not nombre_fichero.endswith('.py'):
        raise HTTPException(status_code=400, detail="El archivo debe ser un script de Python (.py)")

    # 2. Validamos que el tipo sea válido
    tipos_validos = ["alineacion", "comparacion", "preprocesado", "docking"]
    if tipo not in tipos_validos:
        raise HTTPException(
            status_code=400,
            detail=f"El tipo debe ser uno de: {', '.join(tipos_validos)}"
        )

    # 3. Leemos el archivo a memoria, con un tope bajo: un algoritmo es un
    #    script de unos pocos KB, y este endpoint acepta código que después se
    #    ejecutará en el worker o en el nodo del clúster.
    contenido_archivo = await archivo.read(MAX_ALGORITMO_BYTES + 1)
    if len(contenido_archivo) > MAX_ALGORITMO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"El script supera el tamaño máximo permitido ({MAX_ALGORITMO_BYTES // 1024} KB).",
        )

    # 4. BANCO DE PRUEBAS: se ejecuta el algoritmo contra las moleculas de
    #    referencia ANTES de aceptarlo en el catalogo.
    #
    #    Hasta ahora la subida era un acto de fe: nadie comprobaba que el
    #    script llegara siquiera a ejecutarse. Un algoritmo roto entraba igual
    #    que uno correcto, y el fallo aparecia horas despues dentro de un
    #    cribado, como una molecula fallida entre mil. El tipo que declara el
    #    formulario es lo que permite saber COMO invocarlo --una molecula,
    #    dos, o ligando mas receptor-- y la ejecucion comprueba que el script
    #    cumple lo que esa eleccion promete. Ya no hace falta que el propio
    #    script repita el tipo en un comentario: bastaba con que autor y
    #    formulario declararan cosas distintas para que la subida se
    #    rechazara con un mensaje que no decia nada sobre si el algoritmo
    #    funcionaba de verdad, que es lo unico que aqui importa.
    #
    #    Se escribe a un temporal, no a algoritmos/, para que un script que no
    #    pase la prueba no deje rastro en el catalogo.
    with tempfile.TemporaryDirectory(prefix="subida_") as tmp:
        ruta_temporal = os.path.join(tmp, nombre_fichero)
        with open(ruta_temporal, "wb") as f:
            f.write(contenido_archivo)

        prueba = probar_algoritmo(ruta_temporal, tipo)

        if not prueba.valido:
            logger.warning(
                "algoritmo_rechazado_por_banco_de_pruebas",
                extra={"nombre": nombre, "tipo": tipo,
                       "motivo": prueba.motivo, "autor_id": autor_id},
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "mensaje": "El algoritmo no ha superado la prueba de validación.",
                    "motivo": prueba.motivo,
                    "detalle": prueba.detalle,
                    "salida": (prueba.log or "")[-1500:],
                    "ayuda": (
                        "El algoritmo se ejecuta sobre dos moléculas de referencia "
                        "antes de aceptarlo. Comprueba que recibe sus ficheros como "
                        "argumentos posicionales, que escribe el resultado en el "
                        "ÚLTIMO argumento, y que termina con código 0."
                    ),
                },
            )

        # 5. Superada la prueba, se mueve al catalogo, con un nombre que no
        #    pise el script de nadie (ver nombre_algoritmo_libre). Se decide
        #    aqui y no antes a proposito: si el algoritmo no pasa la prueba no
        #    llega a este punto, asi que un rechazo no gasta un nombre.
        nombre_fichero = nombre_algoritmo_libre(nombre_fichero, db)
        ruta_guardado = os.path.join("algoritmos", nombre_fichero)
        shutil.move(ruta_temporal, ruta_guardado)

    # 6. Guardamos en la base de datos, con lo que el banco de pruebas ha
    #    OBSERVADO: el formato real de salida y la clave que contiene la
    #    puntuacion. Anotarlas evita que el motor tenga que adivinarlas, que es
    #    el origen de una familia de fallos que se ha repetido cuatro veces.
    nuevo_algoritmo = models.Algoritmo(
        nombre=nombre,
        descripcion=descripcion,
        tipo=tipo,
        ruta_archivo=nombre_fichero,
        es_publico=es_publico,
        autor_id=autor_id,
        formato_salida=prueba.formato_salida,
        clave_score=prueba.clave_score,
        verificado=True,
    )
    db.add(nuevo_algoritmo)
    db.commit()
    db.refresh(nuevo_algoritmo)

    logger.info(
        "algoritmo_subido",
        extra={"algoritmo_id": nuevo_algoritmo.id, "tipo": tipo,
               "autor_id": autor_id, "formato_salida": prueba.formato_salida,
               "clave_score": prueba.clave_score},
    )
    return nuevo_algoritmo

@app.post("/peticiones", response_model=schemas.PeticionRespuesta)
async def crear_peticion(
    algoritmo_id: int = Form(...),
    archivo_mol: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    """
    Recibe una molécula (.mol2), la guarda en 'uploads/' y crea una petición en cola.
    El propietario de la petición es el usuario autenticado, no un usuario_id
    que el cliente pudiera falsificar en el formulario.
    """
    usuario_id = usuario_actual.id
    # 0. Saneamos el nombre de archivo (protección contra path traversal)
    nombre_fichero = nombre_archivo_seguro(archivo_mol.filename)
    if not nombre_fichero:
        raise HTTPException(status_code=400, detail="Nombre de archivo no válido")

    # 1. Validamos que sea un formato que los algoritmos sepan leer.
    #
    # Antes esto exigía .mol2 y nada más, y era un problema de resultados, no
    # solo de comodidad: ChEMBL y PubChem entregan SDF, así que para lanzar una
    # petición había que convertir, y RDKit lee mal el .mol2 de muchos
    # heterociclos aromáticos. En la cafeína, MolFromMol2File devuelve None, el
    # algoritmo cae a sanitize=False y publica LogP -3,42 en vez de -1,03 con
    # "exito": true. Por el .sdf original salen los valores correctos, así que
    # la restricción estaba degradando la química sin que nadie lo viera.
    ext = os.path.splitext(nombre_fichero)[1].lower()
    if ext not in EXTENSIONES_ENTRADA_ALGORITMO:
        raise HTTPException(
            status_code=400,
            detail=(f"El archivo debe ser una molécula en uno de estos formatos: "
                    f"{', '.join(EXTENSIONES_ENTRADA_ALGORITMO)}."),
        )

    # 1b. Validamos el algoritmo ANTES de guardar nada.
    #
    # Hasta ahora `algoritmo_id` se guardaba sin comprobar siquiera que
    # existiera: un id inventado creaba la peticion igual, se encolaba, y el
    # fallo aparecia despues en el worker como una tarea en ERROR, con el
    # fichero del usuario ya escrito en uploads/ para nada. Comprobarlo aqui
    # devuelve un 404 inmediato y no deja basura.
    #
    # Y es donde se aplica la desactivacion: un algoritmo retirado del catalogo
    # por un administrador no puede usarse en peticiones nuevas, aunque quien
    # lo intente conozca su id o tenga el desplegable cargado de antes.
    algoritmo = db.query(models.Algoritmo).filter(models.Algoritmo.id == algoritmo_id).first()
    if algoritmo is None:
        raise HTTPException(status_code=404, detail="El algoritmo indicado no existe.")
    if not algoritmo.activo:
        raise HTTPException(
            status_code=409,
            detail="Este algoritmo ha sido desactivado por un administrador y no puede ejecutarse.",
        )
    # Y privado quiere decir privado. El id llega en el formulario, así que no
    # basta con que el algoritmo no salga en el desplegable: sin esto,
    # cualquier usuario podía ejecutar el algoritmo privado de otro sin más
    # que indicar su id.
    if not algoritmo.es_publico and algoritmo.autor_id != usuario_id and not es_admin(usuario_actual):
        raise HTTPException(
            status_code=403,
            detail="Este algoritmo es privado de otro usuario.",
        )

    # 2. Guardamos la molécula físicamente en la carpeta 'uploads/'
    #    Por trozos y con tope, igual que /moleculas/subir: aunque aquí el
    #    usuario esté autenticado, cargar el fichero entero en memoria sigue
    #    siendo un problema de capacidad, no solo de abuso.
    nombre_fichero = nombre_libre(nombre_fichero, db)
    ruta_guardado = os.path.join("uploads", nombre_fichero)
    bytes_escritos = await guardar_subida(archivo_mol, ruta_guardado, MAX_SUBIDA_BYTES)

    # 3. Creamos el registro en la base de datos con estado PENDIENTE
    nueva_peticion = models.Peticion(
        estado="PENDIENTE",
        ruta_mol_original=nombre_fichero,
        usuario_id=usuario_id,
        algoritmo_id=algoritmo_id
    )
    db.add(nueva_peticion)
    db.commit()
    db.refresh(nueva_peticion)

    # La molécula de entrada es privada del autor de la petición, no de la
    # biblioteca compartida: la subió para un análisis concreto. Privada
    # (visibilidad=resultado) no es lo mismo que "es un resultado": el
    # CONTENIDO sigue siendo una molécula corriente, solo .mol2 (línea 456),
    # así que tipo=molecula, nunca tipo=resultado -- ese es para lo que
    # calcula el propio algoritmo, no para lo que sube el usuario.
    registrar_archivo(
        db, nombre_fichero,
        propietario_id=usuario_id,
        visibilidad=models.VisibilidadArchivo.resultado,
        tipo=models.TipoArchivo.molecula,
        tamano_bytes=bytes_escritos,
        peticion_id=nueva_peticion.id,
    )
    db.commit()

    # 4. Encolar la tarea en Celery (se procesará en cuanto el worker esté libre)
    tarea = ejecutar_peticion_async.delay(nueva_peticion.id)
    nueva_peticion.celery_task_id = tarea.id
    db.commit()
    db.refresh(nueva_peticion)

    logger.info(
        "peticion_encolada",
        extra={"peticion_id": nueva_peticion.id, "usuario_id": usuario_id, "algoritmo_id": algoritmo_id},
    )
    return nueva_peticion

# NOTA: aqui vivia POST /ejecutar/{peticion_id}, eliminado.
#
# Era codigo anterior a la cola de tareas y acumulaba tres problemas: no
# exigia autenticacion --cualquiera podia disparar la ejecucion de la
# peticion de otro usuario--, ejecutaba el algoritmo de forma SINCRONA
# dentro del proceso web, bloqueando a todos los usuarios mientras duraba,
# y duplicaba una funcionalidad que ya cubre POST /peticiones, que encola
# en Celery automaticamente. No lo invocaba ni el frontend ni los tests.

@app.get("/descargar/{peticion_id}")
def descargar_resultado(
    peticion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    """
    Permite descargar el archivo resultante (.mol2) de una petición completada.
    Solo el propietario (según el token) o un admin pueden descargar el resultado.
    """
    peticion = db.query(models.Peticion).filter(models.Peticion.id == peticion_id).first()
    if not peticion:
        raise HTTPException(status_code=404, detail="Petición no encontrada")
    if peticion.usuario_id != usuario_actual.id and not es_admin(usuario_actual):
        raise HTTPException(status_code=403, detail="No tienes permiso para descargar este resultado")
    if peticion.estado != "COMPLETADO" or not peticion.ruta_mol_resultado:
        raise HTTPException(status_code=400, detail="El resultado aún no está listo o la petición falló")

    # 3. Construimos la ruta donde debería estar el archivo
    ruta_archivo = os.path.join("uploads", peticion.ruta_mol_resultado)
    
    # 4. Verificamos que el archivo físico exista de verdad
    if not os.path.exists(ruta_archivo):
        raise HTTPException(status_code=404, detail="El archivo físico no se encuentra en el servidor")

    # 5. Devolvemos el archivo para que el navegador lo descargue.
    #
    # Sin media_type a mano: FileResponse lo deduce de la extension del fichero.
    # Antes iba fijo a 'chemical/x-mol2', que era mentira en cuanto el algoritmo
    # devolvia un JSON --un filtro, una comparacion, un RMSD--, y es justo lo
    # que corregir_extension (app/tasks.py) se ocupa de que no pase: ahi se
    # renombra el resultado para que un JSON no se haga pasar por una molecula,
    # y declararlo como mol2 al servirlo deshacia ese trabajo.
    return FileResponse(
        path=ruta_archivo,
        filename=peticion.ruta_mol_resultado,
    )


@app.post("/login", response_model=schemas.TokenRespuesta)
def login(datos: schemas.UsuarioLogin, db: Session = Depends(get_db)):
    # 0. Si esta cuenta ha acumulado demasiados fallos recientes, cortar
    #    antes de tocar la base de datos o comparar la contraseña.
    verificar_no_bloqueado(datos.email)

    usuario = db.query(models.Usuario).filter(models.Usuario.email == datos.email).first()

    if not usuario or not verify_password(datos.password_hash, usuario.password_hash):
        registrar_intento_fallido(datos.email)
        logger.warning("login_fallido", extra={"email": datos.email})
        raise HTTPException(status_code=400, detail="Credenciales incorrectas")

    if not usuario.email_verificado:
        raise HTTPException(status_code=403, detail="Debes confirmar tu correo electrónico antes de iniciar sesión. Revisa tu bandeja de entrada.")

    # Cuenta desactivada por un administrador. Se comprueba DESPUES de validar
    # la contraseña: responder "cuenta desactivada" a quien no ha acertado la
    # clave confirmaría a un tercero que ese correo existe en la plataforma.
    if not usuario.activo:
        raise HTTPException(status_code=403, detail="Esta cuenta está desactivada. Contacta con un administrador.")

    limpiar_intentos(datos.email)
    logger.info("login_exito", extra={"email": datos.email, "usuario_id": usuario.id})
    token = crear_access_token(usuario)
    return {
        "access_token": token,
        "token_type": "bearer",
        "usuario": {
            "id": usuario.id,
            "nombre": usuario.nombre,
            "email": usuario.email,
            "rol": usuario.rol.value if usuario.rol else "biologo",
        },
    }

# --- HISTORIAL DE PETICIONES (solo del usuario) ---
@app.get("/peticiones/usuario/{u_id}")
def listar_peticiones_usuario(
    u_id: int,
    response: Response,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
    pagina: Paginacion = Depends(),
):
    if u_id != usuario_actual.id and not es_admin(usuario_actual):
        raise HTTPException(status_code=403, detail="No tienes permiso para ver este historial")
    # joinedload: la respuesta incluye p.algoritmo.nombre, y sin él cada fila
    # dispara su propio SELECT sobre algoritmos al leer ese atributo. No se
    # nota mientras todas las peticiones usan el mismo algoritmo --el identity
    # map de SQLAlchemy lo reutiliza tras la primera carga--, pero en cuanto
    # son distintos el coste pasa a ser una consulta por fila: medido, 43
    # consultas para 40 peticiones frente a las 3 de ahora.
    consulta = db.query(models.Peticion).filter(models.Peticion.usuario_id == u_id)
    response.headers["X-Total-Count"] = str(consulta.count())
    peticiones = consulta.options(joinedload(models.Peticion.algoritmo)) \
        .order_by(models.Peticion.fecha_creacion.desc()) \
        .offset(pagina.offset).limit(pagina.limit).all()
    return [
        {
            "id":                p.id,
            "estado":            p.estado,
            "ruta_mol_original": p.ruta_mol_original,
            "ruta_mol_resultado": p.ruta_mol_resultado,
            "algoritmo_nombre":  p.algoritmo.nombre if p.algoritmo else "—",
            "fecha_creacion":    p.fecha_creacion.isoformat() if p.fecha_creacion else None,
        }
        for p in peticiones
    ]


# --- HISTORIAL DE EJECUCIONES DE WORKFLOW (solo del usuario) ---
@app.get("/ejecuciones/usuario/{u_id}")
def listar_ejecuciones_usuario(
    u_id: int,
    response: Response,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
    pagina: Paginacion = Depends(),
):
    if u_id != usuario_actual.id and not es_admin(usuario_actual):
        raise HTTPException(status_code=403, detail="No tienes permiso para ver este historial")
    # Mismo N+1 que en el historial de peticiones, por e.workflow.nombre. Aquí
    # además es más probable que se manifieste: un usuario acumula ejecuciones
    # de workflows distintos con facilidad, mientras que el catálogo de
    # algoritmos es pequeño y se repite.
    consulta = db.query(models.WorkflowExecution).filter(models.WorkflowExecution.usuario_id == u_id)
    response.headers["X-Total-Count"] = str(consulta.count())
    ejecuciones = consulta.options(joinedload(models.WorkflowExecution.workflow)) \
        .order_by(models.WorkflowExecution.fecha_ejecucion.desc()) \
        .offset(pagina.offset).limit(pagina.limit).all()

    resultado = []
    for e in ejecuciones:
        # Extraer archivos descargables del resultados_json
        archivos = []
        if e.resultados_json and isinstance(e.resultados_json, dict):
            rj = e.resultados_json
            # Un cribado ofrece TODOS sus ficheros, no solo el ranking: uno de
            # Lipinski o de preparacion no tiene ranking, y su resultado --las
            # moleculas y sus propiedades-- no aparecia en ninguna parte fuera
            # del panel del editor, que se pierde al cambiar de pagina.
            if rj.get("modo") == "batch":
                archivos += [os.path.basename(rj[clave])
                             for clave in FICHEROS_DEL_CRIBADO if rj.get(clave)]
            else:
                nodos = rj.get("resultados", rj)
                for nodo in nodos.values() if isinstance(nodos, dict) else []:
                    if not isinstance(nodo, dict):
                        continue
                    if nodo.get("tipo") == "descargar" and nodo.get("archivo"):
                        archivos.append(os.path.basename(nodo["archivo"]))
                    elif nodo.get("archivo_salida"):
                        archivos.append(os.path.basename(nodo["archivo_salida"]))

        resultado.append({
            "id":                  e.id,
            "workflow_id":         e.workflow_id,
            "workflow_nombre":     e.workflow.nombre if e.workflow else "—",
            "estado":              e.estado,
            "fecha_ejecucion":     e.fecha_ejecucion.isoformat() if e.fecha_ejecucion else None,
            "duracion_segundos":   e.duracion_segundos,
            "archivos":            archivos,
        })
    return resultado

@app.get("/algoritmos")
def listar_algoritmos(
    response: Response,
    db: Session = Depends(get_db),
    pagina: Paginacion = Depends(),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
    incluir_inactivos: bool = False,
):
    """
    Cataloga los algoritmos disponibles. Exige estar autenticado: la respuesta
    incluye el `ruta_archivo` de cada script del servidor, y publicarla sin
    credenciales entrega gratis un mapa de los ficheros ejecutables que hay en
    `algoritmos/`. No es un secreto crítico, pero tampoco hay ninguna razón
    para regalarlo: el catálogo solo lo consume la propia interfaz, que ya va
    autenticada.
    """
    consulta = db.query(models.Algoritmo)
    # Un algoritmo desactivado sigue en la base --las peticiones que lo usaron
    # apuntan a el-- pero desaparece del catalogo: no se ofrece en los
    # desplegables ni se puede elegir para una peticion nueva. El admin sí
    # puede pedirlo con incluir_inactivos, que es como lo lista el panel de
    # administracion para poder reactivarlo.
    if not (incluir_inactivos and es_admin(usuario_actual)):
        consulta = consulta.filter(models.Algoritmo.activo == True)  # noqa: E712

    # Y se respeta `es_publico`, que hasta ahora se guardaba y no se leía en
    # ninguna parte: el catálogo entero se le servía a cualquier usuario
    # autenticado, así que marcar un algoritmo como privado --o pulsar "Hacer
    # privado" en el panel de administración-- no tenía ningún efecto. Cada
    # uno ve los públicos más los suyos; el admin, todo, porque su panel
    # necesita poder administrar también los privados.
    if not es_admin(usuario_actual):
        consulta = consulta.filter(or_(
            models.Algoritmo.es_publico == True,  # noqa: E712
            models.Algoritmo.autor_id == usuario_actual.id,
        ))
    response.headers["X-Total-Count"] = str(consulta.count())
    return consulta.order_by(models.Algoritmo.id).offset(pagina.offset).limit(pagina.limit).all()


@app.post("/moleculas/subir")
async def subir_molecula(
    archivo: UploadFile = File(...),
    tipo: str = Form("molecula"),   # "molecula" | "base_de_datos"
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    """
    Sube un archivo de molécula o base de datos a uploads/.

    Exige estar autenticado. Antes era anónimo --"un depósito libre de
    archivos"--, lo que en la práctica significaba que cualquiera en la red,
    sin cuenta, podía escribir ficheros en el servidor sin límite de tamaño ni
    de cantidad: bastaba para llenar el disco y dejar la plataforma inservible.
    Sigue siendo un depósito compartido entre usuarios autenticados, que es lo
    que hace posible reutilizar una base de datos subida por un compañero; lo
    que deja de ser es público para cualquiera.
    """
    nombre_fichero = nombre_archivo_seguro(archivo.filename)
    if not nombre_fichero:
        raise HTTPException(status_code=400, detail="Nombre de archivo no válido")

    if tipo not in ("molecula", "base_de_datos"):
        raise HTTPException(status_code=400, detail="El tipo debe ser 'molecula' o 'base_de_datos'")

    extensiones_validas = {".mol2", ".sdf", ".mol", ".pdb", ".pdbqt", ".smi", ".xyz"}
    ext = os.path.splitext(nombre_fichero)[1].lower()
    if ext not in extensiones_validas:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado. Usa: {', '.join(sorted(extensiones_validas))}"
        )
    if tipo == "base_de_datos" and ext != ".sdf":
        raise HTTPException(status_code=400, detail="Las bases de datos deben estar en formato SDF (.sdf)")

    os.makedirs("uploads", exist_ok=True)
    # Si el nombre ya está ocupado se renombra en vez de pisar el fichero
    # ajeno (ver nombre_libre).
    nombre_fichero = nombre_libre(nombre_fichero, db)
    ruta = os.path.join("uploads", nombre_fichero)
    escritos = await guardar_subida(archivo, ruta, MAX_SUBIDA_BYTES)

    # Contar moléculas si es SDF. Se hace releyendo el fichero por trozos y no
    # sobre el contenido en memoria, porque ya no existe tal contenido: el
    # volcado es en streaming precisamente para no tenerlo entero en RAM.
    num_moleculas = contar_moleculas_sdf(ruta) if ext == ".sdf" else None

    # El indice de posiciones de sus registros, para que el cribado salte
    # a las moleculas de cada bloque en vez de recorrer el fichero entero
    # (ver app/indice_sdf.py). Si fallara no se pierde nada: se construye
    # la primera vez que se use la biblioteca.
    if ext == ".sdf":
        try:
            indice_sdf.obtener(ruta)
        except OSError as e:
            logger.warning("indice_sdf_no_construido",
                           extra={"nombre": nombre_fichero, "error": str(e)})

    # El tipo que se GUARDA se verifica contra el contenido, no se copia del
    # formulario: es la misma idea que el banco de pruebas con los
    # algoritmos --declarar no basta, hay que comprobarlo--, y aquí
    # comprobarlo es gratis porque num_moleculas ya se acaba de calcular.
    # Un .sdf con un único registro es una molécula aunque el formulario diga
    # "base_de_datos"; uno con varios lo es aunque diga "molecula".
    if ext == ".sdf":
        tipo_real = (models.TipoArchivo.base_de_datos if (num_moleculas or 0) > 1
                     else models.TipoArchivo.molecula)
    else:
        tipo_real = models.TipoArchivo.molecula

    registrar_archivo(
        db, nombre_fichero,
        propietario_id=usuario_actual.id,
        visibilidad=models.VisibilidadArchivo.biblioteca,
        tipo=tipo_real,
        tamano_bytes=escritos,
        num_moleculas=num_moleculas,
    )
    db.commit()

    logger.info(
        "molecula_subida",
        extra={
            "usuario_id": usuario_actual.id,
            "nombre": nombre_fichero,
            "bytes": escritos,
            "tipo": tipo_real.value,
        },
    )
    return {
        "nombre":        nombre_fichero,
        "tipo":          tipo_real.value,
        "tamano_kb":     round(escritos / 1024, 1),
        "num_moleculas": num_moleculas,
    }


@app.delete("/moleculas/{nombre_archivo}")
def borrar_molecula(
    nombre_archivo: str,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    """
    Borra un archivo de molécula de uploads/.

    Solo su propietario o un admin. Antes bastaba con estar autenticado para
    borrar cualquier cosa que no estuviera ligada a una petición, lo que
    incluía TODOS los resultados de workflow de los demás usuarios.
    """
    nombre_archivo = exigir_nombre_archivo_seguro(nombre_archivo)
    exigir_acceso_a_archivo(nombre_archivo, db, usuario_actual, para_borrar=True)
    ruta = os.path.join("uploads", nombre_archivo)
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    os.remove(ruta)
    indice_sdf.borrar(ruta)
    registro = _archivo_registrado(nombre_archivo, db)
    if registro is not None:
        db.delete(registro)
    db.commit()
    return {"mensaje": f"{nombre_archivo} eliminado"}


@app.get("/moleculas")
def listar_moleculas(
    response: Response,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
    usuario_id: int = None,
    pagina: Paginacion = Depends(),
):
    """
    Lista las moléculas visibles para el usuario, desde el registro `archivos`.

    Devuelve la biblioteca compartida --que ve cualquier usuario autenticado--
    más los ficheros privados del propio usuario. Los resultados de otros
    quedan fuera.

    Antes esto recorría el directorio entero con un `stat()` por fichero
    (3.600 en el despliegue de desarrollo), cargaba todas las peticiones del
    usuario, luego las de TODOS los usuarios, y paginaba al final, sobre la
    lista ya construida. Y cada nodo del canvas dispara su propia llamada, así
    que un flujo con cinco selectores hacía cinco escaneos completos. Ahora es
    una consulta indexada con LIMIT/OFFSET, y su coste depende del tamaño de
    la página, no del de la carpeta.

    Parámetro opcional:
      usuario_id — para que un admin consulte las moléculas de otro usuario;
      cualquier otro usuario que lo use recibe 403.
    """
    if usuario_id is not None and usuario_id != usuario_actual.id and not es_admin(usuario_actual):
        raise HTTPException(status_code=403, detail="No tienes permiso para ver las moléculas de otro usuario")
    usuario_objetivo = usuario_id if usuario_id is not None else usuario_actual.id

    extensiones_molecula = (".mol2", ".sdf", ".pdbqt", ".mol", ".pdb")

    visibles = or_(
        models.Archivo.visibilidad == models.VisibilidadArchivo.biblioteca,
        models.Archivo.propietario_id == usuario_objetivo,
    )
    consulta = db.query(models.Archivo).filter(
        visibles,
        or_(*[models.Archivo.nombre.ilike(f"%{ext}") for ext in extensiones_molecula]),
    )

    response.headers["X-Total-Count"] = str(consulta.count())
    archivos = consulta.order_by(models.Archivo.nombre)         .offset(pagina.offset).limit(pagina.limit).all()

    return [
        {
            "nombre": a.nombre,
            # "molecula" | "base_de_datos" | "resultado", verificado contra
            # el contenido al subir (ver /moleculas/subir), no deducido de la
            # visibilidad: antes el icono salía de si el fichero era privado
            # o no, así que la molécula de entrada de una petición --privada,
            # pero una molécula corriente-- se mostraba como "base de datos".
            # El *: nulo solo en filas anteriores a esta columna que
            # scripts/migrate.py aún no haya rellenado (backfill_tipo_archivo).
            "tipo": (a.tipo.value if a.tipo else
                     ("resultado" if a.visibilidad == models.VisibilidadArchivo.resultado
                      else "molecula")),
            "num_moleculas": a.num_moleculas,
            "tamano_kb": round((a.tamano_bytes or 0) / 1024, 1),
        }
        for a in archivos
    ]


@app.get("/peticiones/{peticion_id}/estado")
def estado_peticion(
    peticion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    """
    Devuelve el estado actual de una petición y su posición en la cola de espera.
    Solo el propietario de la petición (según el token) o un admin pueden consultarla.
    """
    peticion = db.query(models.Peticion).filter(models.Peticion.id == peticion_id).first()
    if not peticion:
        raise HTTPException(status_code=404, detail="Petición no encontrada")
    if peticion.usuario_id != usuario_actual.id and not es_admin(usuario_actual):
        raise HTTPException(status_code=403, detail="No tienes permiso para ver esta petición")

    posicion_en_cola = 0
    if peticion.estado == "PENDIENTE":
        posicion_en_cola = db.query(models.Peticion).filter(
            models.Peticion.id < peticion_id,
            models.Peticion.estado.in_(["PENDIENTE", "PROCESANDO"])
        ).count() + 1  # +1 porque la propia petición también cuenta

    return {
        "id":              peticion.id,
        "estado":          peticion.estado,
        "posicion_en_cola": posicion_en_cola,
        "celery_task_id":  peticion.celery_task_id,
        "ruta_resultado":  peticion.ruta_mol_resultado,
    }


@app.delete("/peticiones/{peticion_id}")
def borrar_peticion(
    peticion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    """
    Borra una petición de la base de datos por su ID.
    Solo el propietario o un admin pueden borrarla (antes cualquiera con el
    ID podía borrar la petición de otro usuario).
    """
    peticion = db.query(models.Peticion).filter(models.Peticion.id == peticion_id).first()

    if not peticion:
        raise HTTPException(status_code=404, detail="Petición no encontrada")
    if peticion.usuario_id != usuario_actual.id and not es_admin(usuario_actual):
        raise HTTPException(status_code=403, detail="No tienes permiso para borrar esta petición")

    borrados = borrar_archivos_registrados(
        db, models.Archivo.peticion_id == peticion_id)
    db.delete(peticion)
    db.commit()

    return {
        "mensaje": f"Petición {peticion_id} eliminada correctamente",
        "archivos_borrados": borrados,
    }


# --- ENDPOINTS DE WORKFLOWS (KNIME) ---

@app.post("/workflows", response_model=schemas.WorkflowRespuesta)
def crear_workflow(
    nombre: str = Form(...),
    descripcion: str = Form(""),
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    """
    Crea un nuevo workflow vacío. El grafo se rellena después con PUT.
    El propietario es el usuario autenticado, no un usuario_id del formulario.
    """
    nuevo_workflow = models.Workflow(
        nombre=nombre,
        descripcion=descripcion,
        grafo_json={"nodes": [], "edges": []},
        usuario_id=usuario_actual.id,
        estado="borrador"
    )
    db.add(nuevo_workflow)
    db.commit()
    db.refresh(nuevo_workflow)
    return nuevo_workflow


@app.get("/workflows/usuario/{usuario_id}")
def listar_workflows_usuario(
    usuario_id: int,
    response: Response,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
    pagina: Paginacion = Depends(),
):
    """
    Lista todos los workflows de un usuario. Solo el propio usuario o un
    admin pueden listarlos.
    """
    if usuario_id != usuario_actual.id and not es_admin(usuario_actual):
        raise HTTPException(status_code=403, detail="No tienes permiso para ver estos workflows")
    consulta = db.query(models.Workflow).filter(models.Workflow.usuario_id == usuario_id)
    response.headers["X-Total-Count"] = str(consulta.count())
    return consulta.order_by(models.Workflow.id.desc()).offset(pagina.offset).limit(pagina.limit).all()


def _obtener_workflow_propio(workflow_id: int, db: Session, usuario_actual: models.Usuario) -> models.Workflow:
    """Carga un workflow y comprueba que el usuario autenticado es su propietario o admin."""
    workflow = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow no encontrado")
    if workflow.usuario_id != usuario_actual.id and not es_admin(usuario_actual):
        raise HTTPException(status_code=403, detail="No tienes permiso sobre este workflow")
    return workflow


@app.get("/workflows/{workflow_id}", response_model=schemas.WorkflowRespuesta)
def obtener_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    """
    Obtiene un workflow por su ID. Solo el propietario o un admin.
    """
    return _obtener_workflow_propio(workflow_id, db, usuario_actual)


@app.put("/workflows/{workflow_id}", response_model=schemas.WorkflowRespuesta)
def actualizar_workflow(
    workflow_id: int,
    workflow_update: schemas.WorkflowCreate,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    """
    Actualiza la estructura (grafo) de un workflow existente.
    Solo el propietario o un admin.
    """
    workflow = _obtener_workflow_propio(workflow_id, db, usuario_actual)

    workflow.nombre = workflow_update.nombre
    workflow.descripcion = workflow_update.descripcion
    workflow.grafo_json = workflow_update.grafo_json
    workflow.fecha_actualizacion = datetime.utcnow()
    
    db.commit()
    db.refresh(workflow)
    return workflow


@app.delete("/workflows/{workflow_id}")
def borrar_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    """
    Borra un workflow y todas sus ejecuciones. Solo el propietario o un admin.
    """
    workflow = _obtener_workflow_propio(workflow_id, db, usuario_actual)

    # Borrar ejecuciones asociadas y los ficheros que produjeron
    ids_ejecuciones = [
        e.id for e in db.query(models.WorkflowExecution.id)
        .filter(models.WorkflowExecution.workflow_id == workflow_id).all()
    ]
    borrados = 0
    if ids_ejecuciones:
        borrados = borrar_archivos_registrados(
            db, models.Archivo.ejecucion_id.in_(ids_ejecuciones))
        # El flush NO es opcional. borrar_archivos_registrados usa db.delete(),
        # que solo MARCA las filas y las envía al vaciar la sesión; la línea de
        # abajo usa Query.delete(), que emite su DELETE al instante. Sin este
        # flush el borrado de workflow_executions se ejecutaba ANTES que el de
        # archivos, y como archivos.ejecucion_id las referencia, PostgreSQL lo
        # rechazaba: cualquier workflow que se hubiera ejecutado alguna vez
        # devolvía un 500 al intentar borrarlo (ForeignKeyViolation en
        # archivos_ejecucion_id_fkey). Los que nunca se ejecutaron sí se
        # borraban, que es por lo que pasaba desapercibido.
        db.flush()
    db.query(models.WorkflowExecution).filter(models.WorkflowExecution.workflow_id == workflow_id).delete()
    db.delete(workflow)
    db.commit()

    return {
        "mensaje": f"Workflow {workflow_id} eliminado correctamente",
        "archivos_borrados": borrados,
    }


@app.post("/workflows/{workflow_id}/ejecutar")
def ejecutar_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    """
    Encola la ejecución del workflow vía Celery.
    Si el workflow contiene un nodo selectDB con base de datos, se ejecuta en modo batch
    (una molécula a la vez sobre todo el SDF). Si no, ejecución estándar.
    Solo el propietario del workflow o un admin pueden ejecutarlo.
    """
    workflow = _obtener_workflow_propio(workflow_id, db, usuario_actual)
    usuario_id = usuario_actual.id

    # Ser dueño del workflow no basta: el grafo lo manda el cliente, así que
    # puede nombrar cualquier fichero de uploads/, incluido el resultado
    # privado de otro usuario. Se comprueba antes de encolar para que el
    # rechazo sea un 403 inmediato y legible, y no una ejecución que falla
    # diez minutos después. El worker lo vuelve a comprobar (app/tasks.py):
    # entre el encolado y la ejecución pueden cambiar los permisos.
    try:
        permisos.comprobar_acceso_al_grafo(
            workflow.grafo_json, db, usuario_id, usuario_es_admin=es_admin(usuario_actual),
        )
    except permisos.AccesoDenegado as e:
        raise HTTPException(
            status_code=403,
            detail=f"El flujo usa '{e.nombre_archivo}', que no es tuyo: {e.mensaje}",
        )

    # Auto-detectar modo batch: hay nodo selectDB con base de datos seleccionada
    grafo    = workflow.grafo_json or {}
    es_batch = any(
        nodo.get("type") == "selectDB" and nodo.get("data", {}).get("nombre_archivo")
        for nodo in grafo.get("nodes", [])
    )

    ejecucion = models.WorkflowExecution(
        workflow_id=workflow_id,
        usuario_id=usuario_id,
        estado="pendiente",
    )
    db.add(ejecucion)
    db.commit()
    db.refresh(ejecucion)

    if es_batch:
        tarea = ejecutar_workflow_batch_async.delay(workflow_id, usuario_id, ejecucion.id)
    else:
        tarea = ejecutar_workflow_async.delay(workflow_id, usuario_id, ejecucion.id)

    ejecucion.celery_task_id = tarea.id
    db.commit()

    return {
        "ejecucion_id":   ejecucion.id,
        "celery_task_id": tarea.id,
        "estado":         "pendiente",
        "modo":           "batch" if es_batch else "normal",
        "mensaje":        (
            "Modo batch: se procesará cada molécula de la base de datos. Recibirás un correo al terminar."
            if es_batch else
            "Workflow encolado. Recibirás un correo al terminar."
        ),
    }


@app.post("/workflows/ejecuciones/{ejecucion_id}/cancelar")
def cancelar_ejecucion(
    ejecucion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    query = db.query(models.WorkflowExecution).filter(models.WorkflowExecution.id == ejecucion_id)
    if not es_admin(usuario_actual):
        query = query.filter(models.WorkflowExecution.usuario_id == usuario_actual.id)
    ejecucion = query.first()
    if not ejecucion:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada")

    if ejecucion.estado not in ("pendiente", "procesando"):
        raise HTTPException(status_code=400, detail=f"No se puede cancelar una ejecución en estado '{ejecucion.estado}'")

    # La bandera va PRIMERO: es lo que para una ejecución que ya está en
    # marcha. La consultan tanto el workflow normal como cada subtarea de un
    # cribado en lote --revocar el coordinador de un lote no detendría ninguna,
    # porque suele haber terminado ya--, y no solo entre moléculas, sino
    # también mientras se espera al algoritmo o al job del clúster (ver
    # vigilar_cancelacion en app/ejecutor.py), que es donde se va el tiempo.
    from app.tasks import marcar_cancelacion
    marcar_cancelacion(ejecucion_id)

    # Revocar descarta la tarea si todavía está en la cola. Ya NO se usa
    # terminate=True: matar el proceso a mitad dejaba el job corriendo en el
    # bullx, porque nadie llegaba a hacer su scancel. La tarea en marcha se
    # retira sola, cancelando su job, en el siguiente sondeo de la bandera.
    if ejecucion.celery_task_id:
        from app.celery_app import celery_app as _celery
        _celery.control.revoke(ejecucion.celery_task_id)

    ejecucion.estado = "cancelado"
    db.commit()
    return {"mensaje": "Ejecución cancelada correctamente"}


@app.get("/uploads/{nombre_archivo}")
def servir_archivo_upload(
    nombre_archivo: str,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    """
    Sirve un archivo de uploads/ para descarga directa.

    Los ficheros de la biblioteca los descarga cualquier usuario autenticado
    --es lo que permite reutilizar una base de datos subida por otro--, pero
    los resultados de una petición o de una ejecución son privados de su
    propietario. Antes los resultados de workflow no constaban en ninguna
    parte y quedaban accesibles para todos.
    """
    nombre_archivo = exigir_nombre_archivo_seguro(nombre_archivo)
    exigir_acceso_a_archivo(nombre_archivo, db, usuario_actual)
    ruta = os.path.join("uploads", nombre_archivo)
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(path=ruta, filename=nombre_archivo)


@app.get("/workflows/{workflow_id}/ejecuciones")
def obtener_ejecuciones_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    """
    Obtiene el historial de ejecuciones de un workflow. Solo el propietario
    del workflow o un admin.
    """
    _obtener_workflow_propio(workflow_id, db, usuario_actual)
    ejecuciones = db.query(models.WorkflowExecution).filter(
        models.WorkflowExecution.workflow_id == workflow_id
    ).all()
    return ejecuciones


@app.get("/workflows/ejecuciones/{ejecucion_id}", response_model=schemas.WorkflowExecutionRespuesta)
def obtener_ejecucion(
    ejecucion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    """
    Obtiene los detalles de una ejecución específica. Solo el propietario
    de la ejecución o un admin.
    """
    ejecucion = db.query(models.WorkflowExecution).filter(
        models.WorkflowExecution.id == ejecucion_id
    ).first()

    if not ejecucion:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada")
    if ejecucion.usuario_id != usuario_actual.id and not es_admin(usuario_actual):
        raise HTTPException(status_code=403, detail="No tienes permiso para ver esta ejecución")

    return ejecucion


# --- MONITORIZACIÓN DEL SISTEMA (solo admin) ---

def _estado_cola_celery() -> dict:
    """
    Consulta en vivo los workers de Celery conectados a Redis (protocolo de
    inspección de Celery, timeout corto para no bloquear el endpoint si
    Redis no responde). Se limita a lo mínimo necesario para un panel de
    monitorización: cuántos workers hay y cuántas tareas están procesando
    ahora mismo cada uno; el histórico de peticiones sale de la base de
    datos, no de Celery.
    """
    try:
        inspeccion = celery_app.control.inspect(timeout=2)
        activos = inspeccion.ping() or {}
        tareas_activas = inspeccion.active() or {}
        return {
            "disponible": True,
            "workers_conectados": len(activos),
            "tareas_en_ejecucion": sum(len(t) for t in tareas_activas.values()),
            "worker_concurrency_configurado": WORKER_CONCURRENCY,
        }
    except Exception as e:
        return {
            "disponible": False,
            "error": str(e),
            "workers_conectados": 0,
            "tareas_en_ejecucion": 0,
            "worker_concurrency_configurado": WORKER_CONCURRENCY,
        }


@app.get("/sistema/estado")
def estado_sistema(
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(requiere_rol("admin")),
):
    """
    Panel de estado agregado de la plataforma: cola de tareas (Celery en
    vivo), y recuento de peticiones, workflows y usuarios (base de datos).
    Solo accesible para usuarios con rol admin.
    """
    total_peticiones = db.query(models.Peticion).count()
    peticiones_pendientes = db.query(models.Peticion).filter(models.Peticion.estado == "PENDIENTE").count()
    peticiones_procesando = db.query(models.Peticion).filter(models.Peticion.estado == "PROCESANDO").count()
    peticiones_completadas = db.query(models.Peticion).filter(models.Peticion.estado == "COMPLETADO").count()
    peticiones_error = db.query(models.Peticion).filter(models.Peticion.estado == "ERROR").count()

    total_workflows = db.query(models.Workflow).count()
    total_ejecuciones = db.query(models.WorkflowExecution).count()
    ejecuciones_pendientes = db.query(models.WorkflowExecution).filter(
        models.WorkflowExecution.estado.in_(["pendiente", "procesando"])
    ).count()
    ejecuciones_completadas = db.query(models.WorkflowExecution).filter(
        models.WorkflowExecution.estado == "completado"
    ).count()
    ejecuciones_error = db.query(models.WorkflowExecution).filter(
        models.WorkflowExecution.estado == "error"
    ).count()

    total_usuarios = db.query(models.Usuario).count()
    usuarios_verificados = db.query(models.Usuario).filter(models.Usuario.email_verificado == True).count()  # noqa: E712

    return {
        "servidor": {
            "hora_utc": datetime.now(timezone.utc).isoformat(),
            "modo_ejecucion": EXECUTION_MODE,
        },
        "cola": _estado_cola_celery(),
        "peticiones": {
            "total": total_peticiones,
            "pendientes": peticiones_pendientes,
            "procesando": peticiones_procesando,
            "completadas": peticiones_completadas,
            "error": peticiones_error,
        },
        "workflows": {
            "total": total_workflows,
            "ejecuciones_total": total_ejecuciones,
            "ejecuciones_activas": ejecuciones_pendientes,
            "ejecuciones_completadas": ejecuciones_completadas,
            "ejecuciones_error": ejecuciones_error,
        },
        "usuarios": {
            "total": total_usuarios,
            "verificados": usuarios_verificados,
        },
    }


# ===========================================================================
# ADMINISTRACION DE LA PLATAFORMA
# ===========================================================================
#
# Todo lo cientifico de esta plataforma esta abierto a cualquier usuario
# autenticado --subir moleculas, subir algoritmos al catalogo, lanzar
# peticiones--, y eso es deliberado: el filtro no es el rol, es el banco de
# pruebas. Lo unico reservado al administrador es la administracion de la
# propia plataforma, que es lo que vive aqui.
#
# La operacion central no es borrar, es DESACTIVAR. Un usuario tiene
# peticiones, workflows y ficheros colgando por clave foranea, y sus moleculas
# pueden estar en la biblioteca compartida, referenciadas por nombre desde los
# grafos que otros usuarios tienen guardados; un algoritmo tiene peticiones que
# apuntan a el. Borrar la fila romperia la integridad de la base y, con ella,
# el trabajo de terceros. Desactivar corta el acceso o retira el algoritmo de
# circulacion, conserva el historial intacto y, sobre todo, se puede deshacer.
#
# El unico borrado real que ofrece el panel es el de ficheros sueltos, via el
# DELETE /moleculas/{nombre} que ya existia: ahi no hay historial que preservar
# mas alla del propio fichero.


@app.get("/admin/usuarios", response_model=list[schemas.UsuarioAdminRespuesta])
def admin_listar_usuarios(
    response: Response,
    db: Session = Depends(get_db),
    pagina: Paginacion = Depends(),
    admin: models.Usuario = Depends(requiere_rol("admin")),
):
    """
    Lista todas las cuentas, con cuanto trabajo tiene cada una detras.

    Los recuentos van en dos consultas agrupadas y se cruzan en memoria, en vez
    de en un subselect por fila: son dos consultas en total, no dos por
    usuario.
    """
    consulta = db.query(models.Usuario)
    response.headers["X-Total-Count"] = str(consulta.count())
    usuarios = (
        consulta.order_by(models.Usuario.id)
        .offset(pagina.offset).limit(pagina.limit).all()
    )

    ids = [u.id for u in usuarios]
    algoritmos_por_usuario = dict(
        db.query(models.Algoritmo.autor_id, func.count(models.Algoritmo.id))
        .filter(models.Algoritmo.autor_id.in_(ids))
        .group_by(models.Algoritmo.autor_id).all()
    ) if ids else {}
    peticiones_por_usuario = dict(
        db.query(models.Peticion.usuario_id, func.count(models.Peticion.id))
        .filter(models.Peticion.usuario_id.in_(ids))
        .group_by(models.Peticion.usuario_id).all()
    ) if ids else {}

    return [
        schemas.UsuarioAdminRespuesta(
            id=u.id,
            nombre=u.nombre,
            email=u.email,
            rol=u.rol.value if u.rol else "biologo",
            email_verificado=u.email_verificado,
            activo=u.activo,
            fecha_registro=u.fecha_registro,
            n_algoritmos=algoritmos_por_usuario.get(u.id, 0),
            n_peticiones=peticiones_por_usuario.get(u.id, 0),
        )
        for u in usuarios
    ]


@app.patch("/admin/usuarios/{usuario_id}", response_model=schemas.UsuarioAdminRespuesta)
def admin_actualizar_usuario(
    usuario_id: int,
    cambios: schemas.UsuarioAdminActualizar,
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(requiere_rol("admin")),
):
    """
    Cambia el rol, la verificacion del correo o la activacion de una cuenta.

    Un administrador no puede degradarse ni desactivarse a si mismo: no es
    paternalismo, es que hacerlo por error deja la sesion en curso sin permisos
    a la siguiente peticion y sin forma de revertirlo desde la interfaz.

    Esas dos comprobaciones bastan ademas para garantizar que la plataforma
    nunca se queda sin ningun administrador operativo, y no hace falta contar
    cuantos quedan: quien ejecuta esta operacion es por fuerza un admin activo
    --lo exige requiere_rol("admin"), y una cuenta desactivada no pasa de
    obtener_usuario_actual (ver app/auth.py)--, y no puede ser el objetivo de
    la degradacion ni de la desactivacion. Sea cual sea el resultado, el que
    la ejecuta sigue siendo administrador.
    """
    usuario = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    es_uno_mismo = usuario.id == admin.id

    if cambios.rol is not None:
        roles_validos = {r.value for r in models.RolUsuario}
        if cambios.rol not in roles_validos:
            raise HTTPException(
                status_code=400,
                detail=f"Rol no válido. Debe ser uno de: {', '.join(sorted(roles_validos))}.",
            )
        degradacion = (usuario.rol == models.RolUsuario.admin
                       and cambios.rol != models.RolUsuario.admin.value)
        if degradacion and es_uno_mismo:
            raise HTTPException(
                status_code=409,
                detail="No puedes retirarte a ti mismo el rol de administrador.",
            )
        usuario.rol = models.RolUsuario(cambios.rol)

    if cambios.email_verificado is not None:
        usuario.email_verificado = cambios.email_verificado

    if cambios.activo is not None:
        if not cambios.activo and es_uno_mismo:
            raise HTTPException(
                status_code=409, detail="No puedes desactivar tu propia cuenta.",
            )
        usuario.activo = cambios.activo

    db.commit()
    db.refresh(usuario)
    logger.info(
        "admin_usuario_actualizado",
        extra={"admin_id": admin.id, "usuario_id": usuario.id,
               "rol": usuario.rol.value, "activo": usuario.activo,
               "email_verificado": usuario.email_verificado},
    )
    return schemas.UsuarioAdminRespuesta(
        id=usuario.id,
        nombre=usuario.nombre,
        email=usuario.email,
        rol=usuario.rol.value if usuario.rol else "biologo",
        email_verificado=usuario.email_verificado,
        activo=usuario.activo,
        fecha_registro=usuario.fecha_registro,
    )


@app.patch("/admin/algoritmos/{algoritmo_id}", response_model=schemas.AlgoritmoRespuesta)
def admin_actualizar_algoritmo(
    algoritmo_id: int,
    cambios: schemas.AlgoritmoAdminActualizar,
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(requiere_rol("admin")),
):
    """
    Retira un algoritmo de circulacion, lo reactiva, o corrige sus metadatos.

    Es la palanca que le faltaba al administrador. El banco de pruebas
    comprueba que un algoritmo FUNCIONA --que se ejecuta, que es del tipo que
    declara y que produce una salida utilizable--, no que sea cientificamente
    correcto: eso no es verificable automaticamente, ni tampoco por revision,
    porque dos algoritmos correctos del mismo tipo dan resultados distintos.
    La correccion se gestiona por tanto de forma reactiva, y esto es lo que
    convierte "nos hemos dado cuenta de que ese algoritmo esta mal" en una
    accion concreta.

    Desactivar surte efecto en los tres caminos por los que se ejecuta un
    algoritmo: desaparece del catalogo (GET /algoritmos), se rechazan las
    peticiones nuevas que lo pidan (POST /peticiones) y los workflows ya
    guardados que lo referencien por nombre fallan al llegar a ese nodo
    (resolver_algoritmo, en app/workflow_executor.py).

    No se toca el .py del disco: reactivarlo tiene que ser posible, y las
    peticiones antiguas conservan la referencia a lo que realmente ejecutaron.
    """
    algoritmo = db.query(models.Algoritmo).filter(models.Algoritmo.id == algoritmo_id).first()
    if algoritmo is None:
        raise HTTPException(status_code=404, detail="Algoritmo no encontrado")

    if cambios.activo is not None:
        algoritmo.activo = cambios.activo
    if cambios.es_publico is not None:
        algoritmo.es_publico = cambios.es_publico
    if cambios.nombre is not None:
        algoritmo.nombre = cambios.nombre
    if cambios.descripcion is not None:
        algoritmo.descripcion = cambios.descripcion

    db.commit()
    db.refresh(algoritmo)
    logger.info(
        "admin_algoritmo_actualizado",
        extra={"admin_id": admin.id, "algoritmo_id": algoritmo.id,
               "activo": algoritmo.activo},
    )
    return algoritmo


@app.get("/admin/moleculas")
def admin_listar_moleculas(
    response: Response,
    db: Session = Depends(get_db),
    pagina: Paginacion = Depends(),
    admin: models.Usuario = Depends(requiere_rol("admin")),
):
    """
    Todos los ficheros de uploads/, con dueño y visibilidad.

    A diferencia de GET /moleculas --que muestra la biblioteca compartida mas
    lo propio de quien pregunta, que es lo correcto para trabajar-- aqui se ven
    tambien los resultados privados de cada usuario, porque el administrador
    necesita poder localizar y liberar espacio de cualquiera.

    Para borrarlos se usa el DELETE /moleculas/{nombre} que ya existe, que
    admite a cualquier admin (ver app/permisos.py).
    """
    consulta = db.query(models.Archivo)
    response.headers["X-Total-Count"] = str(consulta.count())
    archivos = (
        consulta.order_by(models.Archivo.fecha_creacion.desc())
        .offset(pagina.offset).limit(pagina.limit).all()
    )

    ids_propietarios = {a.propietario_id for a in archivos if a.propietario_id}
    duenos = {
        u.id: u.email
        for u in db.query(models.Usuario).filter(models.Usuario.id.in_(ids_propietarios)).all()
    } if ids_propietarios else {}

    return [
        {
            "nombre": a.nombre,
            "visibilidad": a.visibilidad.value if a.visibilidad else None,
            "tipo": a.tipo.value if a.tipo else None,
            "num_moleculas": a.num_moleculas,
            "propietario_id": a.propietario_id,
            # Sin dueño consta el fichero anterior al registro de propiedad
            # (ver scripts/migrate.py): se trata como biblioteca compartida.
            "propietario_email": duenos.get(a.propietario_id),
            "tamano_kb": round((a.tamano_bytes or 0) / 1024, 1),
            "fecha_creacion": a.fecha_creacion,
        }
        for a in archivos
    ]
