from pydantic import BaseModel
from typing import List, Optional, Dict, Any

# 1. Lo que el usuario nos envía desde la web
class UsuarioRegistro(BaseModel):
    email: str
    nombre: str
    password_hash: str

# 2. Lo que nosotros le devolvemos tras crearlo en la Base de Datos
class UsuarioRespuesta(BaseModel):
    id: int
    email: str
    rol: str

    # Esta configuración permite a Pydantic "leer" el modelo de SQLAlchemy
    class Config:
        from_attributes = True

class AlgoritmoRespuesta(BaseModel):
    id: int
    nombre: str
    descripcion: str
    ruta_mol_resultado: str
    es_publico: bool
    autor_id: int

    class Config:
        from_attributes = True

class PeticionRespuesta(BaseModel):
    id: int
    estado: str
    ruta_mol_original: str
    usuario_id: int
    algoritmo_id: int

    class Config:
        from_attributes = True

class UsuarioLogin(BaseModel):
    email: str
    password_hash: str

# Añade esto al final de app/schemas.py
class AlgoritmoCreate(BaseModel):
    nombre: str
    descripcion: str

# --- ESQUEMAS PARA WORKFLOWS ---

class NodoWorkflow(BaseModel):
    """Representación de un nodo en el workflow"""
    id: str  # ej: "upload_1", "algoritmo_1"
    tipo: str  # ej: "upload", "algoritmo", "comparacion", "ejecutar", "descargar"
    posicion: Dict[str, float]  # { x: 100, y: 50 }
    datos: Dict[str, Any]  # { nombre: "centerMol", archivo_id: 1, ... }


class ConexionWorkflow(BaseModel):
    """Representación de una conexión entre nodos"""
    nodo_origen: str
    puerto_origen: str  # ej: "output"
    nodo_destino: str
    puerto_destino: str  # ej: "input_molecula"


class GrafoWorkflow(BaseModel):
    """Estructura completa del workflow"""
    nodos: List[NodoWorkflow]
    conexiones: List[ConexionWorkflow]


class WorkflowCreate(BaseModel):
    """Crear nuevo workflow"""
    nombre: str
    descripcion: Optional[str] = None
    grafo_json: Dict[str, Any]  # { nodos: [...], edges: [...] }


class WorkflowRespuesta(BaseModel):
    """Respuesta de workflow desde BD"""
    id: int
    nombre: str
    descripcion: Optional[str]
    grafo_json: Dict[str, Any]
    usuario_id: int
    estado: str
    fecha_creacion: str
    fecha_actualizacion: str

    class Config:
        from_attributes = True


class WorkflowExecutionRespuesta(BaseModel):
    """Respuesta de ejecución de workflow"""
    id: int
    workflow_id: int
    usuario_id: int
    estado: str
    resultados_json: Optional[Dict[str, Any]]
    fecha_ejecucion: str
    duracion_segundos: Optional[int]

    class Config:
        from_attributes = True
