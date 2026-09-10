import os
import time
from app.celery_app import celery_app
from app.database import SessionLocal
from app import models
from app.ejecutor import ejecutar_algoritmo
from app.email_utils import (
    correo_completado, correo_error,
    correo_workflow_completado, correo_workflow_error,
)
from app.workflow_executor import WorkflowExecutor, BatchWorkflowExecutor
from app.models import Archivo, VisibilidadArchivo
from app.logging_config import logger
from app.formatos import corregir_extension, extension_salida


def _registrar_resultados(db, nombres, usuario_id, ejecucion_id=None, peticion_id=None):
    """
    Da de alta en el registro `archivos` los ficheros que ha producido una
    ejecucion, como resultados PRIVADOS de su propietario.

    Sin esto caian en el "deposito compartido" --no constaban en ninguna
    tabla-- y cualquier usuario autenticado podia descargarlos y borrarlos.
    """
    directorio = "uploads"
    for nombre in nombres:
        nombre = os.path.basename(nombre)
        ruta = os.path.join(directorio, nombre)
        if not os.path.exists(ruta):
            continue
        archivo = db.query(Archivo).filter(Archivo.nombre == nombre).first()
        if archivo is None:
            archivo = Archivo(nombre=nombre)
            db.add(archivo)
        archivo.propietario_id = usuario_id
        archivo.visibilidad = VisibilidadArchivo.resultado
        archivo.tamano_bytes = os.path.getsize(ruta)
        if ejecucion_id is not None:
            archivo.ejecucion_id = ejecucion_id
        if peticion_id is not None:
            archivo.peticion_id = peticion_id
    db.commit()


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

        # La extension de salida la decide la convencion compartida, no un
        # ".mol2" fijo. Antes se construia como
        #     ruta_mol_original.replace(".mol2", "_resultado.mol2")
        # de modo que el JSON de filtroLipinski --o de Tanimoto, o de RMSD--
        # acababa en un fichero que decia ser una molecula: la biblioteca lo
        # ofrecia como tal y el visor 3D no mostraba nada.
        base_entrada, ext_entrada = os.path.splitext(peticion.ruta_mol_original)
        tipo_algoritmo = algoritmo.tipo.value if algoritmo.tipo else None
        ext_salida = extension_salida(algoritmo.ruta_archivo, tipo_algoritmo, ext_entrada)
        nombre_salida   = f"{base_entrada}_resultado{ext_salida}"
        ruta_mol_salida = os.path.join("uploads", nombre_salida)

        resultado = ejecutar_algoritmo(ruta_algoritmo, ruta_mol_entrada, ruta_mol_salida)

        # 4. Actualizar BD
        if resultado["exito"]:
            # Red de seguridad para algoritmos subidos por el usuario, cuyo
            # formato de salida no se puede predecir por el nombre: si lo que
            # se ha escrito es un JSON, se renombra en vez de dejarlo pasar
            # como molecula.
            ruta_final = corregir_extension(ruta_mol_salida)
            nombre_salida = os.path.basename(ruta_final)

            peticion.estado           = "COMPLETADO"
            peticion.ruta_mol_resultado = nombre_salida
            db.commit()
            _registrar_resultados(db, [nombre_salida], peticion.usuario_id,
                                  peticion_id=peticion.id)
            # 5a. Correo de exito
            if usuario:
                correo_completado(usuario.nombre, usuario.email, peticion_id, algoritmo.nombre)
            return {"exito": True, "archivo": nombre_salida}
        else:
            # Un algoritmo que falla suele dejar escrito su JSON de error en la
            # ruta de salida. Ese fichero no es un resultado: si se queda en
            # disco, aparece en la biblioteca como una molecula que no se puede
            # abrir. Se borra.
            if os.path.exists(ruta_mol_salida):
                os.remove(ruta_mol_salida)
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
        executor = WorkflowExecutor(workflow.grafo_json, usuario_id,
                                    ejecucion_id=ejecucion.id)
        resultado = executor.ejecutar()

        # 3. Persistir resultados — versión slim (sin logs, sin binarios)
        estado_final = resultado.get("estado", "completado")

        _registrar_resultados(db, executor.archivos_generados, usuario_id,
                              ejecucion_id=ejecucion.id)

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


# ---------------------------------------------------------------------------
# Cribado en lote: coordinador + subtareas en paralelo + consolidacion
#
# Antes esto era UNA sola tarea Celery que recorria las N moleculas en un
# bucle. Como consecuencia, `--scale worker=N` no aceleraba el caso de uso
# principal de la plataforma: los demas workers quedaban ociosos mientras uno
# solo cargaba con el cribado entero. En modo slurm era todavia peor, porque
# cada molecula y cada nodo generaban un sbatch que se enviaba y se esperaba
# antes del siguiente: el cluster se usaba como una maquina remota de un
# trabajo a la vez.
#
# Ahora el trabajo se reparte con un `chord`: un grupo de subtareas que
# procesan bloques de moleculas EN PARALELO, y un callback que se ejecuta una
# sola vez, cuando todas terminan, para ordenar el ranking y generar el CSV.
# ---------------------------------------------------------------------------

