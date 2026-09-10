"""
Localiza y opcionalmente elimina ficheros de uploads/ que dicen ser moleculas
pero no lo son.

Por que existe: durante mucho tiempo, app/tasks.py construia el nombre del
fichero de salida de una peticion como

    ruta_mol_original.replace(".mol2", "_resultado.mol2")

es decir, dando por hecho que TODO algoritmo produce una molecula. Los que
devuelven metricas --filtroLipinski, similaridadTanimoto, rmsdConformaciones--
escribian por tanto su JSON en un fichero con extension .mol2. La biblioteca
los ofrecia como moleculas y el visor 3D no mostraba nada al abrirlos. En el
entorno de desarrollo llegaron a acumularse casi dos mil.

El fallo esta corregido en origen (ver app/formatos.py), pero los ficheros ya
escritos siguen en disco. Este script los identifica.

POR DEFECTO NO BORRA NADA: solo informa. Hay que pasar --borrar
explicitamente.

Uso:
    python scripts/limpiar_uploads.py                 # simulacro: solo informa
    python scripts/limpiar_uploads.py --borrar        # borra de disco y del registro
    python scripts/limpiar_uploads.py --borrar --temporales
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOADS = os.path.join(RAIZ, "uploads")

EXTENSIONES_MOLECULA = (".mol2", ".sdf", ".mol", ".pdb", ".pdbqt", ".smi", ".xyz")


def es_json(ruta):
    """Si el fichero contiene un documento JSON, mirando solo su comienzo."""
    try:
        with open(ruta, "rb") as f:
            inicio = f.read(2048).lstrip()
        if inicio[:1] not in (b"{", b"["):
            return False
        with open(ruta, "r", encoding="utf-8", errors="ignore") as f:
            json.load(f)
        return True
    except Exception:
        return False


def clasificar():
    """Devuelve (impostores, temporales, vacios)."""
    impostores, temporales, vacios = [], [], []
    if not os.path.isdir(UPLOADS):
        return impostores, temporales, vacios

    for nombre in sorted(os.listdir(UPLOADS)):
        ruta = os.path.join(UPLOADS, nombre)
        if not os.path.isfile(ruta):
            continue
        ext = os.path.splitext(nombre)[1].lower()

        if os.path.getsize(ruta) == 0:
            vacios.append(nombre)
        elif nombre.startswith("_btmp_"):
            # Temporales del cribado por lotes. Se borran solos al terminar
            # cada molecula; si quedan, es de una ejecucion interrumpida.
            temporales.append(nombre)
        elif ext in EXTENSIONES_MOLECULA and es_json(ruta):
            impostores.append(nombre)

    return impostores, temporales, vacios


def sesion_y_motor():
    """Abre sesion contra la base que indique DATABASE_URL, y dice cual es."""
    from sqlalchemy.orm import sessionmaker

    from app.database import SQLALCHEMY_DATABASE_URL, engine

    return sessionmaker(bind=engine)(), SQLALCHEMY_DATABASE_URL


def huerfanas():
    """
    Filas del registro `archivos` cuyo fichero ya no esta en disco.

    Es facil quedarse con estas sin darse cuenta, porque la interfaz LISTA EL
    REGISTRO y no el directorio: si se borran los ficheros por un lado y el
    registro se limpia en otra base de datos --por ejemplo ejecutando este
    script desde el host, donde DATABASE_URL cae por defecto a SQLite, cuando
    la aplicacion corre en Docker contra PostgreSQL-- los ficheros desaparecen
    del disco pero siguen apareciendo en la web.
    """
    try:
        db, url = sesion_y_motor()
    except Exception as e:
        print(f"  no se pudo consultar el registro: {e}", file=sys.stderr)
        return [], None
    try:
        from app import models

        nombres = [n for (n,) in db.query(models.Archivo.nombre).all()]
        return [n for n in nombres
                if not os.path.exists(os.path.join(UPLOADS, n))], url
    finally:
        db.close()


def borrar_huerfanas(nombres):
    """Elimina del registro las filas sin fichero."""
    if not nombres:
        return 0
    db, _ = sesion_y_motor()
    try:
        from app import models

        n = db.query(models.Archivo).filter(
            models.Archivo.nombre.in_(nombres)).delete(synchronize_session=False)
        db.commit()
        return n
    finally:
        db.close()


def borrar(nombres, motivo):
    """Borra de disco y, si la base de datos esta accesible, del registro."""
    borrados = 0
    for nombre in nombres:
        ruta = os.path.join(UPLOADS, nombre)
        try:
            os.remove(ruta)
            borrados += 1
        except OSError as e:
            print(f"  no se pudo borrar {nombre}: {e}", file=sys.stderr)

    try:
        from sqlalchemy.orm import sessionmaker

        from app import models
        from app.database import engine

        db = sessionmaker(bind=engine)()
        try:
            n = db.query(models.Archivo).filter(
                models.Archivo.nombre.in_(nombres)).delete(synchronize_session=False)
            db.commit()
            print(f"  {borrados} ficheros borrados ({motivo}); {n} filas del registro")
        finally:
            db.close()
    except Exception as e:
        print(f"  {borrados} ficheros borrados ({motivo}); "
              f"registro no actualizado ({e})")
    return borrados


def main():
    parser = argparse.ArgumentParser(
        description="Limpia ficheros de uploads/ que no son moleculas.")
    parser.add_argument("--borrar", action="store_true",
                        help="borra de verdad; sin este flag solo informa")
    parser.add_argument("--temporales", action="store_true",
                        help="incluye tambien los temporales _btmp_ huerfanos")
    args = parser.parse_args()

    impostores, temporales, vacios = clasificar()
    filas_huerfanas, url_registro = huerfanas()
    total_ficheros = len([n for n in os.listdir(UPLOADS)
                          if os.path.isfile(os.path.join(UPLOADS, n))]) if os.path.isdir(UPLOADS) else 0

    print(f"uploads/ contiene {total_ficheros} ficheros.")
    print()
    print(f"  JSON con extension de molecula : {len(impostores)}")
    print(f"  temporales _btmp_ huerfanos    : {len(temporales)}")
    print(f"  ficheros vacios                : {len(vacios)}")
    print()
    if url_registro:
        motor = url_registro.split("://")[0]
        print(f"  registro consultado            : {motor}")
        print(f"  filas sin fichero en disco     : {len(filas_huerfanas)}")
        if len(filas_huerfanas) > 50:
            print()
            print("  AVISO: hay muchas filas sin fichero. Si la aplicacion corre en")
            print("  Docker, este script debe ejecutarse DENTRO del contenedor:")
            print("      docker compose exec backend python scripts/limpiar_uploads.py --borrar")
            print("  Ejecutado desde el host, DATABASE_URL cae por defecto a SQLite y")
            print("  se limpiaria un registro distinto del que usa la web.")
        print()

    for etiqueta, lista in (("JSON con extension de molecula", impostores),
                            ("temporales huerfanos", temporales),
                            ("vacios", vacios)):
        if lista:
            print(f"  ejemplos de {etiqueta}: " + ", ".join(lista[:3])
                  + (" ..." if len(lista) > 3 else ""))

    a_borrar = list(impostores) + list(vacios)
    if args.temporales:
        a_borrar += temporales

    if not a_borrar and not filas_huerfanas:
        print("\nNada que limpiar.")
        return

    if not args.borrar:
        print(f"\nSIMULACRO: se borrarian {len(a_borrar)} ficheros"
              f" y {len(filas_huerfanas)} filas huerfanas del registro.")
        print("Vuelve a ejecutarlo con --borrar para hacerlo de verdad.")
        return

    if a_borrar:
        print(f"\nBorrando {len(a_borrar)} ficheros...")
        borrar(a_borrar, "no son moleculas")
    if filas_huerfanas:
        # Sin esto, los ficheros desaparecen del disco pero la web sigue
        # listandolos: la interfaz consulta el registro, no el directorio.
        n = borrar_huerfanas(filas_huerfanas)
        print(f"  {n} filas huerfanas eliminadas del registro")


if __name__ == "__main__":
    main()
