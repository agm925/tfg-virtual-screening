from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from app.config import DATABASE_URL

# 1. La URL de conexión viene de la variable de entorno DATABASE_URL (ver app/config.py).
#    Por defecto cae a SQLite local para poder seguir desarrollando sin Postgres levantado.
SQLALCHEMY_DATABASE_URL = DATABASE_URL

# 2. Creamos el "Motor" (Engine).
# El argumento 'check_same_thread' es una particularidad necesaria solo para SQLite en FastAPI;
# con PostgreSQL no se pasa ningún connect_args especial.
connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args)

# 3. Creamos la "Fábrica de Sesiones". Cada vez que la web necesite guardar algo, pedirá una sesión aquí.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(Engine, "connect")
def _activar_claves_ajenas_en_sqlite(conexion_dbapi, _registro):
    """
    Hace que SQLite valide las claves ajenas, como hace PostgreSQL.

    SQLite las declara pero NO las comprueba salvo que se le pida por
    conexión: `PRAGMA foreign_keys` vale 0 por defecto. El efecto era que la
    suite de tests --que corre sobre SQLite-- no podía ver una familia entera
    de fallos que en producción (PostgreSQL) sí revientan.

    No es hipotético: por esto pasó desapercibido que DELETE /workflows/{id}
    devolvía un 500 en cuanto el workflow se hubiera ejecutado alguna vez,
    porque borraba las ejecuciones dejando filas de `archivos` apuntando a
    ellas. El test que lo cubre solo falla de verdad con esta comprobación
    activada.

    Se aplica al conectar y solo si el motor es SQLite; con PostgreSQL la
    sentencia no existe y no hay nada que activar, ya viene de serie.
    """
    if not SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
        return
    cursor = conexion_dbapi.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()