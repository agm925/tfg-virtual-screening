from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Enum, JSON
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import uuid
import enum

# Esta es la clase base de la que heredarán todas nuestras tablas
Base = declarative_base()

# Definimos las opciones cerradas (Enums) para los Roles y los Estados
class RolUsuario(enum.Enum):
    # Solo hay dos roles. "biologo" es el rol de trabajo: puede usar TODA la
    # funcionalidad cientifica de la plataforma (subir moleculas, subir
    # algoritmos al catalogo, lanzar peticiones y workflows). "admin" es
    # biologo mas la administracion de la propia plataforma (panel de
    # sistema, y la futura pagina de administracion de usuarios, moleculas
    # y algoritmos). El rol intermedio "desarrollador" desaparecio: no
    # anadia ningun permiso que el biologo no deba tener, y obligaba a
    # repetir la lista de roles en cada endpoint.
    admin = "admin"
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

class TipoAlgoritmo(enum.Enum):
    alineacion   = "alineacion"
    comparacion  = "comparacion"
    preprocesado = "preprocesado"
    docking      = "docking"

# --- TABLA 1: USUARIOS ---
class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    rol = Column(Enum(RolUsuario), default=RolUsuario.biologo, nullable=False)
    fecha_registro = Column(DateTime, default=datetime.utcnow)
    email_verificado = Column(Boolean, default=False, nullable=False)
    token_verificacion = Column(String, nullable=True)
    # Desactivacion en lugar de borrado. Un usuario tiene peticiones, workflows
    # y ficheros colgando de el por clave foranea, y sus moleculas pueden estar
    # en la biblioteca compartida, referenciadas por nombre desde los grafos de
    # workflow que OTROS usuarios tienen guardados: borrar la fila romperia la
    # integridad de la base y, con ella, flujos ajenos. Desactivar corta el
    # acceso --no puede iniciar sesion ni usar un token ya emitido, ver
    # app/auth.py-- y conserva intacto el historial. Es ademas reversible, que
    # es lo que se quiere de una medida administrativa.
    activo = Column(Boolean, default=True, nullable=False, index=True)

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
    tipo = Column(Enum(TipoAlgoritmo), nullable=False)  # alineacion o comparacion
    ruta_archivo = Column(String, nullable=False) # Dónde guardaremos el .py
    es_publico = Column(Boolean, default=False)
    autor_id = Column(Integer, ForeignKey("usuarios.id"), index=True)

    # --- Lo que OBSERVA el banco de pruebas al subir el algoritmo ---
    # (ver app/banco_pruebas.py). Anotarlo evita que el motor tenga que
    # deducirlo: buscar la clave del score por su nombre ha sido el origen de
    # cuatro fallos distintos --"rmsd" frente a "rmsd_angstroms", "MW" anidado
    # bajo "moleculas", "mejor_afinidad" nulo, y la extension del fichero--.
    formato_salida = Column(String, nullable=True)   # "molecula" | "json"
    clave_score = Column(String, nullable=True)      # p.ej. "rmsd_angstroms"
    verificado = Column(Boolean, default=False, nullable=False)

    # Retirada del catalogo sin borrar la fila.
    #
    # Es la palanca que le faltaba al admin: el banco de pruebas comprueba que
    # un algoritmo FUNCIONA, no que sea correcto --dos algoritmos correctos del
    # mismo tipo dan resultados distintos--, asi que la correccion cientifica
    # se gestiona de forma reactiva: cuando se detecta que un algoritmo esta
    # mal, se desactiva. Deja de ofrecerse y deja de poder ejecutarse, pero las
    # peticiones que ya lo usaron siguen apuntando a el y conservan su
    # historial, que es justo lo que se perderia borrandolo.
    activo = Column(Boolean, default=True, nullable=False, index=True)

    # Relaciones
    autor = relationship("Usuario", back_populates="algoritmos")
    peticiones = relationship("Peticion", back_populates="algoritmo")

# --- TABLA 3: PETICIONES (Jobs) ---
class Peticion(Base):
    __tablename__ = "peticiones"

    id = Column(Integer, primary_key=True, index=True)
    # index: /sistema/estado cuenta por estado y /peticiones/{id}/estado calcula
    # la posicion en cola filtrando por el.
    estado = Column(String, default="PENDIENTE", index=True)  # PENDIENTE, PROCESANDO, COMPLETADO, ERROR
    # index: _propietario_de_archivo_uploads consulta por estas dos columnas
    # en CADA descarga y en cada borrado de fichero; sin indice es un recorrido
    # completo de la tabla por peticion.
    ruta_mol_original = Column(String, nullable=False, index=True)
    ruta_mol_resultado = Column(String, nullable=True, index=True)
    celery_task_id = Column(String, nullable=True)
    # index: es el criterio de ordenacion del historial paginado.
    fecha_creacion = Column(DateTime, default=datetime.utcnow, index=True)

    # Claves foráneas para conectar las tablas. Van indexadas porque son el
    # filtro de los listados por usuario y el criterio de los joins; SQLAlchemy
    # no crea indices sobre las claves foraneas automaticamente.
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True)
    algoritmo_id = Column(Integer, ForeignKey("algoritmos.id"), index=True)

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
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True)
    estado = Column(String, default="borrador", index=True)  # borrador, procesando, completado, fallido
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    fecha_actualizacion = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relaciones
    usuario = relationship("Usuario", back_populates="workflows")
    ejecuciones = relationship("WorkflowExecution", back_populates="workflow")


# --- TABLA 5: WORKFLOW_EXECUTIONS (Registro de ejecuciones de workflows) ---
class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True)
    estado = Column(String, default="pendiente", index=True)  # pendiente, procesando, completado, error, cancelado
    celery_task_id = Column(String, nullable=True)
    resultados_json = Column(JSON, nullable=True)
    fecha_ejecucion = Column(DateTime, default=datetime.utcnow, index=True)
    duracion_segundos = Column(Integer, nullable=True)

    # Relaciones
    workflow = relationship("Workflow", back_populates="ejecuciones")
    usuario = relationship("Usuario", back_populates="workflow_executions")



# --- TABLA 6: ARCHIVOS (registro de propiedad de los ficheros de uploads/) ---
class VisibilidadArchivo(str, enum.Enum):
    """
    biblioteca: molécula o base de datos del depósito compartido. Cualquier
                usuario autenticado puede leerla y usarla en sus flujos; solo
                su propietario (o un admin) puede borrarla.
    resultado:  fichero producido por una petición o una ejecución de workflow.
                Privado: solo su propietario o un admin.
    """
    biblioteca = "biblioteca"
    resultado = "resultado"


class TipoArchivo(str, enum.Enum):
    """
    QUÉ es un fichero de uploads/, como eje independiente de `visibilidad`
    (QUIÉN puede verlo). Antes se confundían: el frontend deducía el icono
    "🗄️ base de datos" a partir de `visibilidad == resultado`, así que la
    molécula de entrada de una petición cualquiera --privada, pero una
    molécula normal y corriente-- se mostraba como si fuera una base de
    datos, y un .sdf con 10.000 compuestos subido a la biblioteca compartida
    salía con el mismo icono que un .mol2 de un único compuesto.

    molecula:       un único compuesto (cualquier extensión, incluido un
                     .sdf con un solo registro).
    base_de_datos:  un .sdf con más de un registro.
    resultado:      lo ha producido la propia plataforma --una petición o una
                     ejecución de workflow--, no lo subió nadie a mano.
    """
    molecula = "molecula"
    base_de_datos = "base_de_datos"
    resultado = "resultado"


class Archivo(Base):
    """
    Registro de propiedad de los ficheros de uploads/.

    Existe porque hasta ahora la única fuente de propiedad era la tabla
    `peticiones`, y los resultados de un workflow no se anotaban en ninguna
    parte. Como consecuencia caían en el "depósito público" y cualquier
    usuario autenticado podía listar, descargar y BORRAR los resultados de
    docking y los rankings de otro. Con este registro, todo fichero tiene un
    dueño y una visibilidad explícitos.

    `nombre` es único: dos usuarios no pueden tener a la vez un fichero con el
    mismo nombre. Antes la segunda subida sobrescribía la primera en silencio,
    de modo que la petición pendiente del primer usuario pasaba a ejecutarse
    sobre los datos del segundo. Ahora la subida se renombra en vez de pisar
    nada.

    Los ficheros viven planos en uploads/, sin subcarpetas, y es deliberado:
    los grafos de workflow ya guardados referencian sus moléculas por nombre
    suelto, y el frontend descarta el directorio al construir la descarga, así
    que moverlos rompería tanto los flujos guardados como las descargas. La
    unicidad entre ejecuciones concurrentes se consigue incorporando el id de
    la ejecución al nombre del fichero de salida, no separándolos en carpetas.
    """
    __tablename__ = "archivos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False, unique=True, index=True)
    visibilidad = Column(
        Enum(VisibilidadArchivo),
        default=VisibilidadArchivo.biblioteca,
        nullable=False,
        index=True,
    )
    # Nulo solo para los ficheros heredados de antes de este registro, cuyo
    # dueño no consta en ninguna parte: se tratan como biblioteca compartida.
    propietario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True, index=True)
    # Permite borrar de golpe todo lo que produjo una ejecución.
    ejecucion_id = Column(Integer, ForeignKey("workflow_executions.id"), nullable=True, index=True)
    peticion_id = Column(Integer, ForeignKey("peticiones.id"), nullable=True, index=True)
    tamano_bytes = Column(Integer, nullable=True)
    fecha_creacion = Column(DateTime, default=datetime.utcnow, index=True)
    # Nulo solo en filas anteriores a esta columna; scripts/migrate.py las
    # rellena en el primer arranque (backfill_tipo_archivo). El código nuevo
    # SIEMPRE lo rellena al registrar un fichero.
    tipo = Column(Enum(TipoArchivo), nullable=True, index=True)
    # Cacheado en la subida (o en el backfill) para no releer el fichero
    # entero cada vez que se lista: solo tiene sentido para un .sdf, que es
    # el único formato que puede contener más de un registro.
    num_moleculas = Column(Integer, nullable=True)

    propietario = relationship("Usuario")
