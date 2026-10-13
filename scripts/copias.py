"""
Copias de seguridad de la plataforma (spec 009).

Corre en su propio contenedor (Dockerfile.copias: postgres:16 + python3), de
modo que pg_dump es de la misma version que la base, y solo usa la
biblioteca estandar: no importa nada de app/, que no esta en esa imagen.

Uso (dentro del contenedor):
    python3 copias.py servicio            # una copia al dia, a COPIA_HORA
    python3 copias.py ahora               # una copia ya
    python3 copias.py restaurar <copia>   # base y ficheros desde una copia

Hasta la spec 009 no habia ninguna copia: un borrado por error, una
migracion fallida o un disco roto se llevaban la plataforma entera.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# El nombre de cada copia es su fecha: se ordenan solas y se sabe de un
# vistazo de cuando es cada una.
FORMATO_NOMBRE = "%Y-%m-%d_%H%M"
SUFIJO_PARCIAL = ".parcial"
DOMINGO = 6
VOLCADO = "base.dump"
MANIFIESTO = "manifiesto.json"
# Carpetas de cada origen que no se copian: uploads/.indices se regenera
# sola la primera vez que se usa una biblioteca (app/indice_sdf.py).
EXCLUIR = {"uploads": {".indices"}}


def nombre_copia(fecha: datetime) -> str:
    return fecha.strftime(FORMATO_NOMBRE)


def fecha_de(nombre: str):
    """La fecha de una copia terminada, o None si el nombre no es de una."""
    try:
        return datetime.strptime(nombre, FORMATO_NOMBRE)
    except ValueError:
        # Una .parcial (copia a medias o fallida) o algo que no ha creado
        # este script: ni cuenta como copia ni se borra.
        return None


def copias_a_borrar(nombres) -> list:
    """
    Que copias terminadas sobran: se conservan la mas reciente y la mas
    reciente de un domingo (decision del usuario: una diaria y una semanal).
    Una del domingo cuenta como las dos, y la unica copia nunca se borra.
    """
    fechas = sorted(f for f in (fecha_de(n) for n in nombres) if f is not None)
    if not fechas:
        return []
    conservar = {fechas[-1]}
    domingos = [f for f in fechas if f.weekday() == DOMINGO]
    if domingos:
        conservar.add(domingos[-1])
    return [nombre_copia(f) for f in fechas if f not in conservar]


def _igual(a: os.stat_result, b: os.stat_result) -> bool:
    # Tamaño y fecha, como rsync: leer los dos ficheros enteros para
    # compararlos costaria tanto como copiarlos. shutil.copy2 conserva la
    # fecha, asi que un fichero sin tocar desde la ultima copia coincide.
    return a.st_size == b.st_size and int(a.st_mtime) == int(b.st_mtime)


def copiar_ficheros(origen: Path, destino: Path, anterior=None, excluir=frozenset()) -> tuple:
    """
    Copia el arbol `origen` en `destino` y devuelve (ficheros, bytes).

    Lo que no ha cambiado desde la copia `anterior` se ENLAZA (enlace duro) en
    vez de copiarse: cada copia esta completa por si sola, pero solo ocupa lo
    nuevo. Si el sistema de ficheros no admite enlaces --Docker Desktop en
    Windows, sobre una carpeta montada--, se copia entero: ocupa mas, pero la
    copia sale igual.

    `excluir` son carpetas de primer nivel que no se copian (uploads/.indices,
    que se regenera sola).
    """
    origen, destino = Path(origen), Path(destino)
    anterior = Path(anterior) if anterior else None
    ficheros = octetos = 0
    if not origen.is_dir():
        return 0, 0
    for raiz, carpetas, nombres in os.walk(origen):
        relativa = Path(raiz).relative_to(origen)
        if relativa == Path("."):
            carpetas[:] = [c for c in carpetas if c not in excluir]
        (destino / relativa).mkdir(parents=True, exist_ok=True)
        for nombre in nombres:
            fuente = Path(raiz) / nombre
            copia = destino / relativa / nombre
            datos = fuente.stat()
            previa = anterior / relativa / nombre if anterior else None
            enlazado = False
            if previa is not None and previa.is_file() and _igual(datos, previa.stat()):
                try:
                    os.link(previa, copia)
                    enlazado = True
                except OSError:
                    pass
            if not enlazado:
                shutil.copy2(fuente, copia)
            ficheros += 1
            octetos += datos.st_size
    return ficheros, octetos


def ultima_copia(raiz: Path):
    """La carpeta de la copia terminada mas reciente, o None."""
    raiz = Path(raiz)
    if not raiz.is_dir():
        return None
    terminadas = sorted((fecha_de(p.name), p) for p in raiz.iterdir()
                        if p.is_dir() and fecha_de(p.name) is not None)
    return terminadas[-1][1] if terminadas else None


def volcar_base(ruta: Path) -> None:
    """
    Vuelca la base con pg_dump en formato propio (-Fc): comprimido, y
    pg_restore puede restaurarlo limpiando antes lo que haya. La conexion
    sale de las variables PGHOST, PGUSER, PGPASSWORD y PGDATABASE.
    """
    proceso = subprocess.run(["pg_dump", "-Fc", "-f", str(ruta)],
                             capture_output=True, text=True)
    if proceso.returncode != 0:
        raise RuntimeError(f"pg_dump ha fallado: {proceso.stderr.strip()[-300:]}")


def leer_estado(ruta: Path) -> dict:
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _escribir_json(ruta: Path, datos: dict) -> None:
    # Se escribe aparte y se renombra: quien lo lea (el backend, para la
    # pagina Sistema) nunca ve un JSON a medias.
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporal, ruta)


def hacer_copia(raiz: Path, origenes: dict, ahora: datetime,
                volcar_base=volcar_base, ruta_estado=None) -> str:
    """
    Hace una copia completa en `raiz` y devuelve su nombre.

    Primero la base y despues los ficheros: asi, como mucho, en la copia
    sobra algun fichero que aun no tenia fila (inofensivo); al reves podria
    quedar una fila que apunta a un fichero que no esta en la copia.

    Todo se escribe en <nombre>.parcial y solo al final se renombra: una
    copia sin ese sufijo esta siempre completa. Si algo falla, se borra la
    parcial, no se toca ninguna anterior y el fallo queda en el estado.
    """
    raiz = Path(raiz)
    raiz.mkdir(parents=True, exist_ok=True)
    # Lleva los hashes de las contraseñas y los ficheros privados de todos
    # (spec 007): solo para quien administra el servidor.
    os.chmod(raiz, 0o700)
    nombre = nombre_copia(ahora)
    parcial = raiz / (nombre + SUFIJO_PARCIAL)
    estado_previo = leer_estado(ruta_estado) if ruta_estado else {}
    try:
        if (raiz / nombre).exists():
            raise RuntimeError(f"ya hay una copia {nombre}; espera un minuto")
        if parcial.exists():
            shutil.rmtree(parcial)
        anterior = ultima_copia(raiz)
        parcial.mkdir()
        volcar_base(parcial / VOLCADO)

        ficheros = octetos = 0
        for nombre_origen, origen in origenes.items():
            f, o = copiar_ficheros(
                origen, parcial / nombre_origen,
                anterior=anterior / nombre_origen if anterior else None,
                excluir=EXCLUIR.get(nombre_origen, frozenset()),
            )
            ficheros += f
            octetos += o

        manifiesto = {
            "copia": nombre,
            "fecha": ahora.isoformat(timespec="minutes"),
            "ficheros": ficheros,
            "bytes": octetos,
            "volcado_bytes": (parcial / VOLCADO).stat().st_size,
        }
        _escribir_json(parcial / MANIFIESTO, manifiesto)
        os.replace(parcial, raiz / nombre)
    except Exception as e:
        shutil.rmtree(parcial, ignore_errors=True)
        if ruta_estado:
            _escribir_json(ruta_estado, {
                "ultimo_intento": ahora.isoformat(timespec="minutes"),
                "ok": False,
                "error": str(e),
                "ultima_buena": estado_previo.get("ultima_buena"),
            })
        raise

    for sobrante in copias_a_borrar(p.name for p in raiz.iterdir()):
        shutil.rmtree(raiz / sobrante, ignore_errors=True)
    if ruta_estado:
        _escribir_json(ruta_estado, {
            "ultimo_intento": ahora.isoformat(timespec="minutes"),
            "ok": True,
            "error": None,
            "ultima_buena": manifiesto,
        })
    return nombre


def restaurar_base(ruta: Path) -> None:
    """
    Restaura un volcado de pg_dump. --clean --if-exists borra antes lo que
    haya, asi que vale igual sobre una base vacia que sobre una estropeada.
    """
    proceso = subprocess.run(
        ["pg_restore", "--clean", "--if-exists", "--no-owner",
         "-d", os.environ.get("PGDATABASE", ""), str(ruta)],
        capture_output=True, text=True,
    )
    if proceso.returncode != 0:
        raise RuntimeError(f"pg_restore ha fallado: {proceso.stderr.strip()[-300:]}")


def restaurar(raiz: Path, nombre: str, destinos: dict, restaurar_base=restaurar_base) -> None:
    """
    Repone la base y los ficheros de una copia terminada.

    Los ficheros de la copia se copian encima de los actuales; los que no
    estaban en la copia se quedan (scripts/limpiar_uploads.py los senala
    como huerfanos). Borrar lo que sobra seria irreversible, y quien
    restaura puede decidirlo despues con calma.
    """
    raiz = Path(raiz)
    copia = raiz / nombre
    # fecha_de tambien rechaza nombres con rutas ("../uploads") o .parcial.
    if fecha_de(nombre) is None or not (copia / MANIFIESTO).is_file():
        disponibles = sorted(p.name for p in raiz.iterdir() if fecha_de(p.name)) if raiz.is_dir() else []
        raise ValueError(f"No hay ninguna copia terminada que se llame «{nombre}». "
                         f"Copias disponibles: {', '.join(disponibles) or 'ninguna'}.")
    restaurar_base(copia / VOLCADO)
    for nombre_origen, destino in destinos.items():
        guardado = copia / nombre_origen
        if not guardado.is_dir():
            continue
        for raiz_copia, _, nombres in os.walk(guardado):
            relativa = Path(raiz_copia).relative_to(guardado)
            (Path(destino) / relativa).mkdir(parents=True, exist_ok=True)
            for n in nombres:
                shutil.copy2(Path(raiz_copia) / n, Path(destino) / relativa / n)


def siguiente_copia(ahora: datetime, hora: str) -> datetime:
    """La proxima vez que toca copiar: hoy a `hora` si aun no ha pasado; si no, manana."""
    h, m = (int(x) for x in hora.split(":"))
    cita = ahora.replace(hour=h, minute=m, second=0, microsecond=0)
    return cita if cita > ahora else cita + timedelta(days=1)


# Rutas dentro del contenedor (ver el servicio `copias` de docker-compose.yml).
RAIZ = Path(os.environ.get("COPIAS_DIR", "/copias"))
ESTADO = Path(os.environ.get("COPIAS_ESTADO", "/estado/estado.json"))
ORIGENES = {"uploads": Path("/datos/uploads"), "algoritmos": Path("/datos/algoritmos")}
# Para restaurar se montan con escritura aqui, solo en esa orden: el servicio
# normal los tiene de solo lectura.
DESTINOS = {"uploads": Path("/restaurar/uploads"), "algoritmos": Path("/restaurar/algoritmos")}


def _copiar_ahora() -> bool:
    try:
        # Con zona horaria: el backend, que lee el estado, va en UTC.
        nombre = hacer_copia(RAIZ, ORIGENES, datetime.now().astimezone(), ruta_estado=ESTADO)
    except Exception as e:  # noqa: BLE001 -- el servicio no debe morir por una copia fallida
        print(f"[copias] FALLO: {e}", flush=True)
        return False
    print(f"[copias] copia {nombre} terminada", flush=True)
    return True


def main(argv) -> int:
    orden = argv[1] if len(argv) > 1 else "servicio"
    if orden == "ahora":
        return 0 if _copiar_ahora() else 1
    if orden == "restaurar" and len(argv) == 3:
        if not all(d.is_dir() for d in DESTINOS.values()):
            print("[copias] Para restaurar hay que montar uploads/ y algoritmos/ en "
                  "/restaurar (ver despliegue.md).", file=sys.stderr)
            return 1
        try:
            restaurar(RAIZ, argv[2], DESTINOS)
        except (ValueError, RuntimeError) as e:
            print(f"[copias] {e}", file=sys.stderr)
            return 1
        print(f"[copias] copia {argv[2]} restaurada. Arranca de nuevo backend y workers.")
        return 0
    if orden == "servicio":
        hora = os.environ.get("COPIA_HORA", "03:00")
        while True:
            cita = siguiente_copia(datetime.now(), hora)
            print(f"[copias] proxima copia: {cita:%Y-%m-%d %H:%M}", flush=True)
            # Se duerme en tramos cortos y se vuelve a mirar la hora: un
            # sleep largo se desajusta si el equipo se suspende.
            while datetime.now() < cita:
                time.sleep(min(300, max(1, (cita - datetime.now()).total_seconds())))
            _copiar_ahora()
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
