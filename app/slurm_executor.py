"""
Ejecución remota de algoritmos en el clúster Picasso (UAL) vía SSH + SLURM.

Se activa cuando EXECUTION_MODE=slurm (ver app/config.py). Expone la misma
interfaz que app.ejecutor._ejecutar_local: ejecutar_algoritmo(ruta_algoritmo, *archivos)
devolviendo {"exito": bool, "log": str, "error": str | None}.
"""

import os
import time
import uuid
import posixpath
import paramiko

from app.config import (
    SLURM_HOST, SLURM_PORT, SLURM_USER, SLURM_SSH_KEY_PATH, SLURM_PASSWORD,
    SLURM_REMOTE_DIR, SLURM_PARTITION, SLURM_TIME_LIMIT, SLURM_CPUS_PER_TASK,
    SLURM_MEM, SLURM_MODULES, SLURM_CONDA_ENV, SLURM_POLL_INTERVAL, SLURM_JOB_TIMEOUT,
)

# Estados terminales de un job según `sacct --format=State`
_ESTADOS_OK     = {"COMPLETED"}
_ESTADOS_FALLO  = {"FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL", "OUT_OF_MEMORY", "BOOT_FAIL", "DEADLINE"}


class SlurmExecutor:
    """
    Envía la ejecución de un algoritmo al clúster Picasso como un job SLURM.

    Flujo de ejecutar_algoritmo():
        1. Conecta por SSH al nodo de acceso del clúster.
        2. Crea un directorio remoto propio del job y sube el script + ficheros de entrada.
        3. Genera un script sbatch y lo envía con `sbatch`.
        4. Sondea el estado con `sacct` hasta que el job termina o expira el timeout.
        5. Descarga el log y los ficheros de salida, y cierra la conexión.
    """

    def __init__(self):
        self.host          = SLURM_HOST
        self.port          = SLURM_PORT
        self.user          = SLURM_USER
        self.key_path      = SLURM_SSH_KEY_PATH
        self.password      = SLURM_PASSWORD
        self.remote_base   = SLURM_REMOTE_DIR
        self.partition     = SLURM_PARTITION
        self.time_limit    = SLURM_TIME_LIMIT
        self.cpus          = SLURM_CPUS_PER_TASK
        self.mem           = SLURM_MEM
        self.modules       = [m.strip() for m in SLURM_MODULES.split(",") if m.strip()]
        self.conda_env     = SLURM_CONDA_ENV
        self.poll_interval = SLURM_POLL_INTERVAL
        self.job_timeout   = SLURM_JOB_TIMEOUT

    # ------------------------------------------------------------------
    # Conexión SSH
    # ------------------------------------------------------------------

    def _conectar(self) -> paramiko.SSHClient:
        if not self.user:
            raise ValueError("SLURM_USER no está configurado (ver app/config.py / .env)")
        if not self.key_path and not self.password:
            raise ValueError("Configura SLURM_SSH_KEY_PATH o SLURM_PASSWORD para conectar al clúster")

        cliente = paramiko.SSHClient()
        cliente.load_system_host_keys()
        # RejectPolicy (por defecto en SSHClient si no se fija ninguna, pero se
        # deja explícito): rechaza la conexión si la clave del host no está ya
        # en el known_hosts del sistema, en vez de confiar y guardar
        # silenciosamente cualquier clave que ofrezca el servidor
        # (AutoAddPolicy), que deja la conexión expuesta a un atacante en
        # la misma red haciéndose pasar por SLURM_HOST (MITM). La primera vez
        # que se conecte a un host nuevo hay que añadir su clave al
        # known_hosts del sistema explícitamente (p. ej. con
        # `ssh-keyscan -H <SLURM_HOST> >> ~/.ssh/known_hosts` tras verificar
        # la huella por un canal de confianza), igual que exige un cliente
        # SSH normal la primera vez.
        cliente.set_missing_host_key_policy(paramiko.RejectPolicy())

        kwargs = {"hostname": self.host, "port": self.port, "username": self.user, "timeout": 30}
        if self.key_path:
            kwargs["key_filename"] = self.key_path
        else:
            kwargs["password"] = self.password

        cliente.connect(**kwargs)
        return cliente

    # ------------------------------------------------------------------
    # Generación del script sbatch
    # ------------------------------------------------------------------

    def _generar_script_sbatch(self, remote_dir: str, comando: str) -> str:
        lineas = [
            "#!/bin/bash",
            "#SBATCH --job-name=tfg_vs",
            f"#SBATCH --partition={self.partition}",
            f"#SBATCH --time={self.time_limit}",
            f"#SBATCH --cpus-per-task={self.cpus}",
            f"#SBATCH --mem={self.mem}",
            f"#SBATCH --output={remote_dir}/slurm-%j.out",
            f"#SBATCH --error={remote_dir}/slurm-%j.err",
            "",
        ]
        for modulo in self.modules:
            lineas.append(f"module load {modulo}")
        if self.conda_env:
            lineas.append(f"source activate {self.conda_env}")
        lineas.append(f"cd {remote_dir}")
        lineas.append(comando)
        return "\n".join(lineas) + "\n"

    # ------------------------------------------------------------------
    # Ejecución principal
    # ------------------------------------------------------------------

    def ejecutar_algoritmo(self, ruta_algoritmo: str, *archivos) -> dict:
        cliente = None
        try:
            cliente = self._conectar()
            sftp = cliente.open_sftp()

            job_uid    = uuid.uuid4().hex[:10]
            remote_dir = posixpath.join(self.remote_base, f"job_{job_uid}")
            self._ejecutar_comando(cliente, f"mkdir -p {remote_dir}")

            # Subir el script del algoritmo
            remote_algoritmo = posixpath.join(remote_dir, os.path.basename(ruta_algoritmo))
            sftp.put(ruta_algoritmo, remote_algoritmo)

            # Subir los ficheros de entrada que existan localmente; los que no
            # existan se asumen ficheros de salida que generará el propio script.
            remote_archivos = []
            for archivo in archivos:
                remote_path = posixpath.join(remote_dir, os.path.basename(archivo))
                if os.path.exists(archivo):
                    sftp.put(archivo, remote_path)
                remote_archivos.append(remote_path)

            comando = "python3 {} {}".format(
                remote_algoritmo, " ".join(f'"{a}"' for a in remote_archivos)
            )
            script_sbatch = self._generar_script_sbatch(remote_dir, comando)

            remote_script_path = posixpath.join(remote_dir, "job.sbatch")
            with sftp.open(remote_script_path, "w") as f:
                f.write(script_sbatch.encode("utf-8"))

            salida_sbatch = self._ejecutar_comando(cliente, f"sbatch {remote_script_path}")
            job_id = self._parsear_job_id(salida_sbatch)

            estado_final = self._esperar_finalizacion(cliente, job_id)

            log = self._leer_archivo_remoto(sftp, posixpath.join(remote_dir, f"slurm-{job_id}.out"))
            err = self._leer_archivo_remoto(sftp, posixpath.join(remote_dir, f"slurm-{job_id}.err"))

            if estado_final not in _ESTADOS_OK:
                return {
                    "exito": False,
                    "log":   log,
                    "error": err or f"El job SLURM {job_id} terminó con estado {estado_final}",
                }

            # Descargar de vuelta a su ruta local original los ficheros que existan en remoto
            # (incluye las salidas que el algoritmo haya generado en el directorio del job)
            for archivo, remote_path in zip(archivos, remote_archivos):
                if self._existe_remoto(sftp, remote_path):
                    directorio_local = os.path.dirname(archivo)
                    if directorio_local:
                        os.makedirs(directorio_local, exist_ok=True)
                    sftp.get(remote_path, archivo)

            return {"exito": True, "log": log, "error": None}

        except Exception as e:
            return {"exito": False, "log": "", "error": str(e)}
        finally:
            if cliente:
                cliente.close()

    # ------------------------------------------------------------------
    # Utilidades SSH / SLURM
    # ------------------------------------------------------------------

    def _ejecutar_comando(self, cliente: paramiko.SSHClient, comando: str) -> str:
        _, stdout, stderr = cliente.exec_command(comando)
        salida = stdout.read().decode("utf-8", errors="ignore")
        error  = stderr.read().decode("utf-8", errors="ignore")
        codigo = stdout.channel.recv_exit_status()
        if codigo != 0:
            raise RuntimeError(f"Comando remoto falló ({comando}): {error or salida}")
        return salida

    def _parsear_job_id(self, salida_sbatch: str) -> str:
        # sbatch devuelve algo como: "Submitted batch job 123456"
        for token in salida_sbatch.split():
            if token.isdigit():
                return token
        raise RuntimeError(f"No se pudo extraer el job id de sbatch: {salida_sbatch!r}")

    def _esperar_finalizacion(self, cliente: paramiko.SSHClient, job_id: str) -> str:
        transcurrido = 0
        while transcurrido < self.job_timeout:
            salida = self._ejecutar_comando(
                cliente, f"sacct -j {job_id} --format=State --noheader --parsable2 -X"
            )
            primera_linea = salida.strip().splitlines()[0].strip() if salida.strip() else ""
            estado = primera_linea.split()[0] if primera_linea else ""

            if estado in _ESTADOS_OK or estado in _ESTADOS_FALLO:
                return estado

            time.sleep(self.poll_interval)
            transcurrido += self.poll_interval

        raise TimeoutError(f"El job SLURM {job_id} no terminó en {self.job_timeout}s")

    def _leer_archivo_remoto(self, sftp: paramiko.SFTPClient, ruta: str) -> str:
        try:
            with sftp.open(ruta, "r") as f:
                return f.read().decode("utf-8", errors="ignore")
        except IOError:
            return ""

    def _existe_remoto(self, sftp: paramiko.SFTPClient, ruta: str) -> bool:
        try:
            sftp.stat(ruta)
            return True
        except IOError:
            return False
