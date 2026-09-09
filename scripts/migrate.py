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


def crear_indices_faltantes() -> None:
    """
    Crea los índices declarados en los modelos que aún no existan.

    Hace falta porque `create_all()` solo crea índices al crear la tabla: si
    la tabla ya existe --que es el caso de cualquier despliegue en marcha--,
    los índices añadidos después a los modelos no se aplican nunca, y el
    esquema real se queda por detrás del declarado sin ningún aviso.

    Con Alembic esto sería una migración; mientras no lo haya (ver el trabajo
    futuro sobre migraciones), `checkfirst=True` da un equivalente idempotente
    y suficiente: consulta el catálogo del motor y solo emite CREATE INDEX
    para los que faltan, de modo que el script puede ejecutarse en cada
    arranque sin efectos.
    """
    creados = []
    for tabla in models.Base.metadata.sorted_tables:
        for indice in tabla.indexes:
            try:
                indice.create(bind=engine, checkfirst=True)
                creados.append(indice.name)
            except Exception as e:  # noqa: BLE001
                # Un índice que no se puede crear no debe impedir el arranque
                # de la aplicación: se degrada el rendimiento, no la función.
                print(f"Aviso: no se pudo crear el índice {indice.name}: {e}", file=sys.stderr)
    print(f"Índices verificados: {len(creados)}.")


def main() -> None:
    esperar_base_de_datos()
    models.Base.metadata.create_all(bind=engine)
    print("Tablas creadas/verificadas correctamente.")
    crear_indices_faltantes()


if __name__ == "__main__":
    main()
