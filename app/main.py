import os
from fastapi import FastAPI, Depends, HTTPException, File, UploadFile, Form
from sqlalchemy.orm import Session
from app.database import engine, SessionLocal
from app import models, schemas
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from app.ejecutor import ejecutar_algoritmo
from app.workflow_executor import WorkflowExecutor
from datetime import datetime
import time

# Creamos las tablas en la base de datos (si no existen)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="API Virtual Screening",
    description="Backend para ejecución de algoritmos biomoleculares",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción aquí se pondría la URL exacta de tu web
    allow_credentials=True,
    allow_methods=["*"],  # Permite GET, POST, PUT, DELETE...
    allow_headers=["*"],  # Permite cualquier cabecera
)

# --- DEPENDENCIA DE BASE DE DATOS ---
# Esto es una "manguera" que se abre cuando un usuario hace una petición y se cierra al terminar
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- RUTAS (ENDPOINTS) ---

@app.get("/")
def ruta_raiz():
    return {"estado": "OK", "mensaje": "¡El motor del TFG está funcionando!"}

@app.post("/registro", response_model=schemas.UsuarioRespuesta)
def registrar_usuario(usuario: schemas.UsuarioRegistro, db: Session = Depends(get_db)):
    """
    Registra un nuevo usuario biólogo en la plataforma.
    """
    # 1. Comprobamos si el email ya existe en la base de datos
    usuario_existente = db.query(models.Usuario).filter(models.Usuario.email == usuario.email).first()
    if usuario_existente:
        raise HTTPException(status_code=400, detail="El email ya está registrado")
    
    # 2. Creamos el objeto del nuevo usuario (modelo)
    nuevo_usuario = models.Usuario(
        nombre=usuario.nombre,
        email=usuario.email, 
        password_hash=usuario.password_hash,  # ¡Ojo! En un proyecto real esto se encripta. Lo haremos más adelante.
        rol="biologo"  # Por defecto, todos los que se registran son biólogos
    )
    
    # 3. Lo guardamos físicamente en SQLite
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario) # Recargamos para obtener el ID que le ha asignado la base de datos
    
    return nuevo_usuario

@app.post("/algoritmos", response_model=schemas.AlgoritmoRespuesta)
async def subir_algoritmo(
    nombre: str = Form(...),
    descripcion: str = Form(...),
    autor_id: int = Form(...),             # Corregido: Ahora coincide con models.py
    es_publico: bool = Form(False),        # Añadido: Para aprovechar tu campo es_publico
    archivo: UploadFile = File(...),       # Lo llamamos "archivo" para no confundirlo con la ruta
    db: Session = Depends(get_db)
):
    """
    Sube un script de Python (.py) y lo registra en la base de datos.
    """
    # 1. Validamos que sea un script de Python
    if not archivo.filename.endswith('.py'):
        raise HTTPException(status_code=400, detail="El archivo debe ser un script de Python (.py)")

    # 2. Guardamos el archivo físicamente
    ruta_guardado = os.path.join("algoritmos", archivo.filename)
    with open(ruta_guardado, "wb") as f:
        f.write(await archivo.read())
        
    # 3. Guardamos en la base de datos
    nuevo_algoritmo = models.Algoritmo(
        nombre=nombre,
        descripcion=descripcion,
        ruta_archivo=archivo.filename,     # Corregido: Asignamos el nombre del archivo al campo ruta_archivo
        es_publico=es_publico,
        autor_id=autor_id                  # Corregido: Usamos autor_id
    )
    db.add(nuevo_algoritmo)
    db.commit()
    db.refresh(nuevo_algoritmo)
    
    return nuevo_algoritmo

