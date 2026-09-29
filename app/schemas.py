from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

# 1. Lo que el usuario nos envía desde la web
#
# Validacion real (antes: email/password_hash eran "str" sin mas, asi que
# "no-es-un-email" o una contraseña vacia pasaban el esquema y solo fallaban
# --si fallaban-- mas adelante, con errores menos claros). EmailStr exige un
# formato de correo valido: rechaza el registro con 422 antes de que la
# peticion llegue a tocar la base de datos.
class UsuarioRegistro(BaseModel):
    email: EmailStr
    nombre: str = Field(min_length=1, max_length=120)
    password_hash: str = Field(min_length=8, max_length=128)  # contraseña en texto plano (ver Seccion 2.7.1 de la memoria)

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
    tipo: str  # "alineacion", "comparacion", "preprocesado" o "docking"
    ruta_archivo: str
    es_publico: bool
    autor_id: int
    # Lo que observo el banco de pruebas al subirlo (ver app/banco_pruebas.py).
    formato_salida: Optional[str] = None
    clave_score: Optional[str] = None
    verificado: bool = False
    # Un algoritmo desactivado desaparece del catalogo y no puede ejecutarse,
    # pero su fila --y el historial de peticiones que lo usaron-- se conserva.
    activo: bool = True

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
    email: EmailStr
    password_hash: str = Field(min_length=1, max_length=128)  # min_length=1: no bloquear el rate limit con un 422 antes de contar el intento


class UsuarioSesion(BaseModel):
    id: int
    nombre: str
    email: str
    rol: str


class TokenRespuesta(BaseModel):
    """Respuesta de POST /login: JWT firmado + datos basicos del usuario."""
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioSesion

# Añade esto al final de app/schemas.py
class AlgoritmoCreate(BaseModel):
    nombre: str
    descripcion: str
    tipo: str  # "alineacion" o "comparacion"

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
    nombre: str = Field(min_length=1, max_length=200)
    descripcion: Optional[str] = Field(default=None, max_length=2000)
    grafo_json: Dict[str, Any]  # { nodos: [...], edges: [...] }


class WorkflowRespuesta(BaseModel):
    """Respuesta de workflow desde BD"""
    id: int
    nombre: str
    descripcion: Optional[str]
    grafo_json: Dict[str, Any]
    usuario_id: int
    estado: str
    fecha_creacion: datetime
    fecha_actualizacion: datetime

    class Config:
        from_attributes = True


class WorkflowExecutionRespuesta(BaseModel):
    """Respuesta de ejecución de workflow"""
    id: int
    workflow_id: int
    usuario_id: int
    estado: str
    resultados_json: Optional[Dict[str, Any]]
    fecha_ejecucion: datetime
    duracion_segundos: Optional[int]

    class Config:
        from_attributes = True


# --- Administracion de la plataforma (ver los endpoints /admin de main.py) ---
#
# Todos los campos son opcionales a proposito: el panel envia solo lo que
# cambia, de modo que marcar una casilla no arrastra sin querer el resto de
# valores que el administrador tenia en pantalla.

class UsuarioAdminActualizar(BaseModel):
    """Lo que un administrador puede cambiar de una cuenta ajena."""
    rol: Optional[str] = None               # "admin" | "biologo"
    email_verificado: Optional[bool] = None  # para desbloquear a mano si el correo no llego
    activo: Optional[bool] = None            # desactivar en vez de borrar


class UsuarioAdminRespuesta(BaseModel):
    id: int
    nombre: str
    email: str
    rol: str
    email_verificado: bool
    activo: bool
    fecha_registro: Optional[datetime] = None
    # Contexto para decidir: desactivar a alguien con trabajo detras no es lo
    # mismo que desactivar una cuenta recien creada que no ha hecho nada.
    n_algoritmos: int = 0
    n_peticiones: int = 0


class AlgoritmoAdminActualizar(BaseModel):
    """Lo que un administrador puede cambiar de un algoritmo del catalogo."""
    activo: Optional[bool] = None
    es_publico: Optional[bool] = None
    nombre: Optional[str] = Field(default=None, min_length=1, max_length=120)
    descripcion: Optional[str] = Field(default=None, max_length=2000)
