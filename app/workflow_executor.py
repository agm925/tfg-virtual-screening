"""
Motor de ejecución de Workflows KNIME
Parsea la estructura de nodos y conexiones, ejecuta secuencialmente los algoritmos.
"""

import copy
import csv
import json
import os
import re
from typing import Dict, List, Any, Tuple
from datetime import datetime
from app.ejecutor import (ejecutar_algoritmo, ejecutar_algoritmos_en_lote,
                          desviar_invocaciones)


def resolver_algoritmo(nombre_base: str, usuario_id: int = None) -> str:
    """
    Devuelve la ruta del script de un algoritmo, comprobando que se pueda usar.

    Los nodos del grafo referencian el algoritmo por el nombre de su fichero,
    no por su id en la base de datos, asi que un workflow GUARDADO sigue
    apuntando al mismo .py indefinidamente. Sin esta comprobacion, desactivar
    un algoritmo desde el panel de administracion lo retiraria del catalogo y
    de las peticiones nuevas, pero los flujos ya guardados seguirian
    ejecutandolo tal cual: el agujero justo por donde se colaria el algoritmo
    incorrecto que el administrador acaba de retirar.

    Por la misma razon se comprueba aqui la VISIBILIDAD, y no solo en el
    listado: el grafo lo manda el cliente, asi que puede nombrar el .py de un
    algoritmo privado ajeno aunque no aparezca en ningun desplegable. Filtrar
    el catalogo no es control de acceso; esto si lo es.

    Se bloquea solo si el algoritmo CONSTA en la base. Un .py del catalogo sin
    fila asociada --los que vienen con el repositorio, y los que crean los
    tests-- se sigue aceptando como hasta ahora: aqui se aplica una retirada o
    una privacidad explicitas, no se exige estar registrado.
    """
    ruta_algoritmo = os.path.join("algoritmos", f"{nombre_base}.py")
    if not os.path.exists(ruta_algoritmo):
        raise ValueError(f"Algoritmo no encontrado: {ruta_algoritmo}")

    # Import diferido y sesion propia: esto corre dentro de un worker de
    # Celery, no en una peticion HTTP, asi que no hay sesion que heredar.
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    try:
        registro = (
            db.query(models.Algoritmo)
            .filter(models.Algoritmo.ruta_archivo == f"{nombre_base}.py")
            .first()
        )
        if registro is not None and not registro.activo:
            raise ValueError(
                f"El algoritmo '{registro.nombre}' ha sido desactivado por un "
                f"administrador y no puede ejecutarse."
            )

        if registro is not None and not registro.es_publico:
            usuario = (db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
                       if usuario_id is not None else None)
            es_admin = bool(usuario and usuario.rol and usuario.rol.value == "admin")
            if registro.autor_id != usuario_id and not es_admin:
                raise ValueError(
                    f"El algoritmo '{registro.nombre}' es privado de otro usuario."
                )
    finally:
        db.close()

    return ruta_algoritmo


