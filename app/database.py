from sqlalchemy import create_engine
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