def _clave_progreso(ejecucion_id: int) -> str:
    return f"batch:progreso:{ejecucion_id}"


def _clave_cancelacion(ejecucion_id: int) -> str:
    return f"batch:cancelado:{ejecucion_id}"


def _redis():
    """Cliente Redis, o None si no responde.

    El progreso y la cancelacion se apoyan en Redis --que ya forma parte del
    stack como broker-- pero ninguno de los dos es esencial para que el
    cribado termine: si Redis no esta, se pierde el contador, no el resultado.
    """
    try:
        import redis as _r
        from app.config import REDIS_URL
        cliente = _r.from_url(REDIS_URL, socket_connect_timeout=2, decode_responses=True)
        cliente.ping()
        return cliente
    except Exception:
        return None


def marcar_cancelacion(ejecucion_id: int) -> None:
    """
    Senala que una ejecucion en lote debe abortarse.

    Con una unica tarea bastaba con revocarla con terminate=True. Repartido en
    un chord eso ya no vale: revocar el coordinador no detiene las subtareas
    que ya estan corriendo. Se usa una bandera que cada subtarea consulta antes
    de cada molecula, de modo que la cancelacion sigue funcionando y ademas no
    deja el bloque a medias de forma abrupta.
    """
    cliente = _redis()
    if cliente is not None:
        cliente.setex(_clave_cancelacion(ejecucion_id), 24 * 3600, "1")


@celery_app.task(bind=True, max_retries=0)
def procesar_bloque_batch(self, workflow_json: dict, usuario_id: int,
                          ejecucion_id: int, indices: list) -> list:
    """
    Subtarea: ejecuta el workflow sobre un bloque de moleculas.

    Devuelve la lista de resultados del bloque, que el callback del chord
    recibira junto a la de los demas. No lanza excepciones hacia arriba: un
    bloque que falla entero impediria que el chord llegara a consolidar, asi
    que los errores se devuelven como resultados marcados.
    """
    cliente = _redis()

    def debe_parar():
        return cliente is not None and cliente.exists(_clave_cancelacion(ejecucion_id))

    # El progreso se escribe a la base de datos COMO MUCHO cada
    # INTERVALO_PROGRESO_S segundos, no en cada molecula.
    #
    # El contador autoritativo es el INCR de Redis, que es barato. Reflejarlo
    # en la fila de la ejecucion es solo para que el frontend lo lea con su
    # sondeo habitual, y ese sondeo va cada 3 s: escribir mas a menudo no se
    # ve en pantalla y si se nota en la base de datos. Antes se hacia un commit
    # por molecula --mil moleculas, mil escrituras de un blob JSON-- y ademas
    # con la sesion abierta durante todo el lote.
    INTERVALO_PROGRESO_S = 2.0
    ultimo_volcado = [0.0]

    def al_terminar_molecula(nombre):
        if cliente is None:
            return
        hechas = cliente.incr(_clave_progreso(ejecucion_id))
        cliente.expire(_clave_progreso(ejecucion_id), 24 * 3600)

        ahora = time.monotonic()
        if ahora - ultimo_volcado[0] < INTERVALO_PROGRESO_S:
            return
        ultimo_volcado[0] = ahora

        # Varias subtareas escriben a la vez y gana la ultima, lo que para un
        # indicador de avance es aceptable.
        db = SessionLocal()
        try:
            ejecucion = db.query(models.WorkflowExecution).filter(
                models.WorkflowExecution.id == ejecucion_id).first()
            if ejecucion is not None and isinstance(ejecucion.resultados_json, dict):
                datos = dict(ejecucion.resultados_json)
                datos["progreso"] = hechas
                datos["molecula_actual"] = nombre
                ejecucion.resultados_json = datos
                db.commit()
        finally:
            db.close()

    try:
        executor = BatchWorkflowExecutor(workflow_json, usuario_id, ejecucion_id=ejecucion_id)
        return executor.procesar_bloque(indices, on_molecula=al_terminar_molecula,
                                        debe_parar=debe_parar)
    except Exception as exc:  # noqa: BLE001
        return [{
            "nombre": f"bloque_{indices[0] if indices else '?'}",
            "score": None, "tipo_score": None, "exito": False,
            "errores_nodo": [str(exc)], "archivos": [],
        }]


