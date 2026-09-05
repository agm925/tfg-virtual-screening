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

# --- Modo de ejecución de algoritmos: "local" (subprocess) o "slurm" (clúster Picasso/UAL) ---
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "local")

# --- SLURM / Clúster Picasso (UAL) — solo se usan si EXECUTION_MODE=slurm ---
SLURM_HOST            = os.getenv("SLURM_HOST", "picasso.ual.es")
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
SLURM_POLL_INTERVAL   = int(os.getenv("SLURM_POLL_INTERVAL", "10"))   # segundos entre consultas a sacct
SLURM_JOB_TIMEOUT     = int(os.getenv("SLURM_JOB_TIMEOUT", "3600"))   # segundos máx. de espera total
