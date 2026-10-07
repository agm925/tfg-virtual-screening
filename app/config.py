import os
import secrets
import warnings

from dotenv import load_dotenv

load_dotenv()

# --- Autenticacion (JWT) ---
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if not JWT_SECRET_KEY:
    # Sin JWT_SECRET_KEY en .env, se genera una clave aleatoria por arranque:
    # el servicio sigue funcionando en desarrollo, pero todas las sesiones
    # se invalidan en cada reinicio del proceso (los tokens firmados con la
    # clave anterior dejan de verificar). Nunca debe pasar en produccion.
    JWT_SECRET_KEY = secrets.token_hex(32)
    warnings.warn(
        "JWT_SECRET_KEY no está definida en .env: se ha generado una clave "
        "aleatoria temporal. Las sesiones no sobrevivirán a un reinicio del "
        "backend. Define JWT_SECRET_KEY en .env antes de desplegar.",
        stacklevel=2,
    )
JWT_ALGORITHM      = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", str(60 * 24)))  # 24h por defecto

# --- CORS ---
# Origenes que pueden llamar a la API desde un navegador.
#
# Antes esto era allow_origins=["*"] junto a allow_credentials=True, una
# combinacion que la propia especificacion de CORS declara invalida, y que en
# la practica significaba que cualquier web podia llamar a esta API con un
# token robado. Ya no hace falta ninguna excepcion amplia: la SPA se sirve bajo
# el mismo origen que la API (proxy /api/ de nginx en produccion, proxy de Vite
# en desarrollo), asi que sus peticiones ni siquiera son cross-origin. La lista
# queda como valvula de escape para escenarios donde el frontend se sirva
# aparte; se separan por comas en la variable de entorno.
CORS_ORIGINS = [
    origen.strip()
    for origen in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
    ).split(",")
    if origen.strip()
]

# --- Direccion publica de la plataforma (spec 004) ---
# La que escribe el usuario en el navegador: https://rt.hpca.ual.es/molserver
# en el servidor RTX. Con ella se construyen los enlaces que el backend manda
# fuera (el del correo de verificacion, el boton de la pagina de cuenta
# confirmada). Antes eran http://localhost:8000 y http://localhost:5173 fijos,
# y en un servidor nadie podia activar su cuenta.
URL_PUBLICA_POR_DEFECTO = "http://localhost:5173"


def normalizar_url_publica(valor):
    """Sin espacios ni barra final: los enlaces le anaden la suya."""
    valor = (valor or "").strip().rstrip("/")
    return valor or URL_PUBLICA_POR_DEFECTO


PUBLIC_URL = normalizar_url_publica(os.getenv("PUBLIC_URL"))

# --- Cribado en lote ---
# Moleculas por subtarea Celery. El lote se reparte en bloques que se procesan
# EN PARALELO (ver ejecutar_workflow_batch_async): un bloque por subtarea, y un
# callback que consolida el ranking cuando todas terminan.
#
# El tamano es un compromiso. Bloques muy pequenos multiplican el coste fijo de
# encolar y recoger cada tarea; bloques muy grandes desaprovechan los workers,
# porque el lote no puede terminar antes que su bloque mas lento. 25 reparte
# bien un cribado de unos cientos de moleculas entre 4 workers.
BATCH_TAMANO_BLOQUE = int(os.getenv("BATCH_TAMANO_BLOQUE", "25"))

# --- Límites de subida de ficheros ---
# Tope de tamano por fichero subido. Se aplica mientras se escribe a disco
# (ver guardar_subida en app/main.py), no despues, que es lo unico que impide
# de verdad que una subida grande agote la memoria del proceso web.
# El valor por defecto acompana al client_max_body_size de nginx
# (frontend/nginx.conf): si nginx acepta 512 MB, la API no debe rechazar menos
# sin explicacion, ni al reves.
MAX_SUBIDA_MB = int(os.getenv("MAX_SUBIDA_MB", "512"))
MAX_SUBIDA_BYTES = MAX_SUBIDA_MB * 1024 * 1024

# Los algoritmos son scripts de Python: unos pocos KB. Un tope mucho mas bajo
# reduce la superficie de un endpoint que, por su naturaleza, acepta codigo
# que despues se ejecutara en el worker o en el nodo del cluster.
MAX_ALGORITMO_KB = int(os.getenv("MAX_ALGORITMO_KB", "512"))
MAX_ALGORITMO_BYTES = MAX_ALGORITMO_KB * 1024

# Tamano del trozo con que se leen las subidas y se cuentan los registros SDF.
TAMANO_TROZO_SUBIDA = 1024 * 1024   # 1 MiB

# --- Base de datos ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tfg_virtual_screening.db")

# --- Redis / Celery ---
REDIS_URL          = os.getenv("REDIS_URL", "redis://localhost:6379/0")
WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "1"))

# --- SMTP para notificaciones por correo ---
SMTP_HOST     = os.getenv("SMTP_HOST",     "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER",     "")   # tu cuenta Gmail
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")   # contraseña de aplicación
EMAIL_FROM    = os.getenv("EMAIL_FROM",    SMTP_USER)

# --- Modo de ejecución de algoritmos: "local" (subprocess) o "slurm" (clúster bullx, HPCA-UAL) ---
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "local")

# Tiempo máximo (segundos) que se le concede a un algoritmo en modo local antes
# de darlo por colgado y abortarlo. El equivalente en modo slurm es
# SLURM_JOB_TIMEOUT (más abajo), que ya existía; el modo local no tenía ninguno:
# subprocess.run() esperaba indefinidamente, así que con WORKER_CONCURRENCY=1
# (el valor por defecto) un único script que no terminase dejaba la cola de
# Celery bloqueada entera, sin más forma de recuperarla que matar el worker.
ALGORITMO_TIMEOUT = int(os.getenv("ALGORITMO_TIMEOUT", "1800"))   # 30 min

# --- Banco de pruebas de algoritmos ---
#
# URL del servicio aislado que ejecuta los algoritmos recien subidos para
# comprobarlos antes de aceptarlos (ver app/banco_pruebas.py y
# app/banco_servidor.py).
#
# Si esta vacia, el banco se ejecuta EN ESTE MISMO PROCESO. Eso es lo correcto
# para los tests y para usar el modulo como biblioteca, pero NO para un
# despliegue: significaria ejecutar codigo recien subido, y todavia no
# aceptado, con los privilegios y el entorno del backend --que incluye la clave
# de firma de los JWT y la contrasena de la base de datos--.
#
# En docker-compose.yml se fija BANCO_SOCKET, porque el contenedor del banco no
# tiene red en absoluto (network_mode "none") y se le habla por un socket Unix
# en un volumen compartido. BANCO_URL queda como alternativa por si algun dia
# el sandbox vive en otra maquina.
BANCO_SOCKET = os.getenv("BANCO_SOCKET", "").strip()
BANCO_URL = os.getenv("BANCO_URL", "").strip()

# --- SLURM / Clúster bullx (HPCA, Universidad de Almería) — solo se usan si EXECUTION_MODE=slurm ---
SLURM_HOST            = os.getenv("SLURM_HOST", "bullxual.hpca.ual.es")
SLURM_PORT            = int(os.getenv("SLURM_PORT", "22"))
SLURM_USER            = os.getenv("SLURM_USER", "")
SLURM_SSH_KEY_PATH    = os.getenv("SLURM_SSH_KEY_PATH", "")   # ruta a clave privada; vacío = usar password
SLURM_PASSWORD        = os.getenv("SLURM_PASSWORD", "")       # solo si no se usa clave SSH
SLURM_REMOTE_DIR      = os.getenv("SLURM_REMOTE_DIR", "/home/{user}/tfg_virtual_screening_jobs".format(user=SLURM_USER or "usuario"))
SLURM_PARTITION       = os.getenv("SLURM_PARTITION", "generic")
SLURM_TIME_LIMIT      = os.getenv("SLURM_TIME_LIMIT", "00:30:00")   # formato sbatch --time
SLURM_CPUS_PER_TASK   = int(os.getenv("SLURM_CPUS_PER_TASK", "1"))
SLURM_MEM             = os.getenv("SLURM_MEM", "4G")
SLURM_MODULES         = os.getenv("SLURM_MODULES", "")   # módulos a cargar, separados por coma (ej: "miniconda")
SLURM_CONDA_ENV       = os.getenv("SLURM_CONDA_ENV", "")   # entorno conda a activar en el nodo remoto
# Tareas de un job array que SLURM puede correr a la vez (el %K de
# --array=0-N%K). 0 las deja todas sueltas, que es lo que se quiere si el
# cluster esta libre; un valor bajo es lo educado si se comparte.
SLURM_ARRAY_THROTTLE  = int(os.getenv("SLURM_ARRAY_THROTTLE", "0"))
SLURM_POLL_INTERVAL   = int(os.getenv("SLURM_POLL_INTERVAL", "10"))   # segundos entre consultas a sacct
SLURM_JOB_TIMEOUT     = int(os.getenv("SLURM_JOB_TIMEOUT", "3600"))   # segundos máx. de espera total