class WorkflowExecutor:
    """Ejecuta workflows compilando el grafo y ejecutando nodos en orden topológico."""

    def __init__(self, workflow_json: Dict[str, Any], usuario_id: int,
                 ejecucion_id: int = None, sufijo_extra: str = ""):
        self.workflow_json = workflow_json
        self.usuario_id    = usuario_id
        self.ejecucion_id  = ejecucion_id
        # Token que hace unicos los nombres de salida entre ejecuciones.
        #
        # Antes los nombres se derivaban SOLO del id del nodo
        # ("comparacion_<nodo>.json", "docking_<nodo>.sdf"), y el id del nodo
        # es constante para un workflow dado. Dos ejecuciones simultaneas del
        # mismo flujo --dos usuarios, o el mismo lanzandolo dos veces, o varias
        # replicas de worker, que es justo lo que habilita --scale worker=N--
        # escribian sobre el mismo fichero y se devolvian resultados cruzados.
        # Incorporar el id de la ejecucion al nombre lo elimina.
        #
        # Se mantienen los ficheros PLANOS en uploads/, sin subcarpetas por
        # ejecucion, porque los grafos ya guardados referencian sus moleculas
        # por nombre suelto y el frontend descarta el directorio al construir
        # la descarga: separarlos en carpetas romperia ambas cosas.
        self.token = ""
        if ejecucion_id is not None:
            self.token = f"_e{ejecucion_id}"
        if sufijo_extra:
            self.token += f"_{sufijo_extra}"
        # Nombres de los ficheros producidos, para que quien orquesta pueda
        # registrarlos como resultados privados de su propietario.
        self.archivos_generados = []
        self.nodos         = workflow_json.get("nodes", [])
        self.conexiones    = workflow_json.get("edges", [])
        self.resultados    = {}
        self.mapeo_archivos = {}  # { nodo_id: ruta_archivo }
        self.errores       = []
        self.inicio        = None
        self.fin           = None

    # ------------------------------------------------------------------
    # Utilidades de grafo
    # ------------------------------------------------------------------

    def obtener_orden_ejecucion(self) -> List[str]:
        """Orden topológico (algoritmo de Kahn) sobre el grafo de dependencias.

        Las aristas que referencian nodos inexistentes se ignoran silenciosamente
        (pueden quedar en el grafo_json si el usuario borró nodos entre ejecuciones).
        """
        ids_validos = {nodo["id"] for nodo in self.nodos}
        grafo       = {nodo["id"]: [] for nodo in self.nodos}
        in_degree   = {nodo["id"]: 0  for nodo in self.nodos}

        for conexion in self.conexiones:
            origen  = conexion.get("source") or conexion.get("nodo_origen")
            destino = conexion.get("target") or conexion.get("nodo_destino")
            # Ignorar aristas cuyos extremos no existen como nodos activos
            if not origen or not destino:
                continue
            if origen not in ids_validos or destino not in ids_validos:
                continue
            if destino not in grafo[origen]:          # evitar duplicados
                grafo[origen].append(destino)
                in_degree[destino] += 1

        cola  = [nid for nid in in_degree if in_degree[nid] == 0]
        orden = []
        while cola:
            nodo_actual = cola.pop(0)
            orden.append(nodo_actual)
            for vecino in grafo[nodo_actual]:
                in_degree[vecino] -= 1
                if in_degree[vecino] == 0:
                    cola.append(vecino)

        if len(orden) != len(ids_validos):
            # Solo puede pasar si hay un ciclo real en el grafo
            nodos_en_ciclo = [nid for nid in ids_validos if nid not in orden]
            raise ValueError(
                f"El workflow contiene un ciclo entre los nodos: {nodos_en_ciclo}"
            )
        return orden

    def obtener_nodo_por_id(self, nodo_id: str) -> Dict[str, Any]:
        for nodo in self.nodos:
            if nodo["id"] == nodo_id:
                return nodo
        raise ValueError(f"Nodo {nodo_id} no encontrado en el workflow")

    def obtener_entrada_nodo(self, nodo_id: str, puerto: str = "input") -> Tuple[str, str]:
        """Devuelve (nodo_origen_id, ruta_archivo) para la conexión que llega al puerto dado."""
        for conexion in self.conexiones:
            destino       = conexion.get("target") or conexion.get("nodo_destino")
            puerto_dest   = conexion.get("targetHandle") or conexion.get("puerto_destino", "input")
            if destino == nodo_id and puerto_dest == puerto:
                origen = conexion.get("source") or conexion.get("nodo_origen")
                return origen, self.mapeo_archivos.get(origen)
        return None, None

    # ------------------------------------------------------------------
    # Ejecutores de nodo
    # ------------------------------------------------------------------

    def ejecutar_nodo_upload(self, nodo_id: str, nodo: Dict[str, Any]) -> bool:
        try:
            datos         = nodo.get("data", {})
            nombre_archivo = datos.get("nombre_archivo")
            if not nombre_archivo:
                raise ValueError(f"Nodo {nodo_id}: falta nombre_archivo")

            ruta = os.path.join("uploads", nombre_archivo)
            if not os.path.exists(ruta):
                raise ValueError(f"Archivo no encontrado: {ruta}")

            self.mapeo_archivos[nodo_id] = ruta
            self.resultados[nodo_id] = {"tipo": "upload", "archivo": ruta, "estado": "exito"}
            return True
        except Exception as e:
            self.errores.append(f"Error en nodo UPLOAD {nodo_id}: {e}")
            return False

    def ejecutar_nodo_algoritmo(self, nodo_id: str, nodo: Dict[str, Any]) -> bool:
        """Nodo de alineación (1 entrada obligatoria + 1 referencia opcional)."""
        try:
            datos            = nodo.get("data", {})
            ruta_script      = datos.get("algoritmo_ruta") or datos.get("algoritmo_nombre", "centerMol")
            if ruta_script.endswith(".py"):
                ruta_script = ruta_script[:-3]
            algoritmo_nombre = ruta_script  # nombre base del .py, sin extensión

            _, archivo_entrada = self.obtener_entrada_nodo(nodo_id, "input_molecula")
            if not archivo_entrada:
                raise ValueError(f"Nodo {nodo_id}: sin entrada de molécula")

            ruta_algoritmo = resolver_algoritmo(algoritmo_nombre, self.usuario_id)

            base, ext  = os.path.splitext(os.path.basename(archivo_entrada))
            # alinear3D y alinearMCS siempre fuerzan la salida a .sdf internamente
            # (ver alinear3D.alinear_o3a / alinearMCS.alinear_mcs), así que aquí debemos
            # anticipar esa coerción para que mapeo_archivos no apunte a un archivo
            # con extensión .mol2 que en realidad nunca se escribió.
            if algoritmo_nombre in ("alinear3D", "alinearMCS"):
                ext_salida = ".sdf"
            else:
                ext_salida = ext if ext in (".mol2", ".sdf") else ".sdf"
            nombre_salida = f"{base}_alineado_{nodo_id}{self.token}{ext_salida}"
            ruta_salida   = os.path.join("uploads", nombre_salida)

            # Comprobamos si hay una referencia conectada (para O3A / MCS)
            _, archivo_ref = self.obtener_entrada_nodo(nodo_id, "input_referencia")

            if archivo_ref:
                resultado = ejecutar_algoritmo(ruta_algoritmo, archivo_entrada, archivo_ref, ruta_salida)
            else:
                resultado = ejecutar_algoritmo(ruta_algoritmo, archivo_entrada, ruta_salida)

            if not resultado.get("exito"):
                raise ValueError(f"Error ejecutando algoritmo: {resultado.get('error')}")

            self.mapeo_archivos[nodo_id] = ruta_salida
            self.archivos_generados.append(os.path.basename(ruta_salida))
            self.resultados[nodo_id] = {
                "tipo":            "alineacion",
                "archivo_entrada": archivo_entrada,
                "archivo_salida":  ruta_salida,
                "algoritmo":       algoritmo_nombre,
                "log":             resultado.get("log"),
                "estado":          "exito",
            }
            return True
        except Exception as e:
            self.errores.append(f"Error en nodo ALINEACION {nodo_id}: {e}")
            return False

    def ejecutar_nodo_comparacion(self, nodo_id: str, nodo: Dict[str, Any]) -> bool:
        """Nodo de comparación: dos moléculas de entrada → resultado JSON."""
        try:
            datos            = nodo.get("data", {})
            # Usar ruta_archivo guardada por el nodo (contiene el nombre real del .py)
            # Si no existe (workflows guardados antes de este cambio), intentar con el nombre
            ruta_script = datos.get("algoritmo_ruta") or datos.get("algoritmo_nombre", "similaridadTanimoto")
            # Quitar extensión si ya viene con ella
            if ruta_script.endswith(".py"):
                ruta_script = ruta_script[:-3]

            _, archivo_mol1 = self.obtener_entrada_nodo(nodo_id, "input_mol1")
            _, archivo_mol2 = self.obtener_entrada_nodo(nodo_id, "input_mol2")

            if not archivo_mol1 or not archivo_mol2:
                raise ValueError(f"Nodo {nodo_id}: faltan las dos moléculas de entrada")

            ruta_algoritmo = resolver_algoritmo(ruta_script, self.usuario_id)

            # Los algoritmos de comparación que producen molécula (alinear3D, alinearMCS)
            # usan extensión .sdf; los de métricas (tanimoto, rmsd) usan .json
            nombre_base = ruta_script.lower()
            if any(k in nombre_base for k in ("alinear", "align")):
                nombre_salida = f"comparacion_{nodo_id}{self.token}.sdf"
            else:
                nombre_salida = f"comparacion_{nodo_id}{self.token}.json"
            ruta_salida = os.path.join("uploads", nombre_salida)

            resultado = ejecutar_algoritmo(ruta_algoritmo, archivo_mol1, archivo_mol2, ruta_salida)

            if not resultado.get("exito"):
                raise ValueError(f"Error ejecutando comparación: {resultado.get('error')}")

            self.mapeo_archivos[nodo_id] = ruta_salida
            self.archivos_generados.append(os.path.basename(ruta_salida))

            # Si la salida es JSON la leemos para mostrársela al usuario
            resultado_comparacion = {}
            if ruta_salida.endswith(".json") and os.path.exists(ruta_salida):
                with open(ruta_salida, "r", encoding="utf-8") as f:
                    resultado_comparacion = json.load(f)

            self.resultados[nodo_id] = {
                "tipo":           "comparacion",
                # Clave que el banco de pruebas observo al subir el
                # algoritmo: evita que _extraer_score tenga que
                # adivinarla por su nombre.
                "clave_score":    datos.get("clave_score"),
                "archivo_mol1":   archivo_mol1,
                "archivo_mol2":   archivo_mol2,
                "archivo_salida": ruta_salida,
                "algoritmo":      ruta_script,
                "resultado_json": resultado_comparacion,
                "log":            resultado.get("log"),
                "estado":         "exito",
            }
            return True
        except Exception as e:
            self.errores.append(f"Error en nodo COMPARACION {nodo_id}: {e}")
            return False

    def ejecutar_nodo_preprocesado(self, nodo_id: str, nodo: Dict[str, Any]) -> bool:
        """Nodo de preprocesado: 1 entrada → molécula procesada o JSON de propiedades."""
        try:
            datos            = nodo.get("data", {})
            ruta_script      = datos.get("algoritmo_ruta") or datos.get("algoritmo_nombre", "preparacionObabel")
            if ruta_script.endswith(".py"):
                ruta_script = ruta_script[:-3]
            algoritmo_nombre = ruta_script

            _, archivo_entrada = self.obtener_entrada_nodo(nodo_id, "input_molecula")
            if not archivo_entrada:
                raise ValueError(f"Nodo {nodo_id}: sin entrada de molécula")

            ruta_algoritmo = resolver_algoritmo(algoritmo_nombre, self.usuario_id)

            # filtroLipinski produce JSON; filtroObabel filtra y devuelve molécula; el resto produce molécula
            nombre_base = algoritmo_nombre.lower()
            if "lipinski" in nombre_base:
                nombre_salida = f"{os.path.splitext(os.path.basename(archivo_entrada))[0]}_lipinski_{nodo_id}{self.token}.json"
            else:
                base, ext  = os.path.splitext(os.path.basename(archivo_entrada))
                formato_pedido = datos.get("formato_salida")
                if "preparacionobabel" in nombre_base and formato_pedido and formato_pedido != "mismo":
                    ext_salida = f".{formato_pedido}"
                else:
                    ext_salida = ext if ext in (".mol2", ".sdf") else ".sdf"
                sufijo = "filtrado" if "filtro" in nombre_base else "prep"
                nombre_salida = f"{base}_{sufijo}_{nodo_id}{self.token}{ext_salida}"
            ruta_salida = os.path.join("uploads", nombre_salida)

            if "filtro" in nombre_base and "lipinski" not in nombre_base:
                expresion_filtro = datos.get("filtro_expresion") or "MW>200"
                resultado = ejecutar_algoritmo(ruta_algoritmo, archivo_entrada, ruta_salida,
                                               flags=[expresion_filtro])
            elif "preparacionobabel" in nombre_base:
                flags = []
                if datos.get("sin_h"):
                    flags.append("--sin-h")
                if datos.get("sin_3d"):
                    flags.append("--sin-3d")
                if datos.get("sin_center"):
                    flags.append("--sin-center")
                resultado = ejecutar_algoritmo(ruta_algoritmo, archivo_entrada, ruta_salida,
                                               flags=flags)
            else:
                resultado = ejecutar_algoritmo(ruta_algoritmo, archivo_entrada, ruta_salida)

            if not resultado.get("exito"):
                raise ValueError(f"Error en preprocesado: {resultado.get('error')}")

            self.mapeo_archivos[nodo_id] = ruta_salida
            self.archivos_generados.append(os.path.basename(ruta_salida))

            resultado_json = {}
            if ruta_salida.endswith(".json") and os.path.exists(ruta_salida):
                with open(ruta_salida, "r", encoding="utf-8") as f:
                    resultado_json = json.load(f)

            self.resultados[nodo_id] = {
                "tipo":            "preprocesado",
                "clave_score":     datos.get("clave_score"),
                "archivo_entrada": archivo_entrada,
                "archivo_salida":  ruta_salida,
                "algoritmo":       algoritmo_nombre,
                "resultado_json":  resultado_json,
                "log":             resultado.get("log"),
                "estado":          "exito",
            }
            return True
        except Exception as e:
            self.errores.append(f"Error en nodo PREPROCESADO {nodo_id}: {e}")
            return False

    def ejecutar_nodo_docking(self, nodo_id: str, nodo: Dict[str, Any]) -> bool:
        """Nodo de docking: ligando + receptor → poses SDF + JSON de energías."""
        try:
            datos            = nodo.get("data", {})
            ruta_script      = datos.get("algoritmo_ruta") or datos.get("algoritmo_nombre", "dockingSmina")
            if ruta_script.endswith(".py"):
                ruta_script = ruta_script[:-3]
            algoritmo_nombre = ruta_script

            _, archivo_ligando   = self.obtener_entrada_nodo(nodo_id, "input_ligando")
            _, archivo_receptor  = self.obtener_entrada_nodo(nodo_id, "input_receptor")

            if not archivo_ligando or not archivo_receptor:
                raise ValueError(f"Nodo {nodo_id}: se necesitan ligando y receptor")

            ruta_algoritmo = resolver_algoritmo(algoritmo_nombre, self.usuario_id)

            nombre_salida = f"docking_{nodo_id}{self.token}.sdf"
            ruta_salida   = os.path.join("uploads", nombre_salida)

            _, archivo_referencia = self.obtener_entrada_nodo(nodo_id, "input_referencia")

            flags = [
                "--exhaustiveness", str(datos.get("exhaustiveness", 8)),
                "--num_modes",      str(datos.get("num_modes", 5)),
                "--scoring",        datos.get("scoring", "vinardo"),
            ]

            modo_caja = datos.get("modo_caja", "auto")
            if modo_caja == "manual":
                for campo in ("center_x", "center_y", "center_z", "size_x", "size_y", "size_z"):
                    flags += [f"--{campo}", str(datos.get(campo, 0))]
            else:
                flags += ["--autobox_add", str(datos.get("autobox_add", 8))]
                if modo_caja == "referencia" and archivo_referencia:
                    flags += ["--referencia", archivo_referencia]

            resultado = ejecutar_algoritmo(
                ruta_algoritmo, archivo_ligando, archivo_receptor, ruta_salida, flags=flags
            )

            if not resultado.get("exito"):
                raise ValueError(f"Error en docking: {resultado.get('error')}")

            self.mapeo_archivos[nodo_id] = ruta_salida
            self.archivos_generados.append(os.path.basename(ruta_salida))

            # Leer JSON de energías generado por dockingSmina.py
            ruta_json = os.path.splitext(ruta_salida)[0] + "_energias.json"
            energias  = {}
            if os.path.exists(ruta_json):
                with open(ruta_json, "r", encoding="utf-8") as f:
                    energias = json.load(f)
                # Se anota como generado para que quede registrado con dueño y
                # como resultado PRIVADO, igual que las poses. Sin esto queda
                # en uploads/ sin constar en la tabla `archivos`, y lo que no
                # consta se trata como biblioteca compartida: las afinidades
                # de un cribado ajeno se podían descargar sabiendo el nombre,
                # que es deducible del id de la ejecución.
                self.archivos_generados.append(os.path.basename(ruta_json))

            self.resultados[nodo_id] = {
                "tipo":             "docking",
                "archivo_ligando":  archivo_ligando,
                "archivo_receptor": archivo_receptor,
                "archivo_poses":    ruta_salida,
                "energias":         energias,
                "log":              resultado.get("log"),
                "estado":           "exito",
            }
            return True
        except Exception as e:
            self.errores.append(f"Error en nodo DOCKING {nodo_id}: {e}")
            return False

    def ejecutar_nodo_descargar(self, nodo_id: str, nodo: Dict[str, Any]) -> bool:
        try:
            _, archivo_entrada = self.obtener_entrada_nodo(nodo_id, "input")
            if not archivo_entrada:
                raise ValueError(f"Nodo {nodo_id}: sin entrada")
            self.resultados[nodo_id] = {
                "tipo":    "descargar",
                "archivo": archivo_entrada,
                "estado":  "exito",
            }
            return True
        except Exception as e:
            self.errores.append(f"Error en nodo DESCARGAR {nodo_id}: {e}")
            return False

    def _ejecutar_nodo_select_mol(self, nodo_id: str, nodo: Dict[str, Any]) -> bool:
        """
        Nodo Seleccionar Molécula: recupera un archivo de la biblioteca local.
        El frontend guarda el nombre del archivo en data.nombre_archivo cuando
        el usuario elige una molécula del desplegable.
        """
        try:
            datos          = nodo.get("data", {})
            nombre_archivo = datos.get("nombre_archivo")

            if not nombre_archivo:
                raise ValueError(
                    "Seleccionar Molécula: no se ha elegido ninguna molécula. "
                    "Abre el nodo y selecciona una de la lista."
                )

            ruta = os.path.join("uploads", nombre_archivo)
            if not os.path.exists(ruta):
                raise ValueError(
                    f"El archivo '{nombre_archivo}' no se encuentra en el servidor. "
                    "Comprueba que sigue estando en uploads/."
                )

            self.mapeo_archivos[nodo_id] = ruta
            self.resultados[nodo_id] = {
                "tipo":    "selectMol",
                "archivo": ruta,
                "estado":  "exito",
            }
            return True
        except Exception as e:
            self.errores.append(f"Error en nodo SELECTMOL {nodo_id}: {e}")
            return False

    # ------------------------------------------------------------------
    # Dispatcher principal
    # ------------------------------------------------------------------

    def ejecutar_nodo(self, nodo_id: str) -> bool:
        try:
            nodo      = self.obtener_nodo_por_id(nodo_id)
            tipo_nodo = nodo.get("type", "default")

            # selectDB: proporciona un archivo SDF (base de datos) a los nodos siguientes
            if tipo_nodo == "selectDB":
                datos          = nodo.get("data", {})
                nombre_archivo = datos.get("nombre_archivo")
                if not nombre_archivo:
                    self.errores.append(f"Nodo {nodo_id}: no se ha seleccionado ninguna base de datos")
                    return False
                ruta = os.path.join("uploads", nombre_archivo)
                if not os.path.exists(ruta):
                    self.errores.append(f"Nodo {nodo_id}: el archivo '{nombre_archivo}' no existe en uploads/")
                    return False
                self.mapeo_archivos[nodo_id] = ruta
                self.resultados[nodo_id] = {"tipo": "selectDB", "archivo": ruta, "estado": "exito"}
                return True

            # selectMol proporciona un archivo de molécula de la biblioteca
            if tipo_nodo == "selectMol":
                return self._ejecutar_nodo_select_mol(nodo_id, nodo)

            if tipo_nodo == "upload":
                return self.ejecutar_nodo_upload(nodo_id, nodo)
            elif tipo_nodo in ("algoritmo", "alineacion"):
                return self.ejecutar_nodo_algoritmo(nodo_id, nodo)
            elif tipo_nodo == "comparacion":
                return self.ejecutar_nodo_comparacion(nodo_id, nodo)
            elif tipo_nodo == "preprocesado":
                return self.ejecutar_nodo_preprocesado(nodo_id, nodo)
            elif tipo_nodo == "docking":
                return self.ejecutar_nodo_docking(nodo_id, nodo)
            elif tipo_nodo == "descargar":
                return self.ejecutar_nodo_descargar(nodo_id, nodo)
            elif tipo_nodo == "ejecutar":
                self.resultados[nodo_id] = {"tipo": "ejecutar", "estado": "exito"}
                return True
            else:
                # Nodo sin tipo reconocido — se ignora sin detener el workflow
                if tipo_nodo:
                    self.errores.append(f"Nodo {nodo_id} ignorado: tipo desconocido '{tipo_nodo}'")
                self.resultados[nodo_id] = {"tipo": tipo_nodo, "estado": "ignorado"}
                return True

        except Exception as e:
            self.errores.append(f"Error ejecutando nodo {nodo_id}: {e}")
            return False

    # ------------------------------------------------------------------
    # Ejecución completa del workflow
    # ------------------------------------------------------------------

    def ejecutar(self) -> Dict[str, Any]:
        self.inicio = datetime.utcnow()
        try:
            orden = self.obtener_orden_ejecucion()
            for nodo_id in orden:
                self.ejecutar_nodo(nodo_id)

            self.fin      = datetime.utcnow()
            duracion      = (self.fin - self.inicio).total_seconds()
            estado_final  = "completado" if not self.errores else "error"

            return {
                "exito":              len(self.errores) == 0,
                "estado":             estado_final,
                "resultados":         self.resultados,
                "errores":            self.errores,
                "duracion_segundos":  duracion,
            }

        except Exception as e:
            self.fin     = datetime.utcnow()
            duracion     = (self.fin - self.inicio).total_seconds() if self.inicio else 0
            return {
                "exito":              False,
                "estado":             "error",
                "error_general":      str(e),
                "resultados":         self.resultados,
                "errores":            self.errores,
                "duracion_segundos":  duracion,
            }


