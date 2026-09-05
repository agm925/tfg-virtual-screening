import os
from app.celery_app import celery_app
from app.database import SessionLocal
from app import models
from app.ejecutor import ejecutar_algoritmo
from app.email_utils import (
    correo_completado, correo_error,
    correo_workflow_completado, correo_workflow_error,
)
from app.workflow_executor import WorkflowExecutor, BatchWorkflowExecutor


@celery_app.task(bind=True, max_retries=0)
def ejecutar_peticion_async(self, peticion_id: int) -> dict:
    """
    Tarea Celery: ejecuta el algoritmo de una petición y notifica al usuario por correo.

    Flujo:
        1. Carga la petición y sus relaciones desde la BD.
        2. Marca el estado como PROCESANDO.
        3. Ejecuta el script Python del algoritmo sobre la molécula.
        4. Actualiza la BD con COMPLETADO o ERROR.
        5. Envía un correo de notificación al biólogo.
    """
    db = SessionLocal()
    peticion = None
    try:
        # 1. Cargar petición
        peticion = db.query(models.Peticion).filter(models.Peticion.id == peticion_id).first()
        if not peticion:
            return {"exito": False, "error": f"Petición {peticion_id} no encontrada"}

        usuario   = db.query(models.Usuario).filter(models.Usuario.id == peticion.usuario_id).first()
        algoritmo = db.query(models.Algoritmo).filter(models.Algoritmo.id == peticion.algoritmo_id).first()

        # 2. Marcar como procesando
        peticion.estado = "PROCESANDO"
        db.commit()

        # 3. Preparar rutas y ejecutar
        ruta_mol_entrada = os.path.join("uploads",    peticion.ruta_mol_original)
        ruta_algoritmo   = os.path.join("algoritmos", algoritmo.ruta_archivo)
        nombre_salida    = peticion.ruta_mol_original.replace(".mol2", "_resultado.mol2")
        ruta_mol_salida  = os.path.join("uploads", nombre_salida)

        resultado = ejecutar_algoritmo(ruta_algoritmo, ruta_mol_entrada, ruta_mol_salida)

        # 4. Actualizar BD
        if resultado["exito"]:
            peticion.estado           = "COMPLETADO"
            peticion.ruta_mol_resultado = nombre_salida
            db.commit()
            # 5a. Correo de éxito
            if usuario:
                correo_completado(usuario.nombre, usuario.email, peticion_id, algoritmo.nombre)
            return {"exito": True, "archivo": nombre_salida}
        else:
            peticion.estado = "ERROR"
            db.commit()
            # 5b. Correo de error
            if usuario:
                correo_error(usuario.nombre, usuario.email, peticion_id, algoritmo.nombre,
                             resultado.get("error", "error desconocido"))
            return {"exito": False, "error": resultado.get("error")}

    except Exception as exc:
        if peticion:
            peticion.estado = "ERROR"
            db.commit()
        raise exc
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=0)
def ejecutar_workflow_async(self, workflow_id: int, usuario_id: int, ejecucion_id: int) -> dict:
    """
    Tarea Celery: ejecuta un workflow KNIME completo y notifica al biólogo por correo.

    Flujo:
        1. Marca la ejecución como 'procesando'.
        2. Corre WorkflowExecutor sobre el grafo_json guardado en BD.
        3. Persiste los resultados y el estado final.
        4. Envía un correo al usuario con el resultado.
    """
    db = SessionLocal()
    ejecucion = None
    try:
        workflow  = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
        ejecucion = db.query(models.WorkflowExecution).filter(models.WorkflowExecution.id == ejecucion_id).first()
        usuario   = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()

        if not workflow or not ejecucion:
            return {"exito": False, "error": "Workflow o ejecución no encontrados"}

        # 1. Marcar como procesando
        ejecucion.estado = "procesando"
        workflow.estado  = "procesando"
        db.commit()

        # 2. Ejecutar
        executor = WorkflowExecutor(workflow.grafo_json, usuario_id)
        resultado = executor.ejecutar()

        # 3. Persistir resultados — versión slim (sin logs, sin binarios)
        estado_final = resultado.get("estado", "completado")

        # Extraer archivos de salida por nodo, descartar logs voluminosos
        nodos_slim = {}
        for nodo_id, nodo_res in resultado.get("resultados", {}).items():
            if not isinstance(nodo_res, dict):
                continue
            nodos_slim[nodo_id] = {k: v for k, v in nodo_res.items() if k != "log"}

        resultado_bd = {
            "estado":             estado_final,
            "exito":              resultado.get("exito", False),
            "errores":            resultado.get("errores", []),
            "duracion_segundos":  resultado.get("duracion_segundos", 0),
            "resultados":         nodos_slim,
        }

        ejecucion.estado            = estado_final
        ejecucion.resultados_json   = resultado_bd
        ejecucion.duracion_segundos = int(resultado.get("duracion_segundos", 0))
        workflow.estado             = estado_final
        db.commit()

        # 4. Correo de notificación
        if usuario:
            duracion = resultado.get("duracion_segundos", 0)
            if resultado.get("exito"):
                correo_workflow_completado(usuario.nombre, usuario.email, workflow.nombre, duracion)
            else:
                correo_workflow_error(usuario.nombre, usuario.email, workflow.nombre,
                                      resultado.get("errores", []))

        return resultado

    except Exception as exc:
        if ejecucion:
            ejecucion.estado = "error"
            db.commit()
        raise exc
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=0)
def ejecutar_workflow_batch_async(self, workflow_id: int, usuario_id: int, ejecucion_id: int) -> dict:
    """
    Tarea Celery: ejecuta el workflow sobre cada molécula del SDF del nodo selectDB,
    genera un ranking CSV y notifica al usuario.
    """
    db = SessionLocal()
    ejecucion = None
    try:
        workflow  = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
        ejecucion = db.query(models.WorkflowExecution).filter(models.WorkflowExecution.id == ejecucion_id).first()
        usuario   = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()

        if not workflow or not ejecucion:
            return {"exito": False, "error": "Workflow o ejecución no encontrados"}

        ejecucion.estado = "procesando"
        workflow.estado  = "procesando"
        ejecucion.resultados_json = {"modo": "batch", "progreso": 0, "total": 0, "molecula_actual": ""}
        db.commit()

        def on_progreso(actual, total, nombre_mol):
            ejecucion.resultados_json = {
                "modo":            "batch",
                "progreso":        actual,
                "total":           total,
                "molecula_actual": nombre_mol,
                "estado":          "procesando",
            }
            db.commit()

        executor  = BatchWorkflowExecutor(workflow.grafo_json, usuario_id)
        resultado = executor.ejecutar_batch(on_progreso=on_progreso)

        estado_final = resultado.get("estado", "completado")

        # Guardar solo resumen slim en BD — el CSV completo queda en disco
        resultado_bd = {
            "modo":             "batch",
            "estado":           estado_final,
            "exito":            resultado.get("exito", False),
            "total_moleculas":  resultado.get("total_moleculas", 0),
            "total_exito":      resultado.get("total_exito", 0),
            "total_error":      resultado.get("total_error", 0),
            "tipo_score":       resultado.get("tipo_score"),
            "csv_ranking":      resultado.get("csv_ranking"),
            "base_de_datos":    resultado.get("base_de_datos"),
            "duracion_segundos": resultado.get("duracion_segundos", 0),
            "ranking":          resultado.get("ranking", [])[:25],  # solo top-25 en BD
        }

        ejecucion.estado            = estado_final
        ejecucion.resultados_json   = resultado_bd
        ejecucion.duracion_segundos = int(resultado.get("duracion_segundos", 0))
        workflow.estado             = estado_final
        db.commit()

        if usuario:
            duracion = resultado.get("duracion_segundos", 0)
            if resultado.get("exito"):
                correo_workflow_completado(usuario.nombre, usuario.email, workflow.nombre, duracion)
            else:
                errores = [f"0 moléculas procesadas con éxito de {resultado.get('total_moleculas', '?')}"]
                correo_workflow_error(usuario.nombre, usuario.email, workflow.nombre, errores)

        return resultado

    except Exception as exc:
        if ejecucion:
            ejecucion.estado = "error"
            db.commit()
        raise exc
    finally:
        db.close()
