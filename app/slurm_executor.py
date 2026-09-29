"""
Ejecución remota de algoritmos en el clúster bullx (HPCA, Universidad de Almería) vía SSH + SLURM.

Se activa cuando EXECUTION_MODE=slurm (ver app/config.py). Expone la misma
interfaz que app.ejecutor._ejecutar_local:
ejecutar_algoritmo(ruta_algoritmo, *archivos, flags=()) devolviendo
{"exito": bool, "log": str, "error": str | None}.

La distinción entre `archivos` y `flags` importa aquí más que en local: los
primeros viajan al nodo y se sustituyen por su ruta remota, los segundos se
pasan literalmente (ver ejecutar_algoritmo en app/ejecutor.py).
"""

import os
import random
import shlex
import stat
import time
import uuid
import posixpath
import paramiko

from app.config import (
    SLURM_HOST, SLURM_PORT, SLURM_USER, SLURM_SSH_KEY_PATH, SLURM_PASSWORD,
    SLURM_REMOTE_DIR, SLURM_PARTITION, SLURM_TIME_LIMIT, SLURM_CPUS_PER_TASK,
    SLURM_MEM, SLURM_MODULES, SLURM_CONDA_ENV, SLURM_POLL_INTERVAL, SLURM_JOB_TIMEOUT,
    SLURM_ARRAY_THROTTLE,
)

# Estados terminales de un job según `squeue -o %T` / `scontrol show job`
#
# Antes se sondeaba `sacct`, que los da todos y de forma póstuma. No sirve
# aquí: el bullx no tiene slurmdbd levantado --`sacct` contesta "Problem
# talking to the database: Connection refused"-- y la contabilidad es un
# servicio opcional que cada centro decide desplegar o no. `squeue` y
# `scontrol` los sirve el propio slurmctld, que está siempre.
_ESTADOS_OK     = {"COMPLETED"}
_ESTADOS_FALLO  = {"FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL", "OUT_OF_MEMORY", "BOOT_FAIL", "DEADLINE"}

# Centinela con el código de salida del algoritmo, escrito por el propio job.
_ARCHIVO_CODIGO = "job.rc"

# Primera espera entre sondeos, en segundos. Desde ahi se dobla hasta
# SLURM_POLL_INTERVAL (ver _esperar_finalizacion).
_ESPERA_INICIAL = 1.0

# Intentos de conexion SSH antes de dar el job por fallido, y espera base
# entre ellos (ver _conectar).
_INTENTOS_CONEXION = 4
_ESPERA_REINTENTO = 1.0

# Tareas maximas por array. SLURM lo limita con MaxArraySize (1001 en el
# bullx, `scontrol show config`), asi que un lote mayor se parte en varios.
_MAX_TAREAS_ARRAY = 1000


class SlurmExecutor:
    """
    Envía la ejecución de un algoritmo al clúster bullx como un job SLURM.

    Flujo de ejecutar_algoritmo():
        1. Conecta por SSH al nodo de acceso del clúster.
        2. Crea un directorio remoto propio del job y sube el script + ficheros de entrada.
        3. Genera un script sbatch y lo envía con `sbatch`.
        4. Sondea el estado con `squeue`/`scontrol` hasta que el job termina o expira el timeout.
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
        self.array_throttle = SLURM_ARRAY_THROTTLE
        self.job_timeout   = SLURM_JOB_TIMEOUT

    # ------------------------------------------------------------------
    # Conexión SSH
    # ------------------------------------------------------------------

    def _conectar(self) -> paramiko.SSHClient:
        if not self.user:
            raise ValueError("SLURM_USER no está configurado (ver app/config.py / .env)")
        if not self.key_path and not self.password:
            raise ValueError("Configura SLURM_SSH_KEY_PATH o SLURM_PASSWORD para conectar al clúster")

        kwargs = {"hostname": self.host, "port": self.port, "username": self.user, "timeout": 30}
        if self.key_path:
            kwargs["key_filename"] = self.key_path
        else:
            kwargs["password"] = self.password

        # Se reintenta porque el cribado abre una conexion POR MOLECULA y las
        # lanza a la vez. sshd limita los saludos simultaneos sin autenticar
        # (MaxStartups, 10 por defecto) y a partir de ahi va rechazando: con 11
        # moleculas en paralelo contra el bullx ya se perdio una, que aparecio
        # en el ranking como molecula fallida --"Error reading SSH protocol
        # banner"-- sin tener nada de malo. Un saludo rechazado es una
        # condicion de carrera, no un resultado.
        #
        # La espera lleva un componente aleatorio a proposito: sin el, todos
        # los workers que se quedaron fuera volverian a la vez y chocarian otra
        # vez entre ellos.
        ultimo_error = None
        for intento in range(_INTENTOS_CONEXION):
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

            try:
                cliente.connect(**kwargs)
                return cliente
            except (paramiko.BadHostKeyException, paramiko.AuthenticationException):
                # Estas dos NO se reintentan. Una clave de host que no cuadra es
                # justo la senal que RejectPolicy existe para dar, y unas
                # credenciales que no valen no van a valer a la cuarta: repetir
                # solo retrasaria el error y, con una contrasena, acercaria la
                # cuenta a un bloqueo por intentos fallidos.
                cliente.close()
                raise
            except (paramiko.SSHException, EOFError, OSError) as e:
                ultimo_error = e
                cliente.close()
                if intento == _INTENTOS_CONEXION - 1:
                    break
                time.sleep(_ESPERA_REINTENTO * (2 ** intento) + random.uniform(0, 0.5))

        raise ConnectionError(
            f"No se pudo conectar a {self.host}:{self.port} tras "
            f"{_INTENTOS_CONEXION} intentos: {ultimo_error}") from ultimo_error

    # ------------------------------------------------------------------
    # Generación del script sbatch
    # ------------------------------------------------------------------

    def _lineas_entorno(self) -> list:
        """Las ordenes que dejan al nodo con el entorno del algoritmo listo."""
        lineas = [f"module load {modulo}" for modulo in self.modules]
        if self.conda_env:
            lineas.append(f"source activate {self.conda_env}")
        return lineas

    def _generar_script_sbatch(self, remote_dir: str, comando: str) -> str:
        lineas = [
            # -l (shell de login) y no un bash pelado: en un cluster con lmod,
            # `module` es una funcion que define /etc/profile.d. Sin ella, el
            # "module load" de abajo no existe, no se activa el entorno conda y el
            # job corre con el python del sistema --sin RDKit-- fallando por una
            # razon que no tiene nada que ver con el algoritmo.
            "#!/bin/bash -l",
            "#SBATCH --job-name=tfg_vs",
            f"#SBATCH --partition={self.partition}",
            f"#SBATCH --time={self.time_limit}",
            f"#SBATCH --cpus-per-task={self.cpus}",
            f"#SBATCH --mem={self.mem}",
            f"#SBATCH --output={remote_dir}/slurm-%j.out",
            f"#SBATCH --error={remote_dir}/slurm-%j.err",
            "",
        ]
        lineas += self._lineas_entorno()
        lineas.append(f"cd {shlex.quote(remote_dir)}")
        lineas.append(comando)

        # El job deja escrito su propio código de salida. Es la red de
        # seguridad de _consultar_estado: si cuando se pregunta el job ya no
        # está ni en la cola ni en la memoria de slurmctld (MinJobAge, 300 s
        # por defecto), este fichero es lo único que queda para distinguir
        # "terminó bien" de "lo mataron".
        centinela = posixpath.join(remote_dir, _ARCHIVO_CODIGO)
        lineas.append("codigo=$?")
        lineas.append(f'echo "${{codigo}}" > {shlex.quote(centinela)}')
        lineas.append('exit "${codigo}"')
        return "\n".join(lineas) + "\n"


    def _preparar_tarea(self, sftp, remote_dir: str, ruta_algoritmo: str,
                        archivos, flags) -> tuple:
        """
        Sube a `remote_dir` el script y sus entradas, y devuelve
        (comando, rutas remotas de los ficheros, opciones ya reescritas).

        Esta aqui y no en linea porque lo usan los dos caminos --un job
        suelto y una tarea de un array-- y es justo donde estaban los dos
        fallos que solo se veian en el cluster: que las opciones viajaran
        como si fueran ficheros, y el entrecomillado de nombres que elige
        quien sube la molecula. Duplicarlo seria arreglarlo una vez y
        romperlo en el otro sitio.
        """
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

        # Las opciones van APARTE de los ficheros (ver ejecutar_algoritmo en
        # app/ejecutor.py) y viajan literalmente: convertirlas en rutas
        # remotas, como se hacía cuando venían mezcladas con los ficheros,
        # las volvía irreconocibles para el script.
        #
        # La excepción es una opción cuyo VALOR sí es un fichero
        # --"--referencia molecula.sdf" en dockingSmina--: ese hay que
        # subirlo y sustituirlo por su ruta en el nodo, o el algoritmo
        # buscaría en el clúster una ruta que solo existe en el backend.
        remote_flags = []
        for flag in flags:
            flag = str(flag)
            if os.path.isfile(flag):
                remote_path = posixpath.join(remote_dir, os.path.basename(flag))
                sftp.put(flag, remote_path)
                remote_flags.append(remote_path)
            else:
                remote_flags.append(flag)

        # shlex.quote, y no comillas dobles puestas a mano. El nombre de
        # estos ficheros lo elige quien sube la molécula --el endpoint solo
        # le aplica os.path.basename, ver app/main.py-- y acaba interpolado
        # en el cuerpo de un script bash. Entre comillas DOBLES bash sigue
        # expandiendo $(...) y las comillas invertidas, así que una molécula
        # llamada `ligando$(lo que sea).sdf` no necesitaba ni escapar una
        # comilla para ejecutar comandos arbitrarios en el nodo del clúster,
        # con la cuenta con la que se envía el job. shlex.quote envuelve en
        # comillas SIMPLES y escapa, donde no queda ninguna expansión viva.
        # Vale igual para las opciones: su valor sale de un nodo del grafo,
        # que lo manda el cliente.
        comando = "python3 {} {}".format(
            shlex.quote(remote_algoritmo),
            " ".join(shlex.quote(a) for a in (*remote_archivos, *remote_flags)),
        )
        return comando, remote_archivos, remote_flags

    # ------------------------------------------------------------------
    # Ejecución principal
    # ------------------------------------------------------------------

    def ejecutar_algoritmo(self, ruta_algoritmo: str, *archivos, flags=()) -> dict:
        cliente = None
        try:
            cliente = self._conectar()
            sftp = cliente.open_sftp()

            job_uid    = uuid.uuid4().hex[:10]
            remote_dir = posixpath.join(self.remote_base, f"job_{job_uid}")
            self._ejecutar_comando(cliente, f"mkdir -p {shlex.quote(remote_dir)}")

            comando, remote_archivos, remote_flags = self._preparar_tarea(
                sftp, remote_dir, ruta_algoritmo, archivos, flags)
            remote_algoritmo = posixpath.join(remote_dir, os.path.basename(ruta_algoritmo))

            script_sbatch = self._generar_script_sbatch(remote_dir, comando)

            remote_script_path = posixpath.join(remote_dir, "job.sbatch")
            with sftp.open(remote_script_path, "w") as f:
                f.write(script_sbatch.encode("utf-8"))

            salida_sbatch = self._ejecutar_comando(
                cliente, f"sbatch {shlex.quote(remote_script_path)}")
            job_id = self._parsear_job_id(salida_sbatch)

            estado_final = self._esperar_finalizacion(cliente, job_id, remote_dir)

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

            log += self._descargar_extras(
                sftp, remote_dir, archivos,
                conocidos={remote_algoritmo, remote_script_path, *remote_archivos, *remote_flags},
                job_id=job_id,
            )

            return {"exito": True, "log": log, "error": None}

        except Exception as e:
            return {"exito": False, "log": "", "error": str(e)}
        finally:
            if cliente:
                cliente.close()

    # ------------------------------------------------------------------
    # Ejecucion en lote: un job array para N invocaciones
    # ------------------------------------------------------------------

    def ejecutar_lote(self, invocaciones) -> list:
        """
        Ejecuta N invocaciones independientes como UN job array de SLURM.

        `invocaciones` es una lista de (ruta_algoritmo, archivos, flags), y se
        devuelve una lista de resultados con la misma forma que los de
        ejecutar_algoritmo, uno por invocacion y en el mismo orden.

        Por que existe, teniendo ya ejecutar_algoritmo: porque el coste de un
        job no esta en el nodo de computo sino alrededor. Cada invocacion
        suelta abre su conexion SSH, su sesion SFTP, manda su sbatch y OCUPA UN
        PROCESO LOCAL esperando a que termine. Cribar una biblioteca asi
        significa que el paralelismo real no lo decide el cluster --con sus
        catorce nodos-- sino cuantos procesos Celery caben en la maquina que
        lanza; y de paso apalea el nodo de acceso, que es compartido: con once
        conexiones a la vez contra el bullx, sshd ya rechazo una (MaxStartups).

        Un array le da la vuelta: una conexion, una subida, UN sbatch con N
        tareas y UNA espera. Cuantas corren a la vez lo decide SLURM, que para
        eso sabe que nodos hay libres.

        Igual que ejecutar_algoritmo, no levanta excepciones: un fallo que
        afecte al lote entero se devuelve como N resultados fallidos, porque
        quien llama esta procesando moleculas y necesita saber cuales.
        """
        invocaciones = list(invocaciones)
        if not invocaciones:
            return []

        # Un lote mayor que MaxArraySize lo rechazaria sbatch entero, asi que
        # se parte. Las partes van una detras de otra: dentro de cada una el
        # paralelismo ya lo pone el cluster.
        if len(invocaciones) > _MAX_TAREAS_ARRAY:
            resultados = []
            for i in range(0, len(invocaciones), _MAX_TAREAS_ARRAY):
                resultados += self.ejecutar_lote(invocaciones[i:i + _MAX_TAREAS_ARRAY])
            return resultados

        cliente = None
        try:
            cliente = self._conectar()
            sftp = cliente.open_sftp()

            n = len(invocaciones)
            lote_dir = posixpath.join(self.remote_base, f"lote_{uuid.uuid4().hex[:10]}")

            # Los N directorios en una sola orden remota. Las llaves NO van
            # entrecomilladas: es la expansion de bash la que crea las N rutas.
            self._ejecutar_comando(
                cliente,
                "mkdir -p " + shlex.quote(lote_dir) + "/tarea_{0.." + str(n - 1) + "}")

            tareas = []
            for i, (ruta_algoritmo, archivos, flags) in enumerate(invocaciones):
                tarea_dir = posixpath.join(lote_dir, f"tarea_{i}")
                comando, remote_archivos, remote_flags = self._preparar_tarea(
                    sftp, tarea_dir, ruta_algoritmo, archivos, flags)

                # Cada tarea lleva su orden en un fichero en vez de dentro del
                # sbatch. Asi el script del array es uno solo, y no hay que
                # meter N ordenes --con nombres de fichero que elige el
                # usuario-- en un case de bash.
                ruta_run = posixpath.join(tarea_dir, "run.sh")
                with sftp.open(ruta_run, "w") as f:
                    f.write(("cd " + shlex.quote(tarea_dir) + chr(10)
                             + comando + chr(10)).encode("utf-8"))

                tareas.append({
                    "dir": tarea_dir,
                    "archivos": archivos,
                    "remote_archivos": remote_archivos,
                    "conocidos": {
                        posixpath.join(tarea_dir, os.path.basename(ruta_algoritmo)),
                        ruta_run, *remote_archivos, *remote_flags,
                    },
                })

            ruta_script = posixpath.join(lote_dir, "array.sbatch")
            with sftp.open(ruta_script, "w") as f:
                f.write(self._generar_script_array(lote_dir, n).encode("utf-8"))

            job_id = self._parsear_job_id(
                self._ejecutar_comando(cliente, f"sbatch {shlex.quote(ruta_script)}"))

            self._esperar_lote(cliente, job_id, n)
            codigos = self._codigos_del_lote(cliente, lote_dir, n)

            return [self._recoger_tarea(sftp, tarea, job_id, i, codigos[i])
                    for i, tarea in enumerate(tareas)]

        except Exception as e:  # noqa: BLE001
            return [{"exito": False, "log": "", "error": str(e)} for _ in invocaciones]
        finally:
            if cliente:
                cliente.close()

    def _generar_script_array(self, lote_dir: str, n: int) -> str:
        rango = f"0-{n - 1}"
        if self.array_throttle > 0:
            # %K limita cuantas tareas del array corren a la vez. El cluster es
            # de todos y un cribado de mil moleculas puede llenarlo entero.
            rango += f"%{self.array_throttle}"

        lineas = [
            "#!/bin/bash -l",
            "#SBATCH --job-name=tfg_vs",
            f"#SBATCH --partition={self.partition}",
            f"#SBATCH --time={self.time_limit}",
            f"#SBATCH --cpus-per-task={self.cpus}",
            f"#SBATCH --mem={self.mem}",
            f"#SBATCH --array={rango}",
            # %A es el id del array y %a el indice de la tarea: cada una escribe
            # en su propio directorio y no se pisan.
            f"#SBATCH --output={lote_dir}/tarea_%a/slurm-%A_%a.out",
            f"#SBATCH --error={lote_dir}/tarea_%a/slurm-%A_%a.err",
            "",
        ]
        lineas += self._lineas_entorno()
        lineas += [
            "tarea=" + shlex.quote(lote_dir) + "/tarea_${SLURM_ARRAY_TASK_ID}",
            'bash "${tarea}/run.sh"',
            "codigo=$?",
            'echo "${codigo}" > "${tarea}/' + _ARCHIVO_CODIGO + '"',
            'exit "${codigo}"',
        ]
        return chr(10).join(lineas) + chr(10)

    def _esperar_lote(self, cliente: paramiko.SSHClient, job_id: str, n: int) -> None:
        """
        Espera a que no quede ninguna tarea del array en la cola.

        A diferencia de un job suelto, aqui no se busca un estado: mientras
        `squeue` devuelva algo para ese id quedan tareas vivas, y cuando deja de
        devolver nada han terminado todas. El veredicto de cada una lo da su
        centinela, que es lo que lee _codigos_del_lote.
        """
        espera = min(_ESPERA_INICIAL, self.poll_interval)
        transcurrido = 0.0
        while transcurrido < self.job_timeout:
            salida, error, codigo = self._ejecutar_tolerante(
                cliente, f"squeue -h -j {shlex.quote(job_id)} -o %T")

            if codigo == 0 and not salida.strip():
                return
            if codigo != 0 and "Invalid job id" in (error + salida):
                return

            time.sleep(espera)
            transcurrido += espera
            espera = min(espera * 2, self.poll_interval)

        raise TimeoutError(
            f"El array SLURM {job_id} ({n} tareas) no termino en {self.job_timeout}s")

    def _codigos_del_lote(self, cliente: paramiko.SSHClient, lote_dir: str, n: int) -> list:
        """
        Los N codigos de salida, en orden, en una sola orden remota.

        El printf es para que cada tarea ocupe SIEMPRE una linea, tenga o no
        centinela: si a una le faltara y se saltara su linea, los resultados
        siguientes se leerian corridos y se le atribuirian a la molecula
        equivocada, que es peor que no tenerlos.
        """
        orden = ('for i in $(seq 0 ' + str(n - 1) + '); do printf \'%s\\n\' "$(cat '
                 + shlex.quote(lote_dir) + "/tarea_$i/" + _ARCHIVO_CODIGO
                 + ' 2>/dev/null || echo NA)"; done')
        salida, _, _ = self._ejecutar_tolerante(cliente, orden)

        codigos = salida.split(chr(10))
        codigos += ["NA"] * max(0, n - len(codigos))
        return codigos[:n]

    def _recoger_tarea(self, sftp, tarea: dict, job_id: str, indice: int, codigo: str) -> dict:
        """Log, veredicto y ficheros de vuelta de UNA tarea del array."""
        base = posixpath.join(tarea["dir"], f"slurm-{job_id}_{indice}")
        log = self._leer_archivo_remoto(sftp, base + ".out")
        err = self._leer_archivo_remoto(sftp, base + ".err")

        if codigo.strip() != "0":
            visto = codigo.strip() or "desconocido"
            return {
                "exito": False,
                "log":   log,
                "error": err or f"La tarea {indice} del array {job_id} termino con codigo {visto}",
            }

        for archivo, remote_path in zip(tarea["archivos"], tarea["remote_archivos"]):
            if self._existe_remoto(sftp, remote_path):
                directorio_local = os.path.dirname(archivo)
                if directorio_local:
                    os.makedirs(directorio_local, exist_ok=True)
                sftp.get(remote_path, archivo)

        log += self._descargar_extras(
            sftp, tarea["dir"], tarea["archivos"],
            conocidos=tarea["conocidos"], job_id=job_id, indice_array=indice)

        return {"exito": True, "log": log, "error": None}


    def _descargar_extras(self, sftp, remote_dir: str, archivos, conocidos: set,
                          job_id: str, indice_array: int = None) -> str:
        """
        Trae los ficheros que el algoritmo ha creado por su cuenta en el
        directorio del job, más allá de los que se le pasaron como argumentos.

        Hace falta porque no todo lo que produce un algoritmo es un argumento.
        El caso que lo motiva es dockingSmina.py, que además de las poses
        escribe un `<salida>_energias.json` con las afinidades, derivando el
        nombre de su ruta de salida. Al descargar solo los argumentos, ese
        fichero se quedaba en el clúster: el motor lo buscaba en local, no lo
        encontraba y seguía con `energias = {}` (ver app/workflow_executor.py).
        El efecto no era un error sino algo peor --el ranking del cribado por
        lotes saca de ahí el score de docking, así que el CSV habría salido
        con todas las afinidades a null-- y en modo local no pasaba, porque
        ahí el fichero ya está donde tiene que estar.

        Se descarta lo que hemos puesto nosotros (el script, las entradas, el
        sbatch) y lo que pone SLURM (los .out/.err del propio job).

        El nombre remoto se pasa por os.path.basename antes de construir la
        ruta local: lo escribe código subido por un usuario, y esto escribe en
        uploads/. Un fallo al traer un extra no invalida el resultado, así que
        se anota en el log y se sigue.
        """
        destino = os.path.dirname(archivos[-1]) if archivos else "."
        ignorar = {posixpath.basename(p) for p in conocidos}
        ignorar |= {f"slurm-{job_id}.out", f"slurm-{job_id}.err"}
        if indice_array is not None:
            # En un array los ficheros de SLURM llevan ademas el indice
            # de la tarea (--output=...slurm-%A_%a.out), asi que con el
            # nombre de un job suelto no se reconocerian y acabarian
            # descargados en uploads/ como si fueran resultados.
            ignorar |= {f"slurm-{job_id}_{indice_array}.out",
                        f"slurm-{job_id}_{indice_array}.err"}
        # El centinela del código de salida lo pone el sbatch, no el algoritmo.
        ignorar.add(_ARCHIVO_CODIGO)

        avisos = []
        try:
            # listdir_attr y no listdir: trae nombre y metadatos de una vez, y
            # permite saltarse los subdirectorios sin una consulta por entrada.
            entradas = sftp.listdir_attr(remote_dir)
        except Exception as e:  # noqa: BLE001
            return f"\n[slurm] no se pudo listar {remote_dir}: {e}"

        for entrada in entradas:
            nombre = entrada.filename
            if nombre in ignorar or not stat.S_ISREG(entrada.st_mode or 0):
                continue
            remote_path = posixpath.join(remote_dir, nombre)
            local_path = os.path.join(destino, os.path.basename(nombre))
            try:
                sftp.get(remote_path, local_path)
            except Exception as e:  # noqa: BLE001
                avisos.append(f"\n[slurm] no se pudo traer {nombre}: {e}")

        return "".join(avisos)

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

    def _ejecutar_tolerante(self, cliente: paramiko.SSHClient, comando: str):
        """
        Como _ejecutar_comando, pero devuelve (salida, error, código) en vez de
        levantar una excepción cuando el comando termina mal.

        Lo pide el sondeo de estado: preguntarle a SLURM por un job que ya no
        existe devuelve código distinto de cero, y ahí eso no es un error sino
        parte de la respuesta.
        """
        _, stdout, stderr = cliente.exec_command(comando)
        salida = stdout.read().decode("utf-8", errors="ignore")
        error  = stderr.read().decode("utf-8", errors="ignore")
        return salida, error, stdout.channel.recv_exit_status()

    def _parsear_job_id(self, salida_sbatch: str) -> str:
        # sbatch devuelve algo como: "Submitted batch job 123456"
        for token in salida_sbatch.split():
            if token.isdigit():
                return token
        raise RuntimeError(f"No se pudo extraer el job id de sbatch: {salida_sbatch!r}")

    def _esperar_finalizacion(self, cliente: paramiko.SSHClient, job_id: str,
                              remote_dir: str) -> str:
        # La espera entre sondeos empieza corta y va creciendo hasta
        # poll_interval, en vez de ser ese valor desde el principio.
        #
        # El motivo es que aqui conviven dos escalas muy distintas. Un
        # docking puede tardar media hora, y para el preguntar cada 10 s esta
        # bien: mas a menudo solo seria castigar al nodo de acceso. Pero un
        # Tanimoto o un Lipinski sobre una molecula tardan UN segundo, y con
        # el intervalo fijo cada uno costaba los 10 s enteros de la primera
        # espera. Eso no se nota en una peticion suelta y se nota mucho en un
        # cribado, donde el lote recorre las moleculas en serie: medido contra
        # el bullx, 11 moleculas tardaban 165 s de los que ~110 eran dormir.
        espera = min(_ESPERA_INICIAL, self.poll_interval)
        transcurrido = 0.0
        while transcurrido < self.job_timeout:
            estado = self._consultar_estado(cliente, job_id, remote_dir)

            if estado in _ESTADOS_OK or estado in _ESTADOS_FALLO:
                return estado

            time.sleep(espera)
            transcurrido += espera
            espera = min(espera * 2, self.poll_interval)

        raise TimeoutError(f"El job SLURM {job_id} no terminó en {self.job_timeout}s")

    def _consultar_estado(self, cliente: paramiko.SSHClient, job_id: str,
                          remote_dir: str) -> str:
        """
        Estado del job, preguntando por orden a las tres fuentes que lo saben:

            1. `squeue`, mientras el job siga en la cola (PENDING, RUNNING...).
            2. `scontrol show job`, durante los MinJobAge segundos que
               slurmctld sigue recordándolo después de terminar --300 por
               defecto, frente a los 10 del sondeo: margen de sobra--.
            3. el centinela job.rc que escribe el propio sbatch, para cuando
               ni siquiera eso queda.

        Devuelve "" cuando todavía no hay respuesta fiable, y quien llama
        vuelve a preguntar en el siguiente sondeo. Esa distinción es el
        motivo de que esto no sea una sola orden: un fallo puntual de red o un
        slurmctld ocupado no pueden confundirse con "el job ha fallado", o una
        petición perfectamente sana se daría por perdida.
        """
        salida, error, codigo = self._ejecutar_tolerante(
            cliente, f"squeue -h -j {shlex.quote(job_id)} -o %T")
        if codigo == 0 and salida.strip():
            return salida.strip().splitlines()[0].strip()
        if codigo != 0 and "Invalid job id" not in (error + salida):
            # Ha fallado por algo que no es "ese job ya no existe": se reintenta.
            return ""

        salida, _, codigo = self._ejecutar_tolerante(
            cliente, f"scontrol show job {shlex.quote(job_id)}")
        if codigo == 0:
            for token in salida.split():
                if token.startswith("JobState="):
                    return token.split("=", 1)[1]

        salida, _, codigo = self._ejecutar_tolerante(
            cliente, f"cat {shlex.quote(posixpath.join(remote_dir, _ARCHIVO_CODIGO))}")
        if codigo == 0 and salida.strip().isdigit():
            return "COMPLETED" if salida.strip() == "0" else "FAILED"

        # El job se envió, ya no lo conoce nadie y no dejó código de salida:
        # se quedó sin escribirlo (cancelado, sin memoria, nodo caído).
        return "FAILED"

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
