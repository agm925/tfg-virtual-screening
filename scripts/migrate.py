"""
Espera a que la base de datos (PostgreSQL en producción/Docker, o SQLite en local)
esté disponible y crea las tablas si no existen todavía.

Uso:
    python scripts/migrate.py
"""

import os
import sys
import time

# Asegura que la raíz del proyecto esté en sys.path para poder hacer `import app`
# sin importar desde qué directorio se invoque el script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.exc import OperationalError  # noqa: E402

from app.database import engine  # noqa: E402
from app import models  # noqa: E402

MAX_INTENTOS = 30
ESPERA_SEGUNDOS = 2


def esperar_base_de_datos() -> None:
    for intento in range(1, MAX_INTENTOS + 1):
        try:
            with engine.connect():
                print(f"Base de datos disponible (intento {intento}/{MAX_INTENTOS}).")
                return
        except OperationalError as e:
            print(f"Base de datos no disponible todavía (intento {intento}/{MAX_INTENTOS}): {e}")
            time.sleep(ESPERA_SEGUNDOS)

    print(f"No se pudo conectar a la base de datos tras {MAX_INTENTOS} intentos.", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    esperar_base_de_datos()
    models.Base.metadata.create_all(bind=engine)
    print("Tablas creadas/verificadas correctamente.")


if __name__ == "__main__":
    main()
