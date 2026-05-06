from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Enum, JSON
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import uuid
import enum

# Esta es la clase base de la que heredarán todas nuestras tablas
Base = declarative_base()

# Definimos las opciones cerradas (Enums) para los Roles y los Estados
class RolUsuario(enum.Enum):
    admin = "admin"
    desarrollador = "desarrollador"
    biologo = "biologo"

class EstadoPeticion(enum.Enum):
    en_cola = "en_cola"
    ejecutandose = "ejecutandose"
    resuelto = "resuelto"
    fallido = "fallido"

class EstadoWorkflow(enum.Enum):
    borrador = "borrador"
    procesando = "procesando"
    completado = "completado"
    fallido = "fallido"

# --- TABLA 1: USUARIOS ---
class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    rol = Column(Enum(RolUsuario), default=RolUsuario.biologo, nullable=False)
    fecha_registro = Column(DateTime, default=datetime.utcnow)

    # Relaciones (Un usuario puede tener muchos algoritmos y muchas peticiones)
    algoritmos = relationship("Algoritmo", back_populates="autor")
    peticiones = relationship("Peticion", back_populates="usuario")
    workflows = relationship("Workflow", back_populates="usuario")
    workflow_executions = relationship("WorkflowExecution", back_populates="usuario")

# --- TABLA 2: ALGORITMOS (Scripts) ---
class Algoritmo(Base):
    __tablename__ = "algoritmos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    descripcion = Column(String)
    ruta_archivo = Column(String, nullable=False) # Dónde guardaremos el .py
    es_publico = Column(Boolean, default=False)
    autor_id = Column(Integer, ForeignKey("usuarios.id"))

    # Relaciones
    autor = relationship("Usuario", back_populates="algoritmos")
    peticiones = relationship("Peticion", back_populates="algoritmo")

# --- TABLA 3: PETICIONES (Jobs) ---
class Peticion(Base):
    __tablename__ = "peticiones"

    id = Column(Integer, primary_key=True, index=True)
    estado = Column(String, default="PENDIENTE")  # PENDIENTE, PROCESANDO, COMPLETADO, ERROR
    ruta_mol_original = Column(String, nullable=False) # Dónde guardamos el .mol2 que sube el biólogo
    ruta_mol_resultado = Column(String, nullable=True) # Aquí guardaremos el _aligned.mol2 cuando termine
    
    # Claves foráneas para conectar las tablas
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    algoritmo_id = Column(Integer, ForeignKey("algoritmos.id"))

    # Relaciones (Asegúrate de tener las contrapartes en Usuario y Algoritmo)
    usuario = relationship("Usuario", back_populates="peticiones")
    algoritmo = relationship("Algoritmo", back_populates="peticiones")


# --- TABLA 4: WORKFLOWS (Flujos de trabajo visual tipo KNIME) ---
class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    descripcion = Column(String, nullable=True)
    grafo_json = Column(JSON, nullable=False)  # { nodes: [...], edges: [...] }
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    estado = Column(String, default="borrador")  # borrador, procesando, completado, fallido
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    fecha_actualizacion = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relaciones
    usuario = relationship("Usuario", back_populates="workflows")
    ejecuciones = relationship("WorkflowExecution", back_populates="workflow")


# --- TABLA 5: WORKFLOW_EXECUTIONS (Registro de ejecuciones de workflows) ---
class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"))
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    estado = Column(String, default="pendiente")  # pendiente, procesando, completado, error
    resultados_json = Column(JSON, nullable=True)  # { nodo_id: { resultado, logs, error } }
    fecha_ejecucion = Column(DateTime, default=datetime.utcnow)
    duracion_segundos = Column(Integer, nullable=True)

    # Relaciones
    workflow = relationship("Workflow", back_populates="ejecuciones")
    usuario = relationship("Usuario", back_populates="workflow_executions")

