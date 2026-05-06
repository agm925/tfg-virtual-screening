"""
Motor de ejecución de Workflows KNIME
Parsea la estructura de nodos y conexiones, ejecuta secuencialmente los algoritmos
"""

import json
import os
import sys
from typing import Dict, List, Any, Tuple
from datetime import datetime
import time
from app.ejecutor import ejecutar_algoritmo


class WorkflowExecutor:
    """Ejecuta workflows compilando el grafo y ejecutando nodos en orden"""
    
    def __init__(self, workflow_json: Dict[str, Any], usuario_id: int):
        self.workflow_json = workflow_json
        self.usuario_id = usuario_id
        self.nodos = workflow_json.get("nodes", [])
        self.conexiones = workflow_json.get("edges", [])
        self.resultados = {}
        self.mapeo_archivos = {}  # { nodo_id: ruta_archivo }
        self.errores = []
        self.inicio = None
        self.fin = None
    
    def obtener_orden_ejecucion(self) -> List[str]:
        """
        Obtiene el orden topológico de nodos basado en las conexiones.
        Retorna lista de IDs de nodos en orden de ejecución.
        """
        # Construir grafo de dependencias
        grafo = {nodo["id"]: [] for nodo in self.nodos}
        in_degree = {nodo["id"]: 0 for nodo in self.nodos}
        
        for conexion in self.conexiones:
            nodo_origen = conexion.get("source") or conexion.get("nodo_origen")
            nodo_destino = conexion.get("target") or conexion.get("nodo_destino")
            
            if nodo_origen and nodo_destino:
                grafo[nodo_origen].append(nodo_destino)
                in_degree[nodo_destino] += 1
        
        # Kahn's algorithm para topological sort
        cola = [nodo_id for nodo_id in in_degree if in_degree[nodo_id] == 0]
        orden = []
        
        while cola:
            nodo_actual = cola.pop(0)
            orden.append(nodo_actual)
            
            for vecino in grafo[nodo_actual]:
                in_degree[vecino] -= 1
                if in_degree[vecino] == 0:
                    cola.append(vecino)
        
        if len(orden) != len(self.nodos):
            raise ValueError("Workflow contiene ciclos o nodos desconectados")
        
        return orden
    
    def obtener_nodo_por_id(self, nodo_id: str) -> Dict[str, Any]:
        """Obtiene la definición de un nodo por su ID"""
        for nodo in self.nodos:
            if nodo["id"] == nodo_id:
                return nodo
        raise ValueError(f"Nodo {nodo_id} no encontrado en workflow")
    
    def obtener_entrada_nodo(self, nodo_id: str, puerto: str = "input") -> Tuple[str, str]:
        """
        Obtiene el nodo y puerto que alimenta la entrada de un nodo.
        Retorna (nodo_origen_id, archivo_resultado)
        """
        for conexion in self.conexiones:
            nodo_destino = conexion.get("target") or conexion.get("nodo_destino")
            puerto_destino = conexion.get("targetHandle") or conexion.get("puerto_destino", "input")
            
            if nodo_destino == nodo_id and puerto_destino == puerto:
                nodo_origen = conexion.get("source") or conexion.get("nodo_origen")
                return nodo_origen, self.mapeo_archivos.get(nodo_origen)
        
        return None, None
    
    def ejecutar_nodo_upload(self, nodo_id: str, nodo: Dict[str, Any]) -> bool:
        """Procesa nodo de tipo UPLOAD (ya tiene archivo cargado)"""
        try:
            datos = nodo.get("data", {})
            archivo_id = datos.get("archivo_id")
            nombre_archivo = datos.get("nombre_archivo")
            
            if not nombre_archivo:
                raise ValueError(f"Nodo {nodo_id} sin nombre_archivo especificado")
            
            ruta_archivo = os.path.join("uploads", nombre_archivo)
            
            if not os.path.exists(ruta_archivo):
                raise ValueError(f"Archivo no encontrado: {ruta_archivo}")
            
            self.mapeo_archivos[nodo_id] = ruta_archivo
            self.resultados[nodo_id] = {
                "tipo": "upload",
                "archivo": ruta_archivo,
                "estado": "exito"
            }
            
            return True
        except Exception as e:
            self.errores.append(f"Error en nodo UPLOAD {nodo_id}: {str(e)}")
            return False
    
    def ejecutar_nodo_algoritmo(self, nodo_id: str, nodo: Dict[str, Any]) -> bool:
        """Ejecuta nodo tipo ALGORITMO (aplica algoritmo a entrada)"""
        try:
            datos = nodo.get("data", {})
            algoritmo_id = datos.get("algoritmo_id")
            algoritmo_nombre = datos.get("algoritmo_nombre", "centerMol")
            
            # Obtener archivo de entrada
            nodo_entrada, archivo_entrada = self.obtener_entrada_nodo(nodo_id, "input_molecula")
            
            if not archivo_entrada:
                raise ValueError(f"Nodo {nodo_id} sin entrada de molécula")
            
            # Ruta del algoritmo
            ruta_algoritmo = os.path.join("algoritmos", f"{algoritmo_nombre}.py")
            
            if not os.path.exists(ruta_algoritmo):
                raise ValueError(f"Algoritmo no encontrado: {ruta_algoritmo}")
            
            # Generar ruta de salida
            nombre_entrada = os.path.basename(archivo_entrada)
            nombre_salida = nombre_entrada.replace(".mol2", f"_processed_{nodo_id}.mol2")
            ruta_salida = os.path.join("uploads", nombre_salida)
            
            # Ejecutar algoritmo
            resultado = ejecutar_algoritmo(ruta_algoritmo, archivo_entrada, ruta_salida)
            
            if not resultado.get("exito"):
                raise ValueError(f"Error ejecutando algoritmo: {resultado.get('error')}")
            
            self.mapeo_archivos[nodo_id] = ruta_salida
            self.resultados[nodo_id] = {
                "tipo": "algoritmo",
                "archivo_entrada": archivo_entrada,
                "archivo_salida": ruta_salida,
                "algoritmo": algoritmo_nombre,
                "log": resultado.get("log"),
                "estado": "exito"
            }
            
            return True
        except Exception as e:
            self.errores.append(f"Error en nodo ALGORITMO {nodo_id}: {str(e)}")
            return False
    
    def ejecutar_nodo_comparacion(self, nodo_id: str, nodo: Dict[str, Any]) -> bool:
        """Ejecuta nodo tipo COMPARACION (compara dos moléculas)"""
        try:
            datos = nodo.get("data", {})
            
            # Obtener dos entradas
            nodo_entrada1, archivo_entrada1 = self.obtener_entrada_nodo(nodo_id, "input_mol1")
            nodo_entrada2, archivo_entrada2 = self.obtener_entrada_nodo(nodo_id, "input_mol2")
            
            if not archivo_entrada1 or not archivo_entrada2:
                raise ValueError(f"Nodo COMPARACION {nodo_id} sin ambas moléculas de entrada")
            
            # Ejecutar algoritmo Tanimoto
            ruta_algoritmo = os.path.join("algoritmos", "similaridadTanimoto.py")
            
            if not os.path.exists(ruta_algoritmo):
                raise ValueError(f"Algoritmo Tanimoto no encontrado: {ruta_algoritmo}")
            
            # Archivo de salida JSON
            nombre_salida = f"comparacion_{nodo_id}.json"
            ruta_salida = os.path.join("uploads", nombre_salida)
            
            resultado = ejecutar_algoritmo(ruta_algoritmo, archivo_entrada1, archivo_entrada2, ruta_salida)
            
            if not resultado.get("exito"):
                raise ValueError(f"Error ejecutando Tanimoto: {resultado.get('error')}")
            
            # Leer resultado JSON
            with open(ruta_salida, 'r') as f:
                resultado_comparacion = json.load(f)
            
            self.mapeo_archivos[nodo_id] = ruta_salida
            self.resultados[nodo_id] = {
                "tipo": "comparacion",
                "archivo_mol1": archivo_entrada1,
                "archivo_mol2": archivo_entrada2,
                "similitud": resultado_comparacion.get("similitud"),
                "resultado_json": resultado_comparacion,
                "estado": "exito"
            }
            
            return True
        except Exception as e:
            self.errores.append(f"Error en nodo COMPARACION {nodo_id}: {str(e)}")
            return False
    
    def ejecutar_nodo_descargar(self, nodo_id: str, nodo: Dict[str, Any]) -> bool:
        """Nodo DESCARGAR - marca archivo como listo para descargar"""
        try:
            nodo_entrada, archivo_entrada = self.obtener_entrada_nodo(nodo_id, "input")
            
            if not archivo_entrada:
                raise ValueError(f"Nodo DESCARGAR {nodo_id} sin entrada")
            
            self.resultados[nodo_id] = {
                "tipo": "descargar",
                "archivo": archivo_entrada,
                "estado": "exito"
            }
            
            return True
        except Exception as e:
            self.errores.append(f"Error en nodo DESCARGAR {nodo_id}: {str(e)}")
            return False
    
    def ejecutar_nodo(self, nodo_id: str) -> bool:
        """Ejecuta un nodo individual según su tipo"""
        try:
            nodo = self.obtener_nodo_por_id(nodo_id)
            tipo_nodo = nodo.get("type", "default")
            
            # Saltar nodos visuales sin lógica
            if tipo_nodo == "selectDB" or tipo_nodo == "selectMol":
                self.resultados[nodo_id] = {"tipo": tipo_nodo, "estado": "exito"}
                return True
            
            if tipo_nodo == "upload":
                return self.ejecutar_nodo_upload(nodo_id, nodo)
            elif tipo_nodo == "algoritmo":
                return self.ejecutar_nodo_algoritmo(nodo_id, nodo)
            elif tipo_nodo == "comparacion":
                return self.ejecutar_nodo_comparacion(nodo_id, nodo)
            elif tipo_nodo == "descargar":
                return self.ejecutar_nodo_descargar(nodo_id, nodo)
            elif tipo_nodo == "ejecutar":
                # Nodo ejecutar solo marca que completó
                self.resultados[nodo_id] = {"tipo": "ejecutar", "estado": "exito"}
                return True
            else:
                raise ValueError(f"Tipo de nodo desconocido: {tipo_nodo}")
        
        except Exception as e:
            self.errores.append(f"Error ejecutando nodo {nodo_id}: {str(e)}")
            return False
    
    def ejecutar(self) -> Dict[str, Any]:
        """Ejecuta el workflow completo"""
        self.inicio = datetime.utcnow()
        
        try:
            # Obtener orden de ejecución
            orden = self.obtener_orden_ejecucion()
            
            # Ejecutar cada nodo en orden
            for nodo_id in orden:
                exito = self.ejecutar_nodo(nodo_id)
                if not exito:
                    # Continuar con otros nodos, recolectar todos los errores
                    pass
            
            # Recopilar resultados finales
            self.fin = datetime.utcnow()
            duracion = (self.fin - self.inicio).total_seconds()
            
            estado_final = "completado" if not self.errores else "error"
            
            return {
                "exito": len(self.errores) == 0,
                "estado": estado_final,
                "resultados": self.resultados,
                "errores": self.errores,
                "duracion_segundos": duracion
            }
        
        except Exception as e:
            self.fin = datetime.utcnow()
            duracion = (self.fin - self.inicio).total_seconds()
            
            return {
                "exito": False,
                "estado": "error",
                "error_general": str(e),
                "resultados": self.resultados,
                "errores": self.errores,
                "duracion_segundos": duracion
            }
