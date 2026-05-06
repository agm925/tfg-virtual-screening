from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 1. Definimos que vamos a usar SQLite y el nombre del archivo que se creará
SQLALCHEMY_DATABASE_URL = "sqlite:///./tfg_virtual_screening.db"

# 2. Creamos el "Motor" (Engine). 
# El argumento 'check_same_thread' es una particularidad necesaria solo para SQLite en FastAPI.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# 3. Creamos la "Fábrica de Sesiones". Cada vez que la web necesite guardar algo, pedirá una sesión aquí.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)