@celery_app.task(bind=True, max_retries=0)
def consolidar_batch(self, resultados_por_bloque: list, workflow_id: int,
                     usuario_id: int, ejecucion_id: int, nombre_bd: str,
                     total_moleculas: int, inicio_ts: float) -> dict:
    """
    Callback del chord: se ejecuta una sola vez, cuando todos los bloques han
    terminado. Aplana los resultados, ordena el ranking, genera el CSV,
    persiste el resumen y notifica por correo.
    """
    db = SessionLocal()
    try:
        ejecucion = db.query(models.WorkflowExecution).filter(
            models.WorkflowExecution.id == ejecucion_id).first()
        workflow = db.query(models.Workflow).filter(
            models.Workflow.id == workflow_id).first()
        usuario = db.query(models.Usuario).filter(
            models.Usuario.id == usuario_id).first()
        if ejecucion is None or workflow is None:
            return {"exito": False, "error": "Workflow o ejecución no encontrados"}

        # Aplanar: cada subtarea devolvio la lista de su bloque.
        planos = [r for bloque in (resultados_por_bloque or []) for r in (bloque or [])]

        cliente = _redis()
        cancelado = cliente is not None and cliente.exists(_clave_cancelacion(ejecucion_id))

        executor = BatchWorkflowExecutor(workflow.grafo_json, usuario_id,
                                         ejecucion_id=ejecucion_id)
        resultado = executor.consolidar(
            planos, nombre_bd, total_moleculas, time.time() - inicio_ts)

        if cancelado:
            resultado["estado"] = "cancelado"
            resultado["exito"] = False

        # Los ficheros producidos son privados de su propietario.
        generados = [a for r in planos for a in (r.get("archivos") or [])]
        if resultado.get("csv_ranking"):
            generados.append(resultado["csv_ranking"])
        _registrar_resultados(db, generados, usuario_id, ejecucion_id=ejecucion_id)

        estado_final = resultado.get("estado", "completado")
        ejecucion.estado = estado_final
        ejecucion.resultados_json = {
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
            "ranking":          resultado.get("ranking", [])[:25],   # solo top-25 en BD
            "progreso":         total_moleculas,
            "total":            total_moleculas,
        }
        ejecucion.duracion_segundos = int(resultado.get("duracion_segundos", 0))
        workflow.estado = estado_final
        db.commit()

        if cliente is not None:
            cliente.delete(_clave_progreso(ejecucion_id))
            cliente.delete(_clave_cancelacion(ejecucion_id))

        if usuario and not cancelado:
            if resultado.get("exito"):
                correo_workflow_completado(usuario.nombre, usuario.email,
                                           workflow.nombre,
                                           resultado.get("duracion_segundos", 0))
            else:
                correo_workflow_error(
                    usuario.nombre, usuario.email, workflow.nombre,
                    [f"0 moléculas procesadas con éxito de {total_moleculas}"])

        return resultado
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=0)
def ejecutar_workflow_batch_async(self, workflow_id: int, usuario_id: int, ejecucion_id: int) -> dict:
    """
    Coordinador del cribado en lote.

    No procesa ninguna molecula: cuenta cuantas hay, las reparte en bloques y
    lanza un chord. Termina en seguida, de modo que no ocupa un worker durante
    todo el cribado.
    """
    from celery import chord

    from app.config import BATCH_TAMANO_BLOQUE

    db = SessionLocal()
    ejecucion = None
    try:
        workflow  = db.query(models.Workflow).filter(models.Workflow.id == workflow_id).first()
        ejecucion = db.query(models.WorkflowExecution).filter(
            models.WorkflowExecution.id == ejecucion_id).first()
        if not workflow or not ejecucion:
            return {"exito": False, "error": "Workflow o ejecución no encontrados"}

        executor = BatchWorkflowExecutor(workflow.grafo_json, usuario_id,
                                         ejecucion_id=ejecucion_id)
        nombre_bd, ruta_sdf = executor.localizar_base_de_datos()

        # Solo los indices: no se materializa ninguna molecula todavia. Cada
        # subtarea extrae las suyas cuando le toca, de modo que en ningun
        # momento hay mas ficheros temporales que los del bloque en curso.
        indices = executor.indices_validos(ruta_sdf)
        if not indices:
            raise ValueError("La base de datos no contiene moléculas válidas")

        bloques = [indices[i:i + BATCH_TAMANO_BLOQUE]
                   for i in range(0, len(indices), BATCH_TAMANO_BLOQUE)]

        ejecucion.estado = "procesando"
        workflow.estado  = "procesando"
        ejecucion.resultados_json = {
            "modo": "batch", "progreso": 0, "total": len(indices),
            "molecula_actual": "", "estado": "procesando",
            "bloques": len(bloques),
        }
        db.commit()

        cliente = _redis()
        if cliente is not None:
            cliente.delete(_clave_progreso(ejecucion_id))
            cliente.delete(_clave_cancelacion(ejecucion_id))

        grafo = workflow.grafo_json
        tarea = chord(
            (procesar_bloque_batch.s(grafo, usuario_id, ejecucion_id, bloque)
             for bloque in bloques),
            consolidar_batch.s(workflow_id, usuario_id, ejecucion_id, nombre_bd,
                               len(indices), time.time()),
        )()

        logger.info("batch_repartido", extra={
            "ejecucion_id": ejecucion_id, "moleculas": len(indices),
            "bloques": len(bloques), "tamano_bloque": BATCH_TAMANO_BLOQUE,
        })
        return {"exito": True, "bloques": len(bloques), "moleculas": len(indices),
                "chord_id": getattr(tarea, "id", None)}

    except Exception as exc:
        if ejecucion:
            ejecucion.estado = "error"
            ejecucion.resultados_json = {"modo": "batch", "estado": "error",
                                         "errores": [str(exc)]}
            db.commit()
        raise
    finally:
        db.close()