@app.post("/peticiones", response_model=schemas.PeticionRespuesta)
async def crear_peticion(
    usuario_id: int = Form(...),
    algoritmo_id: int = Form(...),
    archivo_mol: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Recibe una molécula (.mol2), la guarda en 'uploads/' y crea una petición en cola.
    """
    # 1. Validamos que sea un archivo de molécula (por ahora .mol2)
    if not archivo_mol.filename.endswith('.mol2'):
        raise HTTPException(status_code=400, detail="El archivo debe ser una molécula (.mol2)")

    # 2. Guardamos la molécula físicamente en la carpeta 'uploads/'
    ruta_guardado = os.path.join("uploads", archivo_mol.filename)
    with open(ruta_guardado, "wb") as f:
        f.write(await archivo_mol.read())
        
    # 3. Creamos el registro en la base de datos con estado PENDIENTE
    nueva_peticion = models.Peticion(
        estado="PENDIENTE",
        ruta_mol_original=archivo_mol.filename,
        usuario_id=usuario_id,
        algoritmo_id=algoritmo_id
    )
    db.add(nueva_peticion)
    db.commit()
    db.refresh(nueva_peticion)
    
    return nueva_peticion

@app.post("/ejecutar/{peticion_id}")
def ejecutar_peticion(peticion_id: int, db: Session = Depends(get_db)):
    """
    Toma una petición PENDIENTE, ejecuta su algoritmo sobre su molécula y guarda el resultado.
    """
    # 1. Buscamos la petición en la base de datos
    peticion = db.query(models.Peticion).filter(models.Peticion.id == peticion_id).first()
    
    if not peticion:
        raise HTTPException(status_code=404, detail="Petición no encontrada")
    if peticion.estado != "PENDIENTE":
        raise HTTPException(status_code=400, detail="La petición ya ha sido procesada")

    # 2. Actualizamos estado a PROCESANDO
    peticion.estado = "PROCESANDO"
    db.commit()

    # 3. Preparamos las rutas de los archivos
    # Asumimos que la molécula está en 'uploads/' y el algoritmo en 'algoritmos/'
    ruta_mol_entrada = os.path.join("uploads", peticion.ruta_mol_original)
    ruta_algoritmo = os.path.join("algoritmos", peticion.algoritmo.ruta_archivo)
    
    # Generamos el nombre del archivo de salida (ej: DB00173_aligned.mol2)
    nombre_salida = peticion.ruta_mol_original.replace(".mol2", "_aligned.mol2")
    ruta_mol_salida = os.path.join("uploads", nombre_salida)

    # ESTO LO PONES:
    resultado = ejecutar_algoritmo(ruta_algoritmo, ruta_mol_entrada, ruta_mol_salida)

    if resultado["exito"]:
        peticion.estado = "COMPLETADO"
        peticion.ruta_mol_resultado = nombre_salida
        db.commit()
        db.refresh(peticion)
        return {
            "mensaje": "Ejecución completada con éxito",
            "peticion": peticion,
            "log_consola": resultado["log"]
        }
    else:
        peticion.estado = "ERROR"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Error en el algoritmo: {resultado['error']}")
    
@app.get("/descargar/{peticion_id}")
def descargar_resultado(peticion_id: int, db: Session = Depends(get_db)):
    """
    Permite descargar el archivo resultante (.mol2) de una petición completada.
    """
    # 1. Buscamos la petición en la base de datos
    peticion = db.query(models.Peticion).filter(models.Peticion.id == peticion_id).first()
    
    # 2. Validaciones de seguridad
    if not peticion:
        raise HTTPException(status_code=404, detail="Petición no encontrada")
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


@app.post("/login")
def login(datos: schemas.UsuarioLogin, db: Session = Depends(get_db)):
    # Buscamos al usuario por email
    usuario = db.query(models.Usuario).filter(models.Usuario.email == datos.email).first()
    
    # 1. CORRECCIÓN: Comparamos con usuario.password_hash
    if not usuario or usuario.password_hash != datos.password_hash: 
        raise HTTPException(status_code=400, detail="Credenciales incorrectas")
    
    return {
        "id": usuario.id, 
        "nombre": usuario.nombre,
        "email": usuario.email,
        "rol": usuario.rol.name if usuario.rol else "biologo" # Pasamos el enum a texto
    }

# --- NUEVA RUTA: HISTORIAL DE PETICIONES ---
@app.get("/peticiones/usuario/{u_id}")
def listar_peticiones_usuario(u_id: int, db: Session = Depends(get_db)):
    peticiones = db.query(models.Peticion).filter(models.Peticion.usuario_id == u_id).all()
    return peticiones

@app.get("/algoritmos")
def listar_algoritmos(db: Session = Depends(get_db)):
    return db.query(models.Algoritmo).all()

@app.delete("/peticiones/{peticion_id}")
def borrar_peticion(peticion_id: int, db: Session = Depends(get_db)):
    """
    Borra una petición de la base de datos por su ID.
    """
    peticion = db.query(models.Peticion).filter(models.Peticion.id == peticion_id).first()
    
    if not peticion:
        raise HTTPException(status_code=404, detail="Petición no encontrada")
    
    db.delete(peticion)
    db.commit()
    
    return {"mensaje": f"Petición {peticion_id} eliminada correctamente"}


# --- ENDPOINTS DE WORKFLOWS (KNIME) ---

@app.post("/workflows", response_model=schemas.WorkflowRespuesta)
def crear_workflow(workflow: schemas.WorkflowCreate, usuario_id: int = Form(...), db: Session = Depends(get_db)):
    """
    Crea un nuevo workflow vacío o con grafo inicial.
    """
    nuevo_workflow = models.Workflow(
        nombre=workflow.nombre,
        descripcion=workflow.descripcion,
        grafo_json=workflow.grafo_json or {"nodes": [], "edges": []},
        usuario_id=usuario_id,
        estado="borrador"
    )
    db.add(nuevo_workflow)
    db.commit()
    db.refresh(nuevo_workflow)
    return nuevo_workflow


@app.get("/workflows/usuario/{usuario_id}")
def listar_workflows_usuario(usuario_id: int, db: Session = Depends(get_db)):
    """
    Lista todos los workflows de un usuario.
    """
    workflows = db.query(models.Workflow).filter(models.Workflow.usuario_id == usuario_id).all()
    return workflows


@app.get("/workflows/{workflow_id}", response_model=schemas.WorkflowRespuesta)
def obtener_workflow(workflow_id: int, db: Session = Depends(get_db)):
    """
    Obtiene un workflow por su ID.
    """
    workflow = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow no encontrado")
    
    return workflow


@app.put("/workflows/{workflow_id}", response_model=schemas.WorkflowRespuesta)
def actualizar_workflow(workflow_id: int, workflow_update: schemas.WorkflowCreate, db: Session = Depends(get_db)):
    """
    Actualiza la estructura (grafo) de un workflow existente.
    """
    workflow = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow no encontrado")
    
    workflow.nombre = workflow_update.nombre
    workflow.descripcion = workflow_update.descripcion
    workflow.grafo_json = workflow_update.grafo_json
    workflow.fecha_actualizacion = datetime.utcnow()
    
    db.commit()
    db.refresh(workflow)
    return workflow


@app.delete("/workflows/{workflow_id}")
def borrar_workflow(workflow_id: int, db: Session = Depends(get_db)):
    """
    Borra un workflow y todas sus ejecuciones.
    """
    workflow = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow no encontrado")
    
    # Borrar ejecuciones asociadas
    db.query(models.WorkflowExecution).filter(models.WorkflowExecution.workflow_id == workflow_id).delete()
    db.delete(workflow)
    db.commit()
    
    return {"mensaje": f"Workflow {workflow_id} eliminado correctamente"}


@app.post("/workflows/{workflow_id}/ejecutar")
def ejecutar_workflow(workflow_id: int, usuario_id: int = Form(...), db: Session = Depends(get_db)):
    """
    Ejecuta un workflow completo de forma síncrona.
    Retorna los resultados de cada nodo.
    """
    # Obtener workflow
    workflow = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow no encontrado")
    
    # Crear registro de ejecución
    inicio = datetime.utcnow()
    ejecucion = models.WorkflowExecution(
        workflow_id=workflow_id,
        usuario_id=usuario_id,
        estado="procesando"
    )
    db.add(ejecucion)
    db.commit()
    db.refresh(ejecucion)
    
    try:
        # Ejecutar workflow
        executor = WorkflowExecutor(workflow.grafo_json, usuario_id)
        resultado_ejecucion = executor.ejecutar()
        
        # Actualizar estado de workflow
        workflow.estado = resultado_ejecucion.get("estado", "completado")
        
        # Guardar resultados de ejecución
        ejecucion.estado = resultado_ejecucion.get("estado", "completado")
        ejecucion.resultados_json = resultado_ejecucion
        ejecucion.duracion_segundos = int(resultado_ejecucion.get("duracion_segundos", 0))
        
        db.commit()
        db.refresh(ejecucion)
        
        return {
            "exito": resultado_ejecucion.get("exito"),
            "ejecucion_id": ejecucion.id,
            "estado": resultado_ejecucion.get("estado"),
            "resultados": resultado_ejecucion.get("resultados"),
            "errores": resultado_ejecucion.get("errores"),
            "duracion_segundos": resultado_ejecucion.get("duracion_segundos")
        }
    
    except Exception as e:
        # Registrar error
        ejecucion.estado = "error"
        ejecucion.resultados_json = {"error": str(e)}
        workflow.estado = "fallido"
        db.commit()
        
        raise HTTPException(status_code=500, detail=f"Error ejecutando workflow: {str(e)}")


@app.get("/workflows/{workflow_id}/ejecuciones")
def obtener_ejecuciones_workflow(workflow_id: int, db: Session = Depends(get_db)):
    """
    Obtiene el historial de ejecuciones de un workflow.
    """
    ejecuciones = db.query(models.WorkflowExecution).filter(
        models.WorkflowExecution.workflow_id == workflow_id
    ).all()
    return ejecuciones


@app.get("/workflows/ejecuciones/{ejecucion_id}", response_model=schemas.WorkflowExecutionRespuesta)
def obtener_ejecucion(ejecucion_id: int, db: Session = Depends(get_db)):
    """
    Obtiene los detalles de una ejecución específica.
    """
    ejecucion = db.query(models.WorkflowExecution).filter(
        models.WorkflowExecution.id == ejecucion_id
    ).first()
    
    if not ejecucion:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada")
    
    return ejecucion
