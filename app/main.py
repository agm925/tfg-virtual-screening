import os
from fastapi import FastAPI, Depends, HTTPException, File, UploadFile, Form, Query, Response
from sqlalchemy.orm import Session, joinedload
from app.database import engine, SessionLocal
from app import models, schemas
from fastapi.responses import FileResponse, HTMLResponse
import uuid
from fastapi.middleware.cors import CORSMiddleware
from app.tasks import ejecutar_peticion_async, ejecutar_workflow_async, ejecutar_workflow_batch_async
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
from datetime import datetime, timezone
import re

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


def _propietario_de_archivo_uploads(nombre_archivo: str, db: Session):
    """
    Devuelve el usuario_id de la petición dueña de este fichero de
    uploads/, o None si el fichero no está ligado a ninguna petición (es
    del depósito público, o es un resultado de workflow no rastreado por
    esta tabla). Se usa para decidir si GET /uploads/{nombre} o
    DELETE /moleculas/{nombre} deben exigir que el solicitante sea el
    propietario, o si el fichero es de acceso libre para cualquier
    usuario autenticado.
    """
    peticion = db.query(models.Peticion).filter(
        (models.Peticion.ruta_mol_original == nombre_archivo)
        | (models.Peticion.ruta_mol_resultado == nombre_archivo)
    ).first()
    return peticion.usuario_id if peticion else None


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


def contar_moleculas_sdf(ruta: str) -> int:
    """Cuenta los separadores de registro de un SDF leyendo por trozos.

    Se relee el fichero en lugar de contar durante la escritura porque el
    separador ($$$$) puede quedar partido entre dos trozos; aquí se arrastra
    el solapamiento explícitamente.
    """
    separador = b"$$$$"
    total = 0
    sobrante = b""
    with open(ruta, "rb") as f:
        while True:
            trozo = f.read(TAMANO_TROZO_SUBIDA)
            if not trozo:
                break
            datos = sobrante + trozo
            total += datos.count(separador)
            # Conservar los últimos bytes por si el separador cruza la frontera.
            sobrante = datos[-(len(separador) - 1):]
    return total


def exigir_nombre_archivo_seguro(nombre: str) -> str:
    """Como nombre_archivo_seguro, pero rechaza con 400 si el nombre recibido
    no era ya "limpio" -- para endpoints que referencian un archivo existente
    por nombre (GET/DELETE), donde un intento de path traversal debe
    rechazarse explícitamente en vez de reinterpretarse en silencio."""
    seguro = nombre_archivo_seguro(nombre)
    if not seguro or seguro != nombre:
        raise HTTPException(status_code=400, detail="Nombre de archivo no válido")
    return seguro


# --- FUNCIÓN AUXILIAR PARA EXTRAER TIPO DE ALGORITMO ---
async def extraer_tipo_algoritmo(contenido_bytes: bytes) -> str:
    """
    Lee las primeras líneas de un script Python y extrae el tipo de algoritmo.
    Busca la línea: # TIPO_ALGORITMO: alineacion o # TIPO_ALGORITMO: comparacion
    Devuelve el tipo o lanza excepción si no lo encuentra.
    """
    try:
        # Decodificar el contenido del archivo
        contenido = contenido_bytes.decode('utf-8', errors='ignore')
        lineas = contenido.split('\n')[:20]  # Revisar primeras 20 líneas
        
        for linea in lineas:
            # Buscar patrón: # TIPO_ALGORITMO: alineacion | comparacion | preprocesado | docking
            match = re.search(
                r'#\s*TIPO_ALGORITMO\s*:\s*(alineacion|comparacion|preprocesado|docking)',
                linea
            )
            if match:
                tipo = match.group(1)
                return tipo
        
        # Si no encuentra la línea, lanzar excepción
        raise ValueError("No se encontró el metadato # TIPO_ALGORITMO en el script")
    except Exception as e:
        raise ValueError(f"Error al procesar el archivo: {str(e)}")

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
    usuario_actual: models.Usuario = Depends(requiere_rol("admin", "desarrollador")),
):
    """
    Sube un script de Python (.py) y lo registra en la base de datos.
    Valida que el script contenga el metadato # TIPO_ALGORITMO y que coincida con el tipo del formulario.
    Solo usuarios con rol "admin" o "desarrollador" pueden subir algoritmos al catálogo;
    el autor se toma del usuario autenticado, nunca de un campo del formulario.
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

    # 3. Leemos el archivo para extraer el tipo del metadato.
    #    Aquí sí se lee a memoria --hay que inspeccionar el contenido antes de
    #    decidir si se acepta--, pero con un tope muy bajo: un algoritmo es un
    #    script de unos pocos KB, y este endpoint acepta código que después se
    #    ejecutará en el worker o en el nodo del clúster.
    contenido_archivo = await archivo.read(MAX_ALGORITMO_BYTES + 1)
    if len(contenido_archivo) > MAX_ALGORITMO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"El script supera el tamaño máximo permitido ({MAX_ALGORITMO_BYTES // 1024} KB).",
        )
    
    try:
        tipo_extraido = await extraer_tipo_algoritmo(contenido_archivo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # 4. Validamos que el tipo del formulario coincida con el metadato del script
    if tipo != tipo_extraido:
        raise HTTPException(
            status_code=400, 
            detail=f"El tipo del formulario ('{tipo}') no coincide con el metadato del script ('{tipo_extraido}'). "
                   f"Por favor, sube el script en el formulario de '{tipo_extraido}'."
        )

    # 5. Guardamos el archivo físicamente
    ruta_guardado = os.path.join("algoritmos", nombre_fichero)
    with open(ruta_guardado, "wb") as f:
        f.write(contenido_archivo)

    # 6. Guardamos en la base de datos con el tipo validado
    nuevo_algoritmo = models.Algoritmo(
        nombre=nombre,
        descripcion=descripcion,
        tipo=tipo_extraido,  # Guardamos el tipo validado
        ruta_archivo=nombre_fichero,
        es_publico=es_publico,
        autor_id=autor_id
    )
    db.add(nuevo_algoritmo)
    db.commit()
    db.refresh(nuevo_algoritmo)

    logger.info(
        "algoritmo_subido",
        extra={"algoritmo_id": nuevo_algoritmo.id, "tipo": tipo_extraido, "autor_id": autor_id},
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

    # 1. Validamos que sea un archivo de molécula (por ahora .mol2)
    if not nombre_fichero.endswith('.mol2'):
        raise HTTPException(status_code=400, detail="El archivo debe ser una molécula (.mol2)")

    # 2. Guardamos la molécula físicamente en la carpeta 'uploads/'
    #    Por trozos y con tope, igual que /moleculas/subir: aunque aquí el
    #    usuario esté autenticado, cargar el fichero entero en memoria sigue
    #    siendo un problema de capacidad, no solo de abuso.
    ruta_guardado = os.path.join("uploads", nombre_fichero)
    await guardar_subida(archivo_mol, ruta_guardado, MAX_SUBIDA_BYTES)

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

    # 5. Devolvemos el archivo para que el navegador lo descargue
    return FileResponse(
        path=ruta_archivo, 
        filename=peticion.ruta_mol_resultado, 
        media_type='chemical/x-mol2' # Le dice al navegador que es un archivo químico
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
            # Modo batch: el CSV de ranking es el archivo principal
            if rj.get("modo") == "batch" and rj.get("csv_ranking"):
                archivos.append(os.path.basename(rj["csv_ranking"]))
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
    response.headers["X-Total-Count"] = str(consulta.count())
    return consulta.order_by(models.Algoritmo.id).offset(pagina.offset).limit(pagina.limit).all()


@app.post("/moleculas/subir")
async def subir_molecula(
    archivo: UploadFile = File(...),
    tipo: str = Form("molecula"),   # "molecula" | "base_de_datos"
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
    ruta = os.path.join("uploads", nombre_fichero)
    escritos = await guardar_subida(archivo, ruta, MAX_SUBIDA_BYTES)

    # Contar moléculas si es SDF. Se hace releyendo el fichero por trozos y no
    # sobre el contenido en memoria, porque ya no existe tal contenido: el
    # volcado es en streaming precisamente para no tenerlo entero en RAM.
    num_moleculas = contar_moleculas_sdf(ruta) if ext == ".sdf" else None

    logger.info(
        "molecula_subida",
        extra={
            "usuario_id": usuario_actual.id,
            "nombre": nombre_fichero,
            "bytes": escritos,
        },
    )
    return {
        "nombre":        nombre_fichero,
        "tipo":          tipo,
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
    Borra un archivo de molécula de uploads/. Si el fichero pertenece a una
    petición de otro usuario, exige ser el propietario o admin; los
    ficheros del depósito público (sin petición asociada) los puede borrar
    cualquier usuario autenticado.
    """
    nombre_archivo = exigir_nombre_archivo_seguro(nombre_archivo)
    propietario_id = _propietario_de_archivo_uploads(nombre_archivo, db)
    if propietario_id is not None and propietario_id != usuario_actual.id and not es_admin(usuario_actual):
        raise HTTPException(status_code=403, detail="No tienes permiso para borrar este archivo")
    ruta = os.path.join("uploads", nombre_archivo)
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    os.remove(ruta)
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
    Lista las moléculas disponibles en el servidor.

    Combina dos fuentes:
      1. Archivos referenciados en la tabla 'peticiones' del usuario autenticado
         (o de otro usuario si quien pregunta es admin y pasa usuario_id).
      2. Archivos de molécula presentes físicamente en uploads/ que no estén
         en ninguna petición -- el "depósito público" -- que ve cualquier
         usuario autenticado, sea o no el propietario.

    Parámetro opcional:
      usuario_id — para que un admin consulte las moléculas de otro usuario;
      cualquier otro usuario que lo use recibe 403.
    """
    if usuario_id is not None and usuario_id != usuario_actual.id and not es_admin(usuario_actual):
        raise HTTPException(status_code=403, detail="No tienes permiso para ver las moléculas de otro usuario")
    usuario_objetivo = usuario_id if usuario_id is not None else usuario_actual.id

    extensiones_molecula = {".mol2", ".sdf", ".pdbqt", ".mol", ".pdb"}
    moleculas = {}  # nombre_archivo → dict con metadatos

    # 1. Moléculas de las peticiones del usuario objetivo (nunca de todos a la vez)
    query = db.query(models.Peticion).filter(models.Peticion.usuario_id == usuario_objetivo)

    for peticion in query.all():
        for nombre in (peticion.ruta_mol_original, peticion.ruta_mol_resultado):
            if not nombre:
                continue
            ruta = os.path.join("uploads", nombre)
            if os.path.exists(ruta) and os.path.splitext(nombre)[1].lower() in extensiones_molecula:
                moleculas[nombre] = {
                    "nombre":    nombre,
                    "origen":    "base_de_datos",
                    "tamano_kb": round(os.path.getsize(ruta) / 1024, 1),
                }

    # 2. Archivos físicos en uploads/ no registrados en ninguna petición: el
    #    depósito público, visible para cualquier usuario autenticado.
    #    "ficheros_con_dueño" incluye las peticiones de TODOS los usuarios,
    #    no solo las del usuario objetivo -- si no, el resultado privado de
    #    la petición de otro usuario se colaría aquí como si fuera público.
    ficheros_con_dueño = set()
    for original, resultado in db.query(models.Peticion.ruta_mol_original, models.Peticion.ruta_mol_resultado).all():
        if original:
            ficheros_con_dueño.add(original)
        if resultado:
            ficheros_con_dueño.add(resultado)

    if os.path.exists("uploads"):
        for nombre in os.listdir("uploads"):
            if nombre in moleculas or nombre in ficheros_con_dueño:
                continue
            ext = os.path.splitext(nombre)[1].lower()
            if ext in extensiones_molecula:
                ruta = os.path.join("uploads", nombre)
                moleculas[nombre] = {
                    "nombre":    nombre,
                    "origen":    "archivo_local",
                    "tamano_kb": round(os.path.getsize(ruta) / 1024, 1),
                }

    lista_completa = sorted(moleculas.values(), key=lambda m: m["nombre"])
    response.headers["X-Total-Count"] = str(len(lista_completa))
    return lista_completa[pagina.offset: pagina.offset + pagina.limit]

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

    db.delete(peticion)
    db.commit()
    
    return {"mensaje": f"Petición {peticion_id} eliminada correctamente"}


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

    # Borrar ejecuciones asociadas
    db.query(models.WorkflowExecution).filter(models.WorkflowExecution.workflow_id == workflow_id).delete()
    db.delete(workflow)
    db.commit()
    
    return {"mensaje": f"Workflow {workflow_id} eliminado correctamente"}


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

    # Revocar la tarea Celery (terminate=True para matar si ya está corriendo)
    if ejecucion.celery_task_id:
        from app.celery_app import celery_app as _celery
        _celery.control.revoke(ejecucion.celery_task_id, terminate=True, signal="SIGTERM")

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
    Sirve un archivo de la carpeta uploads/ para descarga directa. Exige
    estar autenticado; si el fichero pertenece a la petición de otro
    usuario, exige además ser su propietario o admin (los ficheros del
    depósito público, sin petición asociada, los puede descargar
    cualquier usuario autenticado).
    """
    nombre_archivo = exigir_nombre_archivo_seguro(nombre_archivo)
    propietario_id = _propietario_de_archivo_uploads(nombre_archivo, db)
    if propietario_id is not None and propietario_id != usuario_actual.id and not es_admin(usuario_actual):
        raise HTTPException(status_code=403, detail="No tienes permiso para descargar este archivo")
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
