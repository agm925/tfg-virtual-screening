from pydantic import BaseModel

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