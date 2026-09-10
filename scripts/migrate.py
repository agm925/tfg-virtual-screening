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


def anadir_columnas_faltantes() -> None:
    """
    Añade a las tablas ya existentes las columnas que se hayan declarado
    después en los modelos.

    Hace falta por la misma razón que `crear_indices_faltantes`, pero el
    síntoma es peor: `create_all()` solo define las columnas al CREAR la
    tabla, de modo que sobre un despliegue en marcha una columna nueva no
    aparece nunca y la aplicación falla al escribirla con un
    `UndefinedColumn` en tiempo de ejecución, no al arrancar.

    Es un sustituto mínimo de una herramienta de migraciones como Alembic
    --que sigue siendo la solución de fondo, y así queda recogido en el
    trabajo futuro--: solo sabe AÑADIR columnas, que es el único cambio de
    esquema que se ha necesitado hasta ahora. No renombra, no borra y no
    cambia tipos.
    """
    from sqlalchemy import inspect, text
    from sqlalchemy.schema import CreateColumn

    inspector = inspect(engine)
    anadidas = 0

    for tabla in models.Base.metadata.sorted_tables:
        if not inspector.has_table(tabla.name):
            continue
        existentes = {c["name"] for c in inspector.get_columns(tabla.name)}
        for columna in tabla.columns:
            if columna.name in existentes:
                continue
            tipo = columna.type.compile(dialect=engine.dialect)
            ddl = f'ALTER TABLE {tabla.name} ADD COLUMN {columna.name} {tipo}'

            # Una columna NOT NULL sobre una tabla con filas necesita un valor
            # por defecto, o el motor la rechaza.
            defecto = getattr(columna.default, "arg", None)
            if not columna.nullable:
                if isinstance(defecto, bool):
                    ddl += f" NOT NULL DEFAULT {'true' if defecto else 'false'}"
                elif isinstance(defecto, (int, float)):
                    ddl += f" NOT NULL DEFAULT {defecto}"
                elif isinstance(defecto, str):
                    ddl += f" NOT NULL DEFAULT '{defecto}'"
                # Sin defecto utilizable se añade como nullable: es preferible
                # a que la migración falle y deje el esquema a medias.

            try:
                with engine.begin() as conexion:
                    conexion.execute(text(ddl))
                print(f"  columna añadida: {tabla.name}.{columna.name}")
                anadidas += 1
            except Exception as e:  # noqa: BLE001
                print(f"Aviso: no se pudo añadir {tabla.name}.{columna.name}: {e}",
                      file=sys.stderr)

    print(f"Columnas verificadas: {anadidas} añadidas.")


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
    anadir_columnas_faltantes()
    crear_indices_faltantes()
    registrar_archivos_existentes()


if __name__ == "__main__":
    main()
