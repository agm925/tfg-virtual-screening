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
from app.ejecutor import ejecutar_algoritmo


class WorkflowExecutor:
    """Ejecuta workflows compilando el grafo y ejecutando nodos en orden topológico."""

    def __init__(self, workflow_json: Dict[str, Any], usuario_id: int):
        self.workflow_json = workflow_json
        self.usuario_id    = usuario_id
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

            ruta_algoritmo = os.path.join("algoritmos", f"{algoritmo_nombre}.py")
            if not os.path.exists(ruta_algoritmo):
                raise ValueError(f"Algoritmo no encontrado: {ruta_algoritmo}")

            base, ext  = os.path.splitext(os.path.basename(archivo_entrada))
            # alinear3D y alinearMCS siempre fuerzan la salida a .sdf internamente
            # (ver alinear3D.alinear_o3a / alinearMCS.alinear_mcs), así que aquí debemos
            # anticipar esa coerción para que mapeo_archivos no apunte a un archivo
            # con extensión .mol2 que en realidad nunca se escribió.
            if algoritmo_nombre in ("alinear3D", "alinearMCS"):
                ext_salida = ".sdf"
            else:
                ext_salida = ext if ext in (".mol2", ".sdf") else ".sdf"
            nombre_salida = f"{base}_alineado_{nodo_id}{ext_salida}"
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

            ruta_algoritmo = os.path.join("algoritmos", f"{ruta_script}.py")
            if not os.path.exists(ruta_algoritmo):
                raise ValueError(f"Algoritmo no encontrado: {ruta_algoritmo}")

            # Los algoritmos de comparación que producen molécula (alinear3D, alinearMCS)
            # usan extensión .sdf; los de métricas (tanimoto, rmsd) usan .json
            nombre_base = ruta_script.lower()
            if any(k in nombre_base for k in ("alinear", "align")):
                nombre_salida = f"comparacion_{nodo_id}.sdf"
            else:
                nombre_salida = f"comparacion_{nodo_id}.json"
            ruta_salida = os.path.join("uploads", nombre_salida)

            resultado = ejecutar_algoritmo(ruta_algoritmo, archivo_mol1, archivo_mol2, ruta_salida)

            if not resultado.get("exito"):
                raise ValueError(f"Error ejecutando comparación: {resultado.get('error')}")

            self.mapeo_archivos[nodo_id] = ruta_salida

            # Si la salida es JSON la leemos para mostrársela al usuario
            resultado_comparacion = {}
            if ruta_salida.endswith(".json") and os.path.exists(ruta_salida):
                with open(ruta_salida, "r", encoding="utf-8") as f:
                    resultado_comparacion = json.load(f)

            self.resultados[nodo_id] = {
                "tipo":           "comparacion",
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

            ruta_algoritmo = os.path.join("algoritmos", f"{algoritmo_nombre}.py")
            if not os.path.exists(ruta_algoritmo):
                raise ValueError(f"Algoritmo no encontrado: {ruta_algoritmo}")

            # filtroLipinski produce JSON; filtroObabel filtra y devuelve molécula; el resto produce molécula
            nombre_base = algoritmo_nombre.lower()
            if "lipinski" in nombre_base:
                nombre_salida = f"{os.path.splitext(os.path.basename(archivo_entrada))[0]}_lipinski_{nodo_id}.json"
            else:
                base, ext  = os.path.splitext(os.path.basename(archivo_entrada))
                formato_pedido = datos.get("formato_salida")
                if "preparacionobabel" in nombre_base and formato_pedido and formato_pedido != "mismo":
                    ext_salida = f".{formato_pedido}"
                else:
                    ext_salida = ext if ext in (".mol2", ".sdf") else ".sdf"
                sufijo = "filtrado" if "filtro" in nombre_base else "prep"
                nombre_salida = f"{base}_{sufijo}_{nodo_id}{ext_salida}"
            ruta_salida = os.path.join("uploads", nombre_salida)

            if "filtro" in nombre_base and "lipinski" not in nombre_base:
                expresion_filtro = datos.get("filtro_expresion") or "MW>200"
                resultado = ejecutar_algoritmo(ruta_algoritmo, archivo_entrada, ruta_salida, expresion_filtro)
            elif "preparacionobabel" in nombre_base:
                flags = []
                if datos.get("sin_h"):
                    flags.append("--sin-h")
                if datos.get("sin_3d"):
                    flags.append("--sin-3d")
                if datos.get("sin_center"):
                    flags.append("--sin-center")
                resultado = ejecutar_algoritmo(ruta_algoritmo, archivo_entrada, ruta_salida, *flags)
            else:
                resultado = ejecutar_algoritmo(ruta_algoritmo, archivo_entrada, ruta_salida)

            if not resultado.get("exito"):
                raise ValueError(f"Error en preprocesado: {resultado.get('error')}")

            self.mapeo_archivos[nodo_id] = ruta_salida

            resultado_json = {}
            if ruta_salida.endswith(".json") and os.path.exists(ruta_salida):
                with open(ruta_salida, "r", encoding="utf-8") as f:
                    resultado_json = json.load(f)

            self.resultados[nodo_id] = {
                "tipo":            "preprocesado",
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

            ruta_algoritmo = os.path.join("algoritmos", f"{algoritmo_nombre}.py")
            if not os.path.exists(ruta_algoritmo):
                raise ValueError(f"Algoritmo no encontrado: {ruta_algoritmo}")

            nombre_salida = f"docking_{nodo_id}.sdf"
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
                ruta_algoritmo, archivo_ligando, archivo_receptor, ruta_salida, *flags
            )

            if not resultado.get("exito"):
                raise ValueError(f"Error en docking: {resultado.get('error')}")

            self.mapeo_archivos[nodo_id] = ruta_salida

            # Leer JSON de energías generado por dockingSmina.py
            ruta_json = os.path.splitext(ruta_salida)[0] + "_energias.json"
            energias  = {}
            if os.path.exists(ruta_json):
                with open(ruta_json, "r", encoding="utf-8") as f:
                    energias = json.load(f)

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

    def __init__(self, workflow_json: Dict[str, Any], usuario_id: int):
        self.workflow_json = workflow_json
        self.usuario_id    = usuario_id
        self.nodos         = workflow_json.get("nodes", [])

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------

    def _encontrar_nodo_bd(self):
        for nodo in self.nodos:
            if nodo.get("type") == "selectDB":
                return nodo
        return None

    def _split_sdf(self, ruta_sdf: str) -> List[Dict]:
        """Divide un SDF multi-molécula en archivos temporales individuales."""
        from rdkit import Chem
        supplier  = Chem.SDMolSupplier(ruta_sdf, removeHs=False, sanitize=False)
        moleculas = []
        for i, mol in enumerate(supplier):
            if mol is None:
                continue
            nombre_raw  = mol.GetProp("_Name").strip() if mol.HasProp("_Name") else ""
            nombre      = nombre_raw if nombre_raw else f"mol_{i + 1}"
            nombre_safe = re.sub(r"[^\w\-]", "_", nombre)[:40]
            ruta_temp   = os.path.join("uploads", f"_btmp_{nombre_safe}_{i}.sdf")
            writer = Chem.SDWriter(ruta_temp)
            writer.write(mol)
            writer.close()
            moleculas.append({"nombre": nombre, "ruta": ruta_temp, "indice": i})
        return moleculas

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

        nombre_csv = (
            f"ranking_{os.path.splitext(nombre_bd)[0]}_"
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

                executor  = WorkflowExecutor(workflow_mod, self.usuario_id)
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
