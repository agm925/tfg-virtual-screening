"""
Benchmark de rendimiento de la API de cribado virtual.

Mide el tiempo de ejecucion del algoritmo de filtro de Lipinski
(algoritmos/filtroLipinski.py) sobre lotes de moleculas de distinto tamano,
usando exclusivamente los endpoints reales de la API (POST /peticiones +
polling de GET /peticiones/{id}/estado), igual que lo haria el frontend.

Requisitos:
    - docker compose up -d   (los 6 contenedores deben estar corriendo)
    - pip install requests   (si no lo tienes ya en tu Python del host)

Todos los endpoints que usa el benchmark exigen autenticacion desde el
endurecimiento de seguridad, asi que el script se registra, se da de alta a si
mismo como desarrollador con el correo verificado (directamente contra la BD,
via docker compose exec) y opera con un token JWT como lo haria el frontend.

El numero de workers de Celery NO lo cambia este script: lo cambias tu a
mano con `docker compose up --scale worker=N` ANTES de lanzar el benchmark.
El flag --workers solo sirve para etiquetar esa tanda de resultados en el CSV.

Uso:
    python scripts/benchmark.py --workers 1
    docker compose up --scale worker=4 -d
    python scripts/benchmark.py --workers 4
    python scripts/benchmark.py --workers 1 --batches 50,200
"""

import argparse
import csv
import datetime
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UPLOADS_DIR = PROJECT_ROOT / "uploads"
CSV_PATH = PROJECT_ROOT / "scripts" / "benchmark_results.csv"
CSV_FIELDS = [
    "algoritmo",
    "n_moleculas",
    "n_workers",
    "tiempo_total_s",
    "tiempo_medio_por_molecula_s",
    "moleculas_por_segundo",
    "fecha",
]

API_URL = "http://localhost:8000"
# NOTA: la version original de esta URL (con el filtro "molecular_weight__lte")
# devuelve 404 ("Molecule has no structure records") en cuanto limit>~100, porque
# ese campo de filtro no existe en el API de ChEMBL y ademas algunas moleculas del
# lote no tienen structure record, lo que hace fallar la exportacion SDF entera.
# Se usa el filtro real de ChEMBL para peso molecular (molecule_properties__mw_freebase)
# y se excluyen moleculas sin estructura con molecule_structures__isnull=false.
CHEMBL_SDF_URL = (
    "https://www.ebi.ac.uk/chembl/api/data/molecule.sdf"
    "?limit=1000&molecule_structures__isnull=false&molecule_properties__mw_freebase__lte=500"
)
SDF_LOCAL_NAME = "benchmark_chembl.sdf"
MOL2_PREFIX = "benchmark_mol"

# example.com y no un dominio inventado: la validacion de entrada usa
# EmailStr, que rechaza los TLD reservados como .local con un 422.
TEST_EMAIL = "benchmark_bot@example.com"
TEST_PASSWORD = "benchmark12345"
TEST_NOMBRE = "Benchmark Bot"
ALGORITMO_NOMBRE = "filtroLipinski (benchmark)"
ALGORITMO_RUTA = "filtroLipinski.py"


def docker_exec(*args, timeout=900):
    """Ejecuta un comando dentro del contenedor 'backend' (tiene RDKit, OpenBabel y
    la conexion correcta a Postgres ya configurados; el host no los necesita)."""
    cmd = ["docker", "compose", "exec", "-T", "backend", *args]
    return subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=timeout)


def preflight():
    try:
        r = requests.get(f"{API_URL}/", timeout=5)
        r.raise_for_status()
    except Exception as e:
        sys.exit(
            "No se puede contactar con la API en http://localhost:8000\n"
            f"  ({e})\n"
            "Arranca la plataforma con:  docker compose up -d\n"
        )

    r = docker_exec("true")
    if r.returncode != 0:
        sys.exit(
            "No se pudo ejecutar comandos dentro del contenedor 'backend' via "
            "'docker compose exec'.\n"
            f"stderr: {r.stderr}\n"
            "Comprueba que 'docker compose up -d' esta corriendo en este mismo directorio."
        )
    print("API y contenedor backend accesibles. OK.")


def descargar_sdf() -> Path:
    ruta = UPLOADS_DIR / SDF_LOCAL_NAME
    if ruta.exists() and ruta.stat().st_size > 0:
        print(f"SDF de prueba ya descargado: {ruta.name} ({ruta.stat().st_size / 1024:.1f} KB)")
        return ruta

    print(f"Descargando SDF de prueba desde ChEMBL...\n  {CHEMBL_SDF_URL}")
    UPLOADS_DIR.mkdir(exist_ok=True)
    tmp = ruta.with_suffix(".sdf.tmp")
    with requests.get(CHEMBL_SDF_URL, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
    tmp.rename(ruta)
    print(f"Descargado: {ruta.name} ({ruta.stat().st_size / 1024:.1f} KB)")
    return ruta


def _indice_mol2(ruta: Path) -> int:
    """Indice numerico de un .mol2 generado por la division del SDF.

    Debe distinguir 'benchmark_mol90.mol2' (entrada valida, indice 90) de los
    ficheros de SALIDA que genera el propio algoritmo sobre esa entrada, como
    'benchmark_mol90_resultado.mol2' o 'benchmark_mol90_resultado_resultado.mol2'
    (acumulados de ejecuciones anteriores) — esos NO son moleculas de entrada y
    si se cuelan aqui, RDKit no puede parsearlos ("no se pudo cargar ninguna
    molecula valida"), como paso en el lote de 1000 antes de este fix.
    """
    m = re.fullmatch(rf"{re.escape(MOL2_PREFIX)}(\d+)\.mol2", ruta.name)
    return int(m.group(1)) if m else -1


def dividir_en_mol2(max_n: int) -> list:
    """Divide el SDF en archivos .mol2 individuales usando OpenBabel dentro del
    contenedor backend (el host no tiene por que tener rdkit/openbabel instalados)."""
    existentes = sorted(
        (p for p in UPLOADS_DIR.glob(f"{MOL2_PREFIX}*.mol2") if _indice_mol2(p) != -1),
        key=_indice_mol2,
    )
    if len(existentes) >= max_n:
        print(f"Ya existen {len(existentes)} moleculas .mol2 divididas, reutilizando.")
        return existentes

    print("Dividiendo el SDF en moleculas .mol2 individuales (obabel dentro del contenedor backend)...")
    patron = f"uploads/{MOL2_PREFIX}.mol2"
    r = docker_exec("obabel", "-isdf", f"uploads/{SDF_LOCAL_NAME}", "-omol2", "-O", patron, "-m")
    if r.returncode != 0 and not (UPLOADS_DIR.glob(f"{MOL2_PREFIX}*.mol2")):
        sys.exit(f"Error al convertir el SDF a .mol2 con OpenBabel:\n{r.stdout}\n{r.stderr}")

    generados = sorted(
        (p for p in UPLOADS_DIR.glob(f"{MOL2_PREFIX}*.mol2") if _indice_mol2(p) != -1),
        key=_indice_mol2,
    )
    if not generados:
        sys.exit(f"OpenBabel no genero ningun archivo .mol2:\n{r.stdout}\n{r.stderr}")
    print(f"{len(generados)} moleculas .mol2 generadas en uploads/.")
    return generados


def obtener_o_crear_usuario() -> tuple:
    """Devuelve (usuario_id, cabeceras_con_token).

    Desde el endurecimiento de seguridad, /peticiones, /algoritmos y el sondeo
    de estado exigen un JWT, y subir un algoritmo exige ademas rol de
    desarrollador. El registro por si solo no basta: deja la cuenta sin
    verificar y con rol de usuario, asi que el script completa ambas cosas
    directamente contra la BD --es un bot de medicion, no un usuario real, y
    no hay buzon que confirmar.
    """
    r = requests.post(
        f"{API_URL}/registro",
        json={"email": TEST_EMAIL, "nombre": TEST_NOMBRE, "password_hash": TEST_PASSWORD},
        timeout=15,
    )
    if r.status_code == 200:
        print(f"Usuario de benchmark creado: {TEST_EMAIL}")
    elif r.status_code == 400:
        print(f"Usuario de benchmark ya existia: {TEST_EMAIL}")
    else:
        r.raise_for_status()

    # /registro no devuelve el id, y hay que verificar el correo y elevar el
    # rol antes de poder iniciar sesion y subir el algoritmo de medicion.
    snippet = (
        "from app.database import SessionLocal\n"
        "from app import models\n"
        "db = SessionLocal()\n"
        f"u = db.query(models.Usuario).filter(models.Usuario.email == '{TEST_EMAIL}').first()\n"
        "if u:\n"
        "    u.email_verificado = True\n"
        "    u.rol = models.RolUsuario.desarrollador\n"
        "    db.commit()\n"
        "print(u.id if u else '')\n"
    )
    r = docker_exec("python", "-c", snippet)
    salida = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    if not salida.isdigit():
        sys.exit(f"No se pudo preparar el usuario de benchmark.\nstdout: {r.stdout}\nstderr: {r.stderr}")
    usuario_id = int(salida)

    r = requests.post(
        f"{API_URL}/login",
        json={"email": TEST_EMAIL, "password_hash": TEST_PASSWORD},
        timeout=15,
    )
    if r.status_code != 200:
        sys.exit(f"No se pudo iniciar sesion como el usuario de benchmark: {r.status_code} {r.text}")
    cabeceras = {"Authorization": "Bearer " + r.json()["access_token"]}
    print(f"Sesion iniciada como {TEST_EMAIL} (id={usuario_id}).")
    return usuario_id, cabeceras


def obtener_o_crear_algoritmo(usuario_id: int, cabeceras: dict) -> int:
    # limit=500: el catalogo esta paginado (100 por defecto) y el algoritmo de
    # medicion puede haber quedado por detras de otros en tandas anteriores.
    r = requests.get(f"{API_URL}/algoritmos", params={"limit": 500},
                     headers=cabeceras, timeout=15)
    r.raise_for_status()
    for a in r.json():
        if a.get("ruta_archivo") == ALGORITMO_RUTA and a.get("autor_id") == usuario_id:
            print(f"Algoritmo filtroLipinski ya registrado (id={a['id']}), reutilizando.")
            return a["id"]

    ruta_script = PROJECT_ROOT / "algoritmos" / ALGORITMO_RUTA
    with open(ruta_script, "rb") as f:
        files = {"archivo": (ALGORITMO_RUTA, f, "text/x-python")}
        data = {
            "nombre": ALGORITMO_NOMBRE,
            "descripcion": "Filtro de Lipinski (Ro5) - usado para benchmarking de rendimiento",
            "tipo": "preprocesado",
            "es_publico": "true",
        }
        # El autor lo toma el backend del token, no de un campo del formulario.
        # La subida ejecuta ademas el banco de pruebas (app/banco_pruebas.py),
        # asi que este POST tarda unos segundos mas que antes.
        r = requests.post(f"{API_URL}/algoritmos", data=data, files=files,
                          headers=cabeceras, timeout=180)
    if r.status_code != 200:
        sys.exit(f"No se pudo registrar el algoritmo de medicion: {r.status_code} {r.text}")
    algoritmo_id = r.json()["id"]
    print(f"Algoritmo filtroLipinski registrado (id={algoritmo_id}).")
    return algoritmo_id


def ejecutar_lote(mol2_files: list, usuario_id: int, algoritmo_id: int,
                  n_workers: int, cabeceras: dict) -> dict:
    n = len(mol2_files)
    print(f"\n--- Lote de {n} moleculas (n_workers={n_workers}) ---")

    inicio = time.perf_counter()

    peticion_ids = []
    paso_log = max(1, n // 10)
    for i, ruta in enumerate(mol2_files, start=1):
        with open(ruta, "rb") as f:
            files = {"archivo_mol": (ruta.name, f, "chemical/x-mol2")}
            data = {"algoritmo_id": algoritmo_id}
            r = requests.post(f"{API_URL}/peticiones", data=data, files=files,
                              headers=cabeceras, timeout=30)
        r.raise_for_status()
        peticion_ids.append(r.json()["id"])
        if i % paso_log == 0 or i == n:
            print(f"  Peticiones enviadas: {i}/{n}")

    pendientes = set(peticion_ids)
    errores = 0
    intervalo = 0.5
    while pendientes:
        time.sleep(intervalo)
        intervalo = min(intervalo * 1.3, 3.0)
        for pid in list(pendientes):
            r = requests.get(f"{API_URL}/peticiones/{pid}/estado",
                             headers=cabeceras, timeout=15)
            r.raise_for_status()
            estado = r.json()["estado"]
            if estado in ("COMPLETADO", "ERROR"):
                pendientes.discard(pid)
                if estado == "ERROR":
                    errores += 1
        print(f"  Terminadas: {n - len(pendientes)}/{n} ({errores} con error)   ", end="\r")

    fin = time.perf_counter()
    print()

    if errores:
        print(f"  Aviso: {errores}/{n} peticiones terminaron en estado ERROR.")

    tiempo_total = fin - inicio
    return {
        "algoritmo": "filtroLipinski",
        "n_moleculas": n,
        "n_workers": n_workers,
        "tiempo_total_s": round(tiempo_total, 3),
        "tiempo_medio_por_molecula_s": round(tiempo_total / n, 4),
        "moleculas_por_segundo": round(n / tiempo_total, 3),
        "fecha": datetime.date.today().isoformat(),
    }


def guardar_resultado(fila: dict):
    existe = CSV_PATH.exists()
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not existe:
            writer.writeheader()
        writer.writerow(fila)


def imprimir_resumen(resultados: list):
    print("\n" + "=" * 72)
    print("RESUMEN DEL BENCHMARK")
    print("=" * 72)
    cab = f"{'moleculas':>10} | {'workers':>7} | {'tiempo (s)':>11} | {'s/molecula':>11} | {'mol/s':>10}"
    print(cab)
    print("-" * len(cab))
    for r in resultados:
        print(
            f"{r['n_moleculas']:>10} | {r['n_workers']:>7} | {r['tiempo_total_s']:>11.2f} | "
            f"{r['tiempo_medio_por_molecula_s']:>11.4f} | {r['moleculas_por_segundo']:>10.2f}"
        )
    print(f"\nResultados guardados/acumulados en: {CSV_PATH}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--workers", type=int, required=True,
        help="Numero de workers Celery activos ahora mismo (solo etiqueta el CSV; "
             "cambialo tu con 'docker compose up --scale worker=N' antes de ejecutar)",
    )
    parser.add_argument(
        "--batches", type=str, default="100,500,1000",
        help="Tamanos de lote a probar, separados por comas (por defecto: 100,500,1000)",
    )
    args = parser.parse_args()

    tamanos = sorted(int(x) for x in args.batches.split(","))
    max_n = max(tamanos)

    preflight()
    descargar_sdf()
    mol2_files = dividir_en_mol2(max_n)

    if len(mol2_files) < max_n:
        print(f"Aviso: solo hay {len(mol2_files)} moleculas validas disponibles (se pedian {max_n}).")
        tamanos = sorted(set(t for t in tamanos if t <= len(mol2_files)) | {len(mol2_files)})

    usuario_id, cabeceras = obtener_o_crear_usuario()
    algoritmo_id = obtener_o_crear_algoritmo(usuario_id, cabeceras)

    resultados = []
    for n in tamanos:
        fila = ejecutar_lote(mol2_files[:n], usuario_id, algoritmo_id, args.workers, cabeceras)
        guardar_resultado(fila)
        resultados.append(fila)

    imprimir_resumen(resultados)


if __name__ == "__main__":
    main()
