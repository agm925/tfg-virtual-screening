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


def registrar_archivos_existentes() -> None:
    """
    Da de alta en la tabla `archivos` los ficheros que ya estaban en uploads/.

    Sin esto, al pasar el listado de moléculas a consultar el registro en vez
    de escanear el directorio, toda la biblioteca previa desaparecería de la
    interfaz aunque los ficheros siguieran en disco.

    La propiedad se deduce de la tabla `peticiones`, que hasta ahora era la
    única que la registraba: un fichero que aparece como entrada o salida de
    una petición pertenece a su autor y se marca como resultado privado. Todo
    lo demás no tiene dueño deducible en ninguna parte, así que se registra
    como biblioteca compartida, que es exactamente el trato que recibía antes.

    Es idempotente: solo inserta lo que falta, de modo que puede ejecutarse en
    cada arranque.
    """
    from sqlalchemy.orm import sessionmaker

    directorio = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
    if not os.path.isdir(directorio):
        print("No hay carpeta uploads/: nada que registrar.")
        return

    Sesion = sessionmaker(bind=engine)
    db = Sesion()
    try:
        ya_registrados = {n for (n,) in db.query(models.Archivo.nombre).all()}

        # Propiedad conocida: lo que consta en peticiones.
        duenos = {}
        for usuario_id, peticion_id, original, resultado in db.query(
            models.Peticion.usuario_id, models.Peticion.id,
            models.Peticion.ruta_mol_original, models.Peticion.ruta_mol_resultado,
        ).all():
            for nombre in (original, resultado):
                if nombre:
                    duenos[nombre] = (usuario_id, peticion_id)

        nuevos = 0
        for nombre in os.listdir(directorio):
            ruta = os.path.join(directorio, nombre)
            if not os.path.isfile(ruta) or nombre in ya_registrados:
                continue
            usuario_id, peticion_id = duenos.get(nombre, (None, None))
            db.add(models.Archivo(
                nombre=nombre,
                visibilidad=(models.VisibilidadArchivo.resultado if usuario_id
                             else models.VisibilidadArchivo.biblioteca),
                propietario_id=usuario_id,
                peticion_id=peticion_id,
                tamano_bytes=os.path.getsize(ruta),
            ))
            nuevos += 1
            if nuevos % 500 == 0:
                db.commit()
        db.commit()
        print(f"Archivos registrados: {nuevos} nuevos "
              f"({len(ya_registrados)} ya estaban en el registro).")
    finally:
        db.close()


def main() -> None:
    esperar_base_de_datos()
    models.Base.metadata.create_all(bind=engine)
    print("Tablas creadas/verificadas correctamente.")
    crear_indices_faltantes()
    registrar_archivos_existentes()


if __name__ == "__main__":
    main()