# ---------------------------------------------------------------------------
# Batch executor: ejecuta el workflow sobre cada molécula de un SDF multi-mol
# ---------------------------------------------------------------------------

class BatchWorkflowExecutor:
    """
    Itera sobre todas las moléculas de un SDF (nodo selectDB) y ejecuta
    el workflow completo para cada una, devolviendo un ranking ordenado.
    """

    # Extensiones cuyo contenido cabe dentro del JSON consolidado y por tanto
    # no necesitan un fichero por molecula (ver _recoger_ficheros_por_molecula).
    EXTENSIONES_DE_DATOS = {".json", ".csv"}

    def __init__(self, workflow_json: Dict[str, Any], usuario_id: int,
                 ejecucion_id: int = None):
        self.workflow_json = workflow_json
        self.usuario_id    = usuario_id
        self.ejecucion_id  = ejecucion_id
        self.nodos         = workflow_json.get("nodes", [])

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------

    def _encontrar_nodo_bd(self):
        for nodo in self.nodos:
            if nodo.get("type") == "selectDB":
                return nodo
        return None

    @staticmethod
    def inventario_sdf(ruta_sdf: str) -> Tuple[List[int], int]:
        """
        (indices de las moleculas parseables, total de registros del fichero).

        Devuelve las DOS cifras porque no tienen por que coincidir y la
        diferencia importa: antes solo se contaban las parseables, asi que una
        biblioteca con registros defectuosos se cribaba a medias y el informe
        decia "4 moleculas procesadas, 0 errores, exito" sobre un fichero de
        10.000. Las bibliotecas comerciales (ZINC, Enamine) traen registros
        que RDKit rechaza con normalidad, asi que el caso no es raro: es el
        habitual en cuanto se sale de un fichero de pruebas.

        Se recorre sin escribir nada a disco. El reparto en bloques necesita
        saber cuantas hay antes de procesar ninguna, y materializar la
        biblioteca entera solo para contarla era justamente el problema que
        tenia el metodo anterior: un SDF de 100.000 compuestos creaba 100.000
        ficheros temporales de golpe en uploads/.
        """
        from rdkit import Chem

        from app.formatos import contar_moleculas_sdf

        supplier = Chem.SDMolSupplier(ruta_sdf, removeHs=False, sanitize=False)
        indices = [i for i, mol in enumerate(supplier) if mol is not None]

        # El total se cuenta por separadores ($$$$), no por lo que itere el
        # supplier. Ante un registro malformado RDKit salta al siguiente
        # separador y por el camino se come alguno, de modo que su recuento ya
        # viene mermado: sobre un fichero de 5 registros con 2 corruptos
        # iteraba 3, y el informe habria dicho "2 sin leer" en vez de 4.
        # Ademas es el mismo criterio con el que se conto `num_moleculas` al
        # subir la biblioteca, asi que el cribado y el listado de Moleculas
        # dicen la misma cifra.
        total = contar_moleculas_sdf(ruta_sdf)
        return indices, max(total, len(indices))

    @staticmethod
    def indices_validos(ruta_sdf: str) -> List[int]:
        """Solo los indices parseables. Ver inventario_sdf."""
        return BatchWorkflowExecutor.inventario_sdf(ruta_sdf)[0]

    def extraer_moleculas(self, ruta_sdf: str, indices: List[int]) -> List[Dict]:
        """
        Escribe a disco SOLO las moleculas pedidas, como ficheros temporales.

        Cada subtarea extrae su propio bloque, asi que en ningun momento hay
        mas ficheros temporales que los del bloque en curso.
        """
        from rdkit import Chem
        pedidos   = set(indices)
        # Los bloques son tramos contiguos de la lista de indices, asi que en
        # cuanto se pasa del ultimo que pide este bloque no queda nada por
        # encontrar. Sin este corte, CADA bloque recorria el fichero completo:
        # con una biblioteca de un millon repartida en bloques de mil, eran mil
        # pasadas enteras sobre varios GB, y el cribado se iba en releer en vez
        # de en calcular.
        ultimo     = max(pedidos) if pedidos else -1
        supplier   = Chem.SDMolSupplier(ruta_sdf, removeHs=False, sanitize=False)
        moleculas = []
        for i, mol in enumerate(supplier):
            if i > ultimo:
                break
            if i not in pedidos or mol is None:
                continue
            nombre_raw  = mol.GetProp("_Name").strip() if mol.HasProp("_Name") else ""
            nombre      = nombre_raw if nombre_raw else f"mol_{i + 1}"
            nombre_safe = re.sub(r"[^\w\-]", "_", nombre)[:40]
            # El id de ejecucion en el nombre evita que dos ejecuciones
            # concurrentes del mismo flujo se pisen los temporales.
            sufijo    = f"e{self.ejecucion_id}_" if self.ejecucion_id else ""
            ruta_temp = os.path.join("uploads", f"_btmp_{sufijo}{nombre_safe}_{i}.sdf")
            writer = Chem.SDWriter(ruta_temp)
            writer.write(mol)
            writer.close()
            moleculas.append({"nombre": nombre, "ruta": ruta_temp, "indice": i})
        return moleculas

    def _split_sdf(self, ruta_sdf: str) -> List[Dict]:
        """Compatibilidad: extrae todas las moleculas del SDF."""
        return self.extraer_moleculas(ruta_sdf, self.indices_validos(ruta_sdf))

    @staticmethod
    def _valor_por_ruta(datos, ruta):
        """
        Sigue una ruta tipo "moleculas.MW" dentro de un JSON.

        Entra en el primer elemento de una lista, porque varios algoritmos
        envuelven asi sus resultados: filtroLipinski devuelve
        {"moleculas": [{"MW": ...}]} y la puntuacion vive dentro.
        """
        actual = datos
        for tramo in (ruta or "").split("."):
            if isinstance(actual, list):
                actual = actual[0] if actual else None
            if not isinstance(actual, dict):
                return None
            actual = actual.get(tramo)
        if isinstance(actual, list):
            actual = actual[0] if actual else None
        return actual

    @staticmethod
    def _tipo_de_score(clave, tipo_nodo):
        """Etiqueta legible del score, para el encabezado del CSV de ranking."""
        c = (clave or "").lower().split(".")[-1]
        if "similitud" in c or "tanimoto" in c:
            return "similitud"
        if "rmsd" in c:
            return "rmsd"
        if "afinidad" in c:
            return "docking"
        if c in ("mw", "peso_molecular"):
            return "lipinski"
        return tipo_nodo or "score"

    @staticmethod
    def _como_score(valor) -> float:
        """
        Convierte un valor del JSON de un algoritmo en score, o None si no lo es.

        Existe porque comprobar que la clave está no basta: puede estar con
        valor null. dockingSmina.py escribe "mejor_afinidad": null cuando el
        docking se ejecuta correctamente pero no encuentra ninguna pose, y el
        float(None) que había antes lanzaba TypeError. En modo lote ese
        TypeError lo capturaba el except por molécula, así que la molécula se
        marcaba como fallida cuando en realidad el resultado legítimo era
        "sin afinidad": debe quedar sin puntuar y caer al final del ranking,
        no contarse como error de ejecución.

        Se descarta bool aparte porque en Python es subclase de int y
        float(True) daría 1.0, convirtiendo un "exito": true en un score.
        """
        if valor is None or isinstance(valor, bool):
            return None
        try:
            return float(valor)
        except (TypeError, ValueError):
            return None

    def _extraer_score(self, resultado_workflow: Dict) -> Tuple:
        """
        Extrae el score numérico principal del resultado de un workflow de molécula única.
        Devuelve (valor_float | None, tipo_str | None).
        """
        for nodo_res in resultado_workflow.get("resultados", {}).values():
            if not isinstance(nodo_res, dict):
                continue
            tipo = nodo_res.get("tipo")
            # "or {}" y no get(..., {}): si la clave existe con valor None
            # (nodo que falló antes de escribir su JSON), el "in" de abajo
            # reventaría con TypeError.
            rj   = nodo_res.get("resultado_json") or {}

            # En todas las ramas se usa _como_score y solo se devuelve si dio un
            # número: si un nodo trae la clave a null, se sigue buscando en los
            # demás nodos en vez de abortar la extracción entera.
            # Si el banco de pruebas anoto la clave al subir el algoritmo, se
            # usa esa y no hay nada que adivinar. Es lo que elimina de raiz la
            # familia de fallos que se repitio cuatro veces: "rmsd" frente a
            # "rmsd_angstroms", "MW" anidado bajo "moleculas", etc.
            declarada = nodo_res.get("clave_score")
            if declarada:
                score = self._como_score(self._valor_por_ruta(rj, declarada))
                if score is None and isinstance(nodo_res.get("energias"), dict):
                    score = self._como_score(
                        self._valor_por_ruta(nodo_res["energias"], declarada))
                if score is not None:
                    return score, self._tipo_de_score(declarada, tipo)

            if tipo == "comparacion":
                score = self._como_score(rj.get("similitud"))
                if score is not None:
                    return score, "similitud"
                # rmsdConformaciones.py escribe la clave "rmsd_angstroms", no
                # "rmsd": buscar solo "rmsd" hacía que el score saliera None
                # para TODAS las moléculas y el cribado por RMSD terminara
                # siempre en "error" con el ranking vacío. Se acepta también
                # "rmsd" por si un algoritmo de comparación propio la emite así.
                for clave in ("rmsd_angstroms", "rmsd"):
                    score = self._como_score(rj.get(clave))
                    if score is not None:
                        return score, "rmsd"

            elif tipo == "docking":
                energias = nodo_res.get("energias") or {}
                if isinstance(energias, dict):
                    score = self._como_score(energias.get("mejor_afinidad"))
                    if score is not None:
                        return score, "docking"

            elif tipo == "preprocesado":
                if not isinstance(rj, dict):
                    continue
                # filtroLipinski.py soporta bibliotecas multi-molécula, así que
                # anida las propiedades bajo "moleculas": [{...}] y en la raíz
                # solo deja el recuento (total/pass/fail). Buscar "MW" en la
                # raíz no encontraba nada nunca. En batch cada fichero temporal
                # tiene exactamente una molécula, así que el score es su MW.
                moleculas = rj.get("moleculas")
                if isinstance(moleculas, list) and moleculas and isinstance(moleculas[0], dict):
                    score = self._como_score(moleculas[0].get("MW"))
                    if score is not None:
                        return score, "lipinski"
                score = self._como_score(rj.get("MW"))
                if score is not None:
                    return score, "lipinski"

        return None, None

    def _generar_csv(self, ranking: List[Dict], nombre_bd: str, tipo_score: str) -> str:
        label_score = {
            "similitud": "Tanimoto (0-1, mayor mejor)",
            "rmsd":      "RMSD (Å, menor mejor)",
            "docking":   "Afinidad (kcal/mol, menor mejor)",
            "lipinski":  "Peso molecular (Da)",
        }.get(tipo_score or "", "Score")

        sufijo_ejecucion = f"_e{self.ejecucion_id}" if self.ejecucion_id else ""
        nombre_csv = (
            f"ranking_{os.path.splitext(nombre_bd)[0]}{sufijo_ejecucion}_"
            f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        ruta_csv = os.path.join("uploads", nombre_csv)
        with open(ruta_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Posición", "Nombre molécula", label_score, "Estado"])
            for r in ranking:
                writer.writerow([
                    r.get("posicion", "—"),
                    r["nombre"],
                    f"{r['score']:.4f}" if r.get("score") is not None else "—",
                    "OK" if r["exito"] else "ERROR",
                ])
        return nombre_csv

    # ------------------------------------------------------------------
    # Ejecución batch principal
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Piezas reutilizables por las subtareas Celery
    # ------------------------------------------------------------------

    def localizar_base_de_datos(self) -> Tuple[str, str]:
        """Devuelve (nombre, ruta) del SDF del nodo selectDB, o lanza ValueError."""
        nodo_bd = self._encontrar_nodo_bd()
        if not nodo_bd:
            raise ValueError("No hay nodo 'Seleccionar BD' en el workflow")
        nombre_archivo = nodo_bd.get("data", {}).get("nombre_archivo")
        if not nombre_archivo:
            raise ValueError("El nodo 'Seleccionar BD' no tiene base de datos seleccionada")
        ruta_sdf = os.path.join("uploads", nombre_archivo)
        if not os.path.exists(ruta_sdf):
            raise ValueError(f"Base de datos '{nombre_archivo}' no encontrada en uploads/")
        return nombre_archivo, ruta_sdf


    def _preparar_molecula(self, mol_info: Dict, nodo_bd_id: str):
        """
        El grafo de UNA molecula: el nodo de base de datos pasa a ser un
        selectMol que apunta a su fichero temporal.
        """
        workflow_mod = copy.deepcopy(self.workflow_json)
        for nodo in workflow_mod["nodes"]:
            if nodo["id"] == nodo_bd_id:
                nodo["type"] = "selectMol"
                nodo["data"]["nombre_archivo"] = os.path.basename(mol_info["ruta"])
                break

        # sufijo_extra: dentro de una misma ejecucion las N moleculas pasan por
        # los mismos nodos, asi que el id de ejecucion solo no basta para
        # distinguir sus salidas.
        return WorkflowExecutor(
            workflow_mod, self.usuario_id,
            ejecucion_id=self.ejecucion_id,
            sufijo_extra="m{}".format(mol_info["indice"]))

    def _resultado_molecula(self, mol_info: Dict, executor, resultado: Dict) -> Dict:
        score, tipo_score = self._extraer_score(resultado)
        return {
            "nombre":       mol_info["nombre"],
            "score":        score,
            "tipo_score":   tipo_score,
            "exito":        resultado.get("exito", False),
            "errores_nodo": resultado.get("errores", []),
            "archivos":     executor.archivos_generados,
            # Los numeros de cada nodo. Sin esto solo sobrevivia el score, y
            # el MW/LogP/HBD de un Lipinski o el Tanimoto de una comparacion
            # existian UNICAMENTE dentro del JSON por molecula: de ahi venia
            # tener un fichero por molecula para poder consultarlos.
            "detalle":      self._detalle_por_nodo(resultado),
        }

    @staticmethod
    def _clave_invocacion(invocacion) -> tuple:
        ruta, archivos, flags = invocacion
        return (ruta, tuple(archivos), tuple(flags))


    def _invocaciones_del_bloque(self, moleculas: List[Dict], nodo_bd_id: str):
        """
        Que invocacion de algoritmo pide cada molecula, recorriendo el grafo EN
        SECO: las llamadas se desvian y no se ejecuta nada.

        Devuelve None si alguna molecula no pide exactamente una. Con dos
        algoritmos encadenados no sirve ni el array ni el trozo: el segundo
        necesita la salida del primero, y aqui todo va a la vez.
        """
        invocaciones = []
        for mol_info in moleculas:
            anotadas = []

            def anotar(ruta, archivos, flags, _destino=anotadas):
                _destino.append((ruta, list(archivos), list(flags)))
                # Se finge exito para que el resto del grafo siga su curso: lo
                # que interesa de esta pasada es llegar al final, no el
                # resultado, que se tira.
                return {"exito": True, "log": "", "error": None}

            with desviar_invocaciones(anotar):
                self._preparar_molecula(mol_info, nodo_bd_id).ejecutar()

            if len(anotadas) != 1:
                return None
            invocaciones.append(anotadas[0])
        return invocaciones

    def _segunda_pasada(self, moleculas: List[Dict], nodo_bd_id: str,
                        calculado: Dict, on_molecula=None) -> List[Dict]:
        """
        Recorre el grafo de verdad, sirviendo desde `calculado` los algoritmos
        que ya se han ejecutado.

        Es lo que permite no reimplementar nada: el registro de ficheros, el
        score y el nodo de descarga son los de siempre, porque el grafo se
        ejecuta igual. Lo unico que cambia es de donde sale el resultado del
        algoritmo.
        """
        def servir(ruta, archivos, flags):
            # Un fallo de cuenta aqui no rompe nada: devolver None deja que esa
            # invocacion se ejecute por su cuenta, como antes.
            return calculado.get(self._clave_invocacion((ruta, archivos, flags)))

        resultados = []
        for mol_info in moleculas:
            try:
                executor = self._preparar_molecula(mol_info, nodo_bd_id)
                with desviar_invocaciones(servir):
                    resultado = executor.ejecutar()
                resultados.append(
                    self._resultado_molecula(mol_info, executor, resultado))
            except Exception as e:  # noqa: BLE001
                resultados.append({
                    "nombre":       mol_info["nombre"],
                    "score":        None,
                    "tipo_score":   None,
                    "exito":        False,
                    "errores_nodo": [str(e)],
                    "archivos":     [],
                })
            finally:
                if os.path.exists(mol_info["ruta"]):
                    os.remove(mol_info["ruta"])
                if on_molecula is not None:
                    on_molecula(mol_info["nombre"])

        return resultados

    # ------------------------------------------------------------------
    # Troceado: UN job para el bloque entero
    # ------------------------------------------------------------------

    def _plantilla_de_trozo(self, moleculas: List[Dict], invocaciones: List):
        """
        Si las N invocaciones solo se diferencian en la molecula de entrada y en
        el fichero de salida, devuelve con que llamar al algoritmo una sola vez.
        En cualquier otro caso, None.

        Se comprueba de verdad y no se da por supuesto porque las N van a
        compartir un unico job: si una referencia o una opcion cambiara de una
        molecula a otra, el trozo estaria calculando otra cosa. Y la salida
        tiene que ser un JSON: de un fichero de moleculas no se puede repartir
        por nombre lo que vuelve.
        """
        primera_ruta, primeros_archivos, primeros_flags = invocaciones[0]
        if len(primeros_archivos) < 2:
            return None
        if os.path.splitext(primeros_archivos[-1])[1].lower() != ".json":
            return None

        # La entrada que cambia es el temporal de la molecula.
        try:
            posicion = primeros_archivos.index(moleculas[0]["ruta"])
        except ValueError:
            return None
        if posicion == len(primeros_archivos) - 1:
            return None            # la molecula no puede ser la salida

        for mol_info, (ruta, archivos, flags) in zip(moleculas, invocaciones):
            if ruta != primera_ruta or list(flags) != list(primeros_flags):
                return None
            if len(archivos) != len(primeros_archivos):
                return None
            if archivos[posicion] != mol_info["ruta"]:
                return None
            # Todo lo que no sea la molecula ni la salida tiene que coincidir.
            for i, valor in enumerate(archivos[:-1]):
                if i != posicion and valor != primeros_archivos[i]:
                    return None

        return {
            "algoritmo":     primera_ruta,
            "archivos":      list(primeros_archivos),
            "flags":         list(primeros_flags),
            "pos_molecula":  posicion,
        }

    def _escribir_trozo(self, moleculas: List[Dict]) -> str:
        """Las N moleculas del bloque en un solo SDF."""
        sufijo = "e{}_".format(self.ejecucion_id) if self.ejecucion_id else ""
        ruta = os.path.join(
            "uploads", "_btrozo_{}{}.sdf".format(sufijo, moleculas[0]["indice"]))

        with open(ruta, "wb") as destino:
            for mol_info in moleculas:
                with open(mol_info["ruta"], "rb") as origen:
                    datos = origen.read()
                destino.write(datos)
                # El separador es lo que distingue un SDF de varias moleculas de
                # uno solo mal pegado. Si el fichero no lo trae, se pone: sin el,
                # RDKit lee el trozo entero como un unico registro roto.
                if not datos.rstrip().endswith(b"$$$$"):
                    destino.write(b"$$$$" + bytes([10]))
        return ruta

    def _repartir_salida_del_trozo(self, ruta_salida: str, moleculas: List[Dict]):
        """
        (resultados por molecula en su orden, salida completa del trozo), o None
        si lo que devolvio el algoritmo no se puede repartir.

        Aqui se comprueba lo unico que no se podia saber de antemano: si el
        algoritmo sabe tragar varias moleculas. Los que devuelven una lista en
        "moleculas" --el contrato que ya valida el banco de pruebas al aceptar
        un algoritmo-- si; uno que solo mire su primer argumento devolvera un
        resultado en vez de N, y entonces se vuelve por el camino de un job por
        molecula.
        """
        try:
            with open(ruta_salida, "r", encoding="utf-8") as f:
                datos = json.load(f)
        except (OSError, ValueError):
            return None

        if not isinstance(datos, dict):
            return None
        lista = datos.get("moleculas")
        if not isinstance(lista, list) or len(lista) != len(moleculas):
            return None

        # Emparejar por nombre cuando los nombres bastan para distinguirlas; si
        # no, por orden, que es el que sigue el algoritmo al recorrer el SDF.
        por_nombre = {}
        for entrada in lista:
            if isinstance(entrada, dict) and entrada.get("nombre") is not None:
                por_nombre.setdefault(entrada["nombre"], []).append(entrada)

        if (len(por_nombre) == len(moleculas)
                and all(len(v) == 1 for v in por_nombre.values())
                and all(m["nombre"] in por_nombre for m in moleculas)):
            return [por_nombre[m["nombre"]][0] for m in moleculas], datos

        return lista, datos

    @staticmethod
    def _escribir_salida_individual(ruta: str, datos_trozo: Dict, entrada: Dict) -> None:
        """
        La parte del trozo que le toca a una molecula, con la misma forma que
        tendria si se hubiera ejecutado sola.

        Se escribe para que la segunda pasada del grafo no note la diferencia:
        el nodo lee su fichero de salida como siempre y de ahi sale el score.
        """
        individual = {k: v for k, v in datos_trozo.items() if k != "moleculas"}
        individual["total"] = 1
        individual["moleculas"] = [entrada]
        if "pass" in datos_trozo or "fail" in datos_trozo:
            paso = str(entrada.get("estado", "")).upper() == "PASS"
            individual["pass"] = 1 if paso else 0
            individual["fail"] = 0 if paso else 1

        directorio = os.path.dirname(ruta)
        if directorio:
            os.makedirs(directorio, exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(individual, f, ensure_ascii=False)

    def _procesar_en_trozo(self, moleculas: List[Dict], nodo_bd_id: str,
                           on_molecula=None):
        """
        Manda el bloque entero como UN job: las N moleculas en un SDF y el
        algoritmo recorriendolo completo. Devuelve None si no se presta, y
        entonces se intenta un job por molecula.

        Es el mismo trabajo que hace una peticion suelta sobre una biblioteca, y
        de ahi viene la medida que lo justifica: 10.000 moleculas asi tardaron
        143 s contra el bullx, mientras que molecula a molecula son 10.000
        transferencias y 10.000 tareas. El coste no esta en el calculo, esta en
        el viaje.
        """
        if len(moleculas) < 2:
            return None

        invocaciones = self._invocaciones_del_bloque(moleculas, nodo_bd_id)
        if invocaciones is None:
            return None

        plantilla = self._plantilla_de_trozo(moleculas, invocaciones)
        if plantilla is None:
            return None

        ruta_trozo = None
        ruta_salida = None
        try:
            ruta_trozo = self._escribir_trozo(moleculas)
            sufijo = "e{}_".format(self.ejecucion_id) if self.ejecucion_id else ""
            ruta_salida = os.path.join(
                "uploads",
                "_btrozo_{}{}_salida.json".format(sufijo, moleculas[0]["indice"]))

            argumentos = list(plantilla["archivos"])
            argumentos[plantilla["pos_molecula"]] = ruta_trozo
            argumentos[-1] = ruta_salida

            resultado = ejecutar_algoritmo(plantilla["algoritmo"], *argumentos,
                                           flags=plantilla["flags"])
            if not resultado.get("exito"):
                return None

            reparto = self._repartir_salida_del_trozo(ruta_salida, moleculas)
            if reparto is None:
                return None
            entradas, datos_trozo = reparto

            # Cada molecula recibe su parte donde el grafo la espera.
            for invocacion, entrada in zip(invocaciones, entradas):
                self._escribir_salida_individual(
                    invocacion[1][-1], datos_trozo, entrada)

            log = resultado.get("log") or ""
            calculado = {self._clave_invocacion(inv): {"exito": True, "log": log,
                                                       "error": None}
                         for inv in invocaciones}
            return self._segunda_pasada(moleculas, nodo_bd_id, calculado, on_molecula)

        finally:
            for ruta in (ruta_trozo, ruta_salida):
                if ruta and os.path.exists(ruta):
                    os.remove(ruta)

    def _procesar_en_array(self, moleculas: List[Dict], nodo_bd_id: str,
                           on_molecula=None):
        """
        Despacha el bloque entero como UN job array, o devuelve None si este
        grafo no se presta y hay que ir molecula a molecula.

        Por que en dos pasadas y no reimplementando aqui lo que hace cada nodo:
        el grafo es el que sabe que algoritmo toca, con que ficheros y con que
        opciones --y eso cambia segun el tipo de nodo--. La primera pasada lo
        recorre EN SECO, con las llamadas al algoritmo desviadas, solo para
        anotar que pide cada molecula. La segunda lo recorre de verdad, con los
        resultados ya calculados servidos desde el desvio, de modo que el
        registro de ficheros, el score y el nodo de descarga siguen siendo los
        de siempre, sin una segunda copia que mantener.

        Solo se presta un grafo con EXACTAMENTE una invocacion por molecula. Si
        hay dos algoritmos encadenados, el segundo necesita la salida del
        primero y las tareas de un array corren a la vez: irian con la entrada
        sin escribir todavia.
        """
        if len(moleculas) < 2:
            return None

        invocaciones = self._invocaciones_del_bloque(moleculas, nodo_bd_id)
        if invocaciones is None:
            return None

        resultados_lote = ejecutar_algoritmos_en_lote(invocaciones)

        calculado = {self._clave_invocacion(inv): res
                     for inv, res in zip(invocaciones, resultados_lote)}

        return self._segunda_pasada(moleculas, nodo_bd_id, calculado, on_molecula)

    def procesar_bloque(self, indices: List[int], on_molecula=None,
                        debe_parar=None) -> List[Dict]:
        """
        Ejecuta el workflow sobre las moleculas de `indices` y devuelve una
        lista de resultados por molecula.

        Es la unidad de trabajo que ejecuta cada subtarea Celery. Se procesan
        de una en una dentro del bloque, pero los bloques corren en paralelo.

        `debe_parar` es un predicado que se consulta antes de cada molecula:
        permite abortar una ejecucion cancelada sin esperar a que termine el
        bloque entero.
        """
        nombre_bd, ruta_sdf = self.localizar_base_de_datos()
        nodo_bd_id = self._encontrar_nodo_bd()["id"]

        moleculas = self.extraer_moleculas(ruta_sdf, indices)

        # Tres caminos, del mas barato al mas caro, y cada uno devuelve None
        # cuando el grafo no se presta:
        #
        #   1. Un job para el bloque entero, con las N moleculas en un SDF.
        #      Pide que el algoritmo sepa recorrer varias.
        #   2. Un job array, una tarea por molecula. Una conexion y una
        #      espera, pero N transferencias.
        #   3. Molecula a molecula, que es como estaba.
        if debe_parar is None or not debe_parar():
            for camino in (self._procesar_en_trozo, self._procesar_en_array):
                resultados = camino(moleculas, nodo_bd_id, on_molecula=on_molecula)
                if resultados is not None:
                    return resultados

        resultados = []

        for mol_info in moleculas:
            if debe_parar is not None and debe_parar():
                # Limpiar los temporales que ya no se van a procesar.
                for pendiente in moleculas[len(resultados):]:
                    if os.path.exists(pendiente["ruta"]):
                        os.remove(pendiente["ruta"])
                break
            try:
                executor = self._preparar_molecula(mol_info, nodo_bd_id)
                resultado = executor.ejecutar()
                resultados.append(
                    self._resultado_molecula(mol_info, executor, resultado))
            except Exception as e:
                resultados.append({
                    "nombre":       mol_info["nombre"],
                    "score":        None,
                    "tipo_score":   None,
                    "exito":        False,
                    "errores_nodo": [str(e)],
                    "archivos":     [],
                })
            finally:
                if os.path.exists(mol_info["ruta"]):
                    os.remove(mol_info["ruta"])
                if on_molecula is not None:
                    on_molecula(mol_info["nombre"])

        return resultados


    @staticmethod
    def _detalle_por_nodo(resultado: Dict) -> Dict:
        """
        Lo que ha calculado cada nodo para esta molecula, sin los logs.

        Se toma `resultado_json` --y `energias` en el docking, que lo escribe
        aparte-- y no el nodo entero a proposito: ahi dentro tambien viaja la
        salida por consola del algoritmo, que multiplicada por las moleculas de
        una biblioteca es la diferencia entre un fichero manejable y uno que no
        se puede abrir.
        """
        detalle = {}
        for nodo_id, nodo_res in (resultado.get("resultados") or {}).items():
            if not isinstance(nodo_res, dict):
                continue
            datos = nodo_res.get("resultado_json") or {}
            if not datos and isinstance(nodo_res.get("energias"), dict):
                datos = nodo_res["energias"]
            if datos:
                detalle[nodo_id] = {"tipo": nodo_res.get("tipo"), "datos": datos}
        return detalle

    @classmethod
    def _recoger_ficheros_por_molecula(cls, nombres: List[str]) -> List[str]:
        """
        Borra los ficheros de datos de UNA molecula y devuelve los que quedan.

        Su contenido acaba de copiarse al JSON consolidado, asi que conservarlos
        es tener la misma cifra en dos sitios y, en una biblioteca de verdad,
        un fichero y una fila en `archivos` por molecula: diez mil moleculas
        eran diez mil de cada.

        Lo que lleva estructura --poses de un docking, una alineacion-- NO se
        borra: eso no cabe dentro de un JSON y es el resultado en si, no una
        forma de consultarlo.
        """
        supervivientes = []
        for nombre in nombres:
            if os.path.splitext(nombre)[1].lower() in cls.EXTENSIONES_DE_DATOS:
                ruta = os.path.join("uploads", nombre)
                if os.path.exists(ruta):
                    os.remove(ruta)
                continue
            supervivientes.append(nombre)
        return supervivientes

    def _generar_json_resultados(self, resumen: Dict, moleculas: List[Dict],
                                 nombre_bd: str) -> str:
        """
        El cribado entero en un fichero: el resumen y TODAS las moleculas con
        sus numeros, no solo las 25 del ranking que se guardan en la base de
        datos.
        """
        sufijo = "_e{}".format(self.ejecucion_id) if self.ejecucion_id else ""
        nombre = "resultados_{}{}_{}.json".format(
            os.path.splitext(nombre_bd)[0], sufijo,
            datetime.utcnow().strftime("%Y%m%d_%H%M%S"))

        with open(os.path.join("uploads", nombre), "w", encoding="utf-8") as f:
            json.dump({"resumen": resumen, "moleculas": moleculas}, f,
                      ensure_ascii=False, indent=2)
        return nombre

    def consolidar(self, resultados: List[Dict], nombre_bd: str,
                   total_moleculas: int, duracion: float) -> Dict[str, Any]:
        """
        Ordena los resultados de todos los bloques, genera el CSV y arma el
        resumen. Es el callback del chord: se ejecuta una sola vez, cuando
        todas las subtareas han terminado.
        """
        tipo_score_global = next(
            (r["tipo_score"] for r in resultados if r.get("tipo_score")), None)

        validos   = [r for r in resultados if r["exito"] and r["score"] is not None]
        invalidos = [r for r in resultados if not r["exito"] or r["score"] is None]

        # similitud -> mayor es mejor; rmsd y afinidad -> menor es mejor
        invertir = tipo_score_global == "similitud"
        validos.sort(key=lambda x: x["score"], reverse=invertir)

        for pos, r in enumerate(validos, 1):
            r["posicion"] = pos
        for r in invalidos:
            r["posicion"] = None

        ranking  = validos + invalidos
        ruta_csv = self._generar_csv(ranking, nombre_bd, tipo_score_global)

        # El resultado del cribado es UN fichero, no uno por molecula: los de
        # datos se borran una vez su contenido esta en el JSON consolidado.
        for molecula in ranking:
            molecula["archivos"] = self._recoger_ficheros_por_molecula(
                molecula.get("archivos") or [])

        resumen = {
            "modo":             "batch",
            "estado":           "completado" if validos else "error",
            "exito":            len(validos) > 0,
            "total_moleculas":  total_moleculas,
            "total_exito":      len(validos),
            "total_error":      len(invalidos),
            "tipo_score":       tipo_score_global,
            "base_de_datos":    nombre_bd,
            "duracion_segundos": duracion,
        }
        nombre_json = self._generar_json_resultados(resumen, ranking, nombre_bd)

        return dict(resumen,
                    ranking=ranking,
                    csv_ranking=ruta_csv,
                    json_resultados=nombre_json)

    def ejecutar_batch(self, on_progreso=None) -> Dict[str, Any]:
        inicio = datetime.utcnow()

        nodo_bd = self._encontrar_nodo_bd()
        if not nodo_bd:
            raise ValueError("No hay nodo 'Seleccionar BD' en el workflow")

        nombre_archivo = nodo_bd.get("data", {}).get("nombre_archivo")
        if not nombre_archivo:
            raise ValueError("El nodo 'Seleccionar BD' no tiene base de datos seleccionada")

        ruta_sdf = os.path.join("uploads", nombre_archivo)
        if not os.path.exists(ruta_sdf):
            raise ValueError(f"Base de datos '{nombre_archivo}' no encontrada en uploads/")

        moleculas = self._split_sdf(ruta_sdf)
        if not moleculas:
            raise ValueError("La base de datos no contiene moléculas válidas")

        nodo_bd_id          = nodo_bd["id"]
        resultados_batch    = []
        tipo_score_global   = None

        for i, mol_info in enumerate(moleculas):
            if on_progreso:
                on_progreso(i + 1, len(moleculas), mol_info["nombre"])

            try:
                # Reemplazar selectDB → selectMol apuntando al archivo temporal
                workflow_mod = copy.deepcopy(self.workflow_json)
                for nodo in workflow_mod["nodes"]:
                    if nodo["id"] == nodo_bd_id:
                        nodo["type"] = "selectMol"
                        nodo["data"]["nombre_archivo"] = os.path.basename(mol_info["ruta"])
                        break

                # sufijo_extra: dentro de una misma ejecucion las N moleculas
                # pasan por los mismos nodos, asi que el id de ejecucion solo
                # no basta para distinguir sus salidas.
                executor  = WorkflowExecutor(
                    workflow_mod, self.usuario_id,
                    ejecucion_id=self.ejecucion_id,
                    sufijo_extra=f"m{mol_info['indice']}")
                resultado = executor.ejecutar()

                score, tipo_score = self._extraer_score(resultado)
                if tipo_score and not tipo_score_global:
                    tipo_score_global = tipo_score

                resultados_batch.append({
                    "nombre":       mol_info["nombre"],
                    "score":        score,
                    "exito":        resultado.get("exito", False),
                    "errores_nodo": resultado.get("errores", []),
                })

            except Exception as e:
                resultados_batch.append({
                    "nombre":       mol_info["nombre"],
                    "score":        None,
                    "exito":        False,
                    "errores_nodo": [str(e)],
                })
            finally:
                if os.path.exists(mol_info["ruta"]):
                    os.remove(mol_info["ruta"])

        # Ordenar: similitud → mayor es mejor; rmsd/docking → menor es mejor
        validos   = [r for r in resultados_batch if r["exito"] and r["score"] is not None]
        invalidos = [r for r in resultados_batch if not r["exito"] or r["score"] is None]

        invertir = tipo_score_global == "similitud"
        validos.sort(key=lambda x: x["score"], reverse=invertir)

        for pos, r in enumerate(validos, 1):
            r["posicion"] = pos
        for r in invalidos:
            r["posicion"] = None

        ranking  = validos + invalidos
        ruta_csv = self._generar_csv(ranking, nombre_archivo, tipo_score_global)

        duracion = (datetime.utcnow() - inicio).total_seconds()
        return {
            "modo":             "batch",
            "estado":           "completado" if validos else "error",
            "exito":            len(validos) > 0,
            "total_moleculas":  len(moleculas),
            "total_exito":      len(validos),
            "total_error":      len(invalidos),
            "tipo_score":       tipo_score_global,
            "ranking":          ranking,
            "csv_ranking":      ruta_csv,
            "base_de_datos":    nombre_archivo,
            "duracion_segundos": duracion,
        }
