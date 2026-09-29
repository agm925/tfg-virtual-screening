"""
Tests de app/slurm_executor.py con un doble de SSH/SFTP.

No hace falta el cluster: lo que se comprueba es como se CONSTRUYE el trabajo
--que argumentos acaban en la linea de comandos del nodo y que ficheros van y
vuelven--, que es exactamente donde estaban los dos fallos que estos tests
fijan. Los dos fallaban en silencio y solo en modo slurm, asi que sin esto no
se descubren hasta estar ejecutando en el bullx y mirando resultados raros:

  1. Las opciones viajaban mezcladas con los ficheros, asi que se convertian
     en rutas remotas: "--exhaustiveness" llegaba como
     "/.../job_abc/--exhaustiveness" y dockingSmina.py, que las detecta con
     startswith("--"), las descartaba y corria con sus valores por defecto.

  2. Solo se descargaban de vuelta los ficheros que se habian pasado como
     argumento, de modo que el "<salida>_energias.json" que dockingSmina
     escribe por su cuenta se quedaba en el cluster. El motor no lo encontraba
     y seguia con energias={}, y de ahi sale el score del cribado por lotes:
     el ranking habria salido entero a null.

  3. El estado del job se sondeaba con `sacct`, que necesita slurmdbd. El
     bullx no lo tiene levantado, asi que ahi no contesta nunca: todo job
     terminaba en TimeoutError al agotar SLURM_JOB_TIMEOUT. Ahora se pregunta
     a squeue y scontrol, que los sirve slurmctld, con el codigo de salida
     que el propio sbatch deja escrito como ultimo recurso.
"""
import os
import shlex
import stat
from types import SimpleNamespace

import paramiko
import pytest

from app import slurm_executor
from app.slurm_executor import SlurmExecutor

MODO_FICHERO_REGULAR = stat.S_IFREG | 0o644


class _FicheroRemoto:
    """Lo minimo que usa _leer_archivo_remoto: un context manager con read()."""

    def __init__(self, contenido: bytes):
        self._contenido = contenido

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self._contenido

    def write(self, datos):
        self._contenido = datos


class FakeSFTP:
    """
    Doble de paramiko.SFTPClient que anota todo lo que se le pide.

    `remotos` simula el contenido del nodo: lo que ya esta ahi antes de
    empezar mas lo que el job "genera", que en un test se siembra a mano.
    """

    def __init__(self, genera_al_terminar=None):
        self.remotos = {}
        self.subidos = {}          # ruta_remota -> ruta_local
        self.descargados = []      # (ruta_remota, ruta_local)
        self.escritos = {}         # ruta_remota -> bytes
        self._genera = genera_al_terminar or {}

    # --- API de paramiko que usa SlurmExecutor ---

    def put(self, local, remote):
        self.subidos[remote] = local
        self.remotos[remote] = b"contenido subido"

    def get(self, remote, local):
        if remote not in self.remotos:
            raise IOError(f"no existe: {remote}")
        with open(local, "wb") as f:
            f.write(self.remotos[remote])
        self.descargados.append((remote, local))

    def open(self, ruta, modo="r"):
        if "w" in modo:
            fichero = _FicheroRemoto(b"")
            self.escritos[ruta] = fichero
            self.remotos[ruta] = b"sbatch"
            return fichero
        if ruta not in self.remotos:
            raise IOError(f"no existe: {ruta}")
        return _FicheroRemoto(self.remotos[ruta])

    def stat(self, ruta):
        if ruta not in self.remotos:
            raise IOError(f"no existe: {ruta}")
        return SimpleNamespace(st_mode=MODO_FICHERO_REGULAR)

    def listdir_attr(self, directorio):
        entradas = []
        for ruta in self.remotos:
            if os.path.dirname(ruta.replace("\\", "/")) == directorio:
                entradas.append(SimpleNamespace(
                    filename=ruta.rsplit("/", 1)[-1],
                    st_mode=MODO_FICHERO_REGULAR,
                ))
        return entradas

    # --- utilidad del test ---

    def sembrar_salida_del_job(self, remote_dir):
        """Simula lo que el algoritmo deja escrito en el directorio del job."""
        for nombre, contenido in self._genera.items():
            self.remotos[f"{remote_dir}/{nombre}"] = contenido


class FakeSSH:
    def __init__(self, sftp):
        self._sftp = sftp
        self.comandos = []
        self.remote_dir = None
        # Codigo con el que "termina" el algoritmo dentro del job.
        self.codigo_salida_job = 0
        # Respuestas al sondeo de estado, como (salida, error, codigo). Por
        # defecto se imita al bullx: el job ya salio de la cola y quien
        # contesta es scontrol, porque alli no hay contabilidad que consultar.
        self.respuestas_squeue = [("", "", 0)]
        self.respuestas_scontrol = [("JobId=12345 JobState=COMPLETED", "", 0)]

    def _siguiente(self, respuestas):
        """La ultima respuesta se repite: el sondeo puede preguntar mas veces
        de las que el test haya previsto."""
        return respuestas[0] if len(respuestas) == 1 else respuestas.pop(0)

    def open_sftp(self):
        return self._sftp

    def exec_command(self, comando):
        self.comandos.append(comando)
        error, codigo = "", 0

        if comando.startswith("mkdir -p"):
            self.remote_dir = comando.split(" ", 2)[2].strip("'\"")
            salida = ""
        elif comando.startswith("sbatch"):
            # A partir de aqui el job "ha corrido": deja sus ficheros.
            self._sftp.sembrar_salida_del_job(self.remote_dir)
            self._sftp.remotos[f"{self.remote_dir}/slurm-12345.out"] = b"log del job"
            self._sftp.remotos[f"{self.remote_dir}/slurm-12345.err"] = b""
            # El centinela que escribe el propio sbatch con su codigo de salida.
            self._sftp.remotos[f"{self.remote_dir}/job.rc"] = (
                f"{self.codigo_salida_job}\n".encode())
            salida = "Submitted batch job 12345"
        elif comando.startswith("squeue"):
            salida, error, codigo = self._siguiente(self.respuestas_squeue)
        elif comando.startswith("scontrol show job"):
            salida, error, codigo = self._siguiente(self.respuestas_scontrol)
        elif comando.startswith("cat "):
            contenido = self._sftp.remotos.get(shlex.split(comando)[1])
            salida = "" if contenido is None else contenido.decode()
            codigo = 1 if contenido is None else 0
        else:
            salida = ""

        canal = SimpleNamespace(recv_exit_status=lambda: codigo)
        stdout = SimpleNamespace(read=lambda: salida.encode(), channel=canal)
        stderr = SimpleNamespace(read=lambda: error.encode())
        return None, stdout, stderr

    def close(self):
        pass


@pytest.fixture()
def ejecutor(monkeypatch):
    """SlurmExecutor con la conexion SSH sustituida por el doble."""

    def _construir(genera_al_terminar=None):
        sftp = FakeSFTP(genera_al_terminar)
        ssh = FakeSSH(sftp)
        ejec = SlurmExecutor()
        ejec.remote_base = "/remoto/jobs"
        monkeypatch.setattr(ejec, "_conectar", lambda: ssh)
        return ejec, ssh, sftp

    return _construir


def _argumentos_enviados(sftp) -> list:
    """
    Los argumentos de la linea `python3 ...` del sbatch que se subio al nodo,
    ya troceados.

    Se comparan tokens y no la cadena entera a proposito: shlex.quote solo
    entrecomilla lo que lo necesita, asi que "--scoring" viaja tal cual pero
    un nombre con espacios iria entre comillas. Comprobar la cadena ataria el
    test a ese detalle en vez de a lo que importa, que es que argumento recibe
    el script.
    """
    for fichero in sftp.escritos.values():
        texto = fichero.read().decode()
        for linea in texto.splitlines():
            if linea.startswith("python3"):
                return shlex.split(linea)[1:]   # sin el propio "python3"
    raise AssertionError("no se escribio ningun sbatch con una linea python3")


# ---------------------------------------------------------------------------
# 1. Las opciones no se convierten en rutas remotas
# ---------------------------------------------------------------------------

def test_las_opciones_viajan_literales_y_no_como_rutas(ejecutor, tmp_path):
    ejec, _, sftp = ejecutor()
    entrada = tmp_path / "ligando.sdf"
    entrada.write_bytes(b"molecula")
    salida = tmp_path / "poses.sdf"

    resultado = ejec.ejecutar_algoritmo(
        str(tmp_path / "dockingSmina.py"), str(entrada), str(salida),
        flags=["--exhaustiveness", "16", "--scoring", "vinardo"],
    )
    assert resultado["exito"], resultado

    argumentos = _argumentos_enviados(sftp)
    # Tal cual las espera dockingSmina.py: _parsear_argv_opcionales exige que
    # el argumento EMPIECE por "--", cosa que una ruta remota no cumple.
    assert argumentos[-4:] == ["--exhaustiveness", "16", "--scoring", "vinardo"]
    assert not any(a.startswith("/remoto/jobs") and "--" in a for a in argumentos)


def test_una_opcion_cuyo_valor_es_un_fichero_si_se_sube_y_se_reescribe(ejecutor, tmp_path):
    """
    `--referencia molecula.sdf` de dockingSmina: la opcion viaja literal pero
    su valor es un fichero de verdad, que hay que subir al nodo y sustituir
    por su ruta alli. Si no, el algoritmo buscaria una ruta del backend.
    """
    ejec, _, sftp = ejecutor()
    referencia = tmp_path / "referencia.sdf"
    referencia.write_bytes(b"molecula de referencia")
    entrada = tmp_path / "ligando.sdf"
    entrada.write_bytes(b"molecula")
    salida = tmp_path / "poses.sdf"

    resultado = ejec.ejecutar_algoritmo(
        str(tmp_path / "dockingSmina.py"), str(entrada), str(salida),
        flags=["--referencia", str(referencia)],
    )
    assert resultado["exito"], resultado

    argumentos = _argumentos_enviados(sftp)
    assert argumentos[-2] == "--referencia"
    # El valor apunta al nodo, no al backend.
    assert argumentos[-1].startswith("/remoto/jobs/job_")
    assert argumentos[-1].endswith("/referencia.sdf")
    assert str(referencia) not in argumentos
    assert any(r.endswith("/referencia.sdf") for r in sftp.subidos)


def test_los_ficheros_si_se_convierten_en_rutas_remotas(ejecutor, tmp_path):
    """El comportamiento de siempre para los argumentos que SI son ficheros."""
    ejec, _, sftp = ejecutor()
    entrada = tmp_path / "entrada.sdf"
    entrada.write_bytes(b"molecula")
    salida = tmp_path / "salida.sdf"

    ejec.ejecutar_algoritmo(str(tmp_path / "algo.py"), str(entrada), str(salida))

    argumentos = _argumentos_enviados(sftp)
    assert all(a.startswith("/remoto/jobs/job_") for a in argumentos)
    assert argumentos[-2].endswith("/entrada.sdf")
    assert argumentos[-1].endswith("/salida.sdf")


# ---------------------------------------------------------------------------
# 2. Vuelve lo que genera el algoritmo, no solo lo que se le paso
# ---------------------------------------------------------------------------

def test_se_descarga_el_json_de_energias_que_el_algoritmo_escribe_por_su_cuenta(
    ejecutor, tmp_path
):
    ejec, _, _ = ejecutor(genera_al_terminar={
        "poses.sdf": b"poses generadas",
        "poses_energias.json": b'{"mejor_afinidad": -9.1}',
    })
    entrada = tmp_path / "ligando.sdf"
    entrada.write_bytes(b"molecula")
    salida = tmp_path / "poses.sdf"

    resultado = ejec.ejecutar_algoritmo(
        str(tmp_path / "dockingSmina.py"), str(entrada), str(salida),
        flags=["--exhaustiveness", "8"],
    )
    assert resultado["exito"], resultado

    # El de siempre: es un argumento.
    assert salida.read_bytes() == b"poses generadas"
    # El que se quedaba en el cluster: lo deriva el propio script de su salida.
    energias = tmp_path / "poses_energias.json"
    assert energias.exists(), "el JSON de energias no volvio del nodo"
    assert b"mejor_afinidad" in energias.read_bytes()


def test_no_se_traen_ni_el_script_ni_el_sbatch_ni_los_logs_de_slurm(ejecutor, tmp_path):
    """
    El barrido del directorio del job solo debe traer lo que ha aparecido
    alli, no lo que pusimos nosotros ni lo que deja SLURM.
    """
    ejec, _, _ = ejecutor(genera_al_terminar={"salida.sdf": b"resultado"})
    entrada = tmp_path / "entrada.sdf"
    entrada.write_bytes(b"molecula")
    salida = tmp_path / "salida.sdf"
    script = tmp_path / "algo.py"
    script.write_bytes(b"print('hola')")

    ejec.ejecutar_algoritmo(str(script), str(entrada), str(salida))

    for no_deseado in ("job.sbatch", "slurm-12345.out", "slurm-12345.err", "job.rc"):
        assert not (tmp_path / no_deseado).exists(), f"{no_deseado} no debia bajarse"
    # Y el script del algoritmo no debe volver pisando el original.
    assert script.read_bytes() == b"print('hola')"


def test_un_extra_que_no_se_puede_traer_no_tumba_el_job(ejecutor, tmp_path, monkeypatch):
    """
    Traer un fichero acompañante es "mejor tenerlo": si falla, se anota en el
    log y el resultado del algoritmo sigue siendo valido.
    """
    ejec, _, sftp = ejecutor(genera_al_terminar={
        "salida.sdf": b"resultado",
        "extra_que_falla.json": b"{}",
    })
    entrada = tmp_path / "entrada.sdf"
    entrada.write_bytes(b"molecula")
    salida = tmp_path / "salida.sdf"

    get_original = sftp.get

    def get_que_falla(remote, local):
        if remote.endswith("extra_que_falla.json"):
            raise IOError("permiso denegado")
        return get_original(remote, local)

    monkeypatch.setattr(sftp, "get", get_que_falla)

    resultado = ejec.ejecutar_algoritmo(str(tmp_path / "algo.py"), str(entrada), str(salida))

    assert resultado["exito"] is True
    assert "extra_que_falla.json" in resultado["log"]
    assert salida.read_bytes() == b"resultado"


# ---------------------------------------------------------------------------
# 6. De donde sale el estado del job
# ---------------------------------------------------------------------------


def _correr(ejec, tmp_path):
    """Un job cualquiera: aqui lo que se mira es el sondeo, no los ficheros."""
    entrada = tmp_path / "entrada.sdf"
    entrada.write_bytes(b"molecula")
    return ejec.ejecutar_algoritmo(
        str(tmp_path / "algo.py"), str(entrada), str(tmp_path / "salida.sdf"))


def test_nunca_se_le_pregunta_a_sacct(ejecutor, tmp_path):
    """
    El sondeo usaba `sacct`, que depende de slurmdbd: un servicio opcional
    que el bullx no tiene levantado. Alli contesta "Problem talking to the
    database: Connection refused", asi que el estado no llegaba nunca y todo
    job acababa en TimeoutError... cuatro horas despues, que es lo que vale
    SLURM_JOB_TIMEOUT. squeue y scontrol los sirve el propio slurmctld.
    """
    ejec, ssh, _ = ejecutor(genera_al_terminar={"salida.sdf": b"resultado"})

    assert _correr(ejec, tmp_path)["exito"] is True
    assert not any(c.startswith("sacct") for c in ssh.comandos)


def test_mientras_el_job_sigue_en_la_cola_manda_squeue(ejecutor, tmp_path):
    ejec, ssh, _ = ejecutor(genera_al_terminar={"salida.sdf": b"resultado"})
    ejec.poll_interval = 0
    ssh.respuestas_squeue = [("PENDING", "", 0), ("RUNNING", "", 0), ("", "", 0)]

    assert _correr(ejec, tmp_path)["exito"] is True

    # Tres sondeos: los dos primeros los resuelve la cola y solo el tercero,
    # cuando el job ya no esta en ella, baja a preguntarle a scontrol.
    assert sum(1 for c in ssh.comandos if c.startswith("squeue")) == 3
    assert sum(1 for c in ssh.comandos if c.startswith("scontrol")) == 1


def test_si_slurm_ya_no_conoce_el_job_decide_el_centinela(ejecutor, tmp_path):
    """
    slurmctld solo recuerda un job terminado durante MinJobAge (300 s por
    defecto). Si el worker se queda sin preguntar mas tiempo del que dura esa
    memoria --una desconexion larga, por ejemplo-- ni la cola ni scontrol
    saben ya nada, y lo unico que queda en el nodo es el codigo de salida que
    el propio sbatch dejo escrito.
    """
    desconocido = ("", "slurm_load_jobs error: Invalid job id specified", 1)
    ejec, ssh, _ = ejecutor(genera_al_terminar={"salida.sdf": b"resultado"})
    ssh.respuestas_squeue = [desconocido]
    ssh.respuestas_scontrol = [desconocido]

    assert _correr(ejec, tmp_path)["exito"] is True
    assert any(c.startswith("cat ") for c in ssh.comandos)


def test_el_centinela_tambien_delata_al_job_que_fallo(ejecutor, tmp_path):
    desconocido = ("", "slurm_load_jobs error: Invalid job id specified", 1)
    ejec, ssh, _ = ejecutor(genera_al_terminar={"salida.sdf": b"resultado"})
    ssh.respuestas_squeue = [desconocido]
    ssh.respuestas_scontrol = [desconocido]
    ssh.codigo_salida_job = 3

    assert _correr(ejec, tmp_path)["exito"] is False


def test_un_fallo_pasajero_de_squeue_no_se_toma_por_un_job_fallado(ejecutor, tmp_path):
    """
    Un corte de red o un slurmctld ocupado no pueden confundirse con "el job
    ha fallado": eso daria por perdida una peticion que va perfectamente. Se
    distingue por lo que dice el error, no por el codigo de salida.
    """
    ejec, ssh, _ = ejecutor(genera_al_terminar={"salida.sdf": b"resultado"})
    ejec.poll_interval = 0
    ssh.respuestas_squeue = [
        ("", "slurm_load_jobs error: Unable to contact slurm controller", 1),
        ("", "", 0),
    ]

    assert _correr(ejec, tmp_path)["exito"] is True
    # El sondeo fallido ni siquiera llega a consultar a scontrol: espera y
    # vuelve a preguntar.
    assert sum(1 for c in ssh.comandos if c.startswith("scontrol")) == 1


# ---------------------------------------------------------------------------
# 7. Reintentos de conexion
# ---------------------------------------------------------------------------


def _paramiko_falso(monkeypatch, errores):
    """
    Sustituye paramiko.SSHClient por uno que levanta, por orden, los errores de
    `errores`, y conecta bien cuando se le acaban. Devuelve la lista de
    intentos, que es lo que miden estos tests.
    """
    intentos = []

    class ClienteFalso:
        def load_system_host_keys(self):
            pass

        def set_missing_host_key_policy(self, _politica):
            pass

        def close(self):
            pass

        def connect(self, **kwargs):
            intentos.append(kwargs)
            if len(intentos) <= len(errores):
                raise errores[len(intentos) - 1]

    monkeypatch.setattr(slurm_executor.paramiko, "SSHClient", ClienteFalso)
    monkeypatch.setattr(slurm_executor.time, "sleep", lambda _s: None)
    return intentos


def _ejecutor_configurado():
    ejec = SlurmExecutor()
    ejec.user = "agm925"
    ejec.key_path = "/root/.ssh/id_rsa_ual"
    return ejec


def _clave(nombre):
    return SimpleNamespace(get_base64=lambda: nombre)


def test_un_saludo_rechazado_por_sshd_se_reintenta(monkeypatch):
    """
    El cribado abre una conexion por molecula y las lanza a la vez. sshd corta
    las que pasan de MaxStartups, y contra el bullx eso ya se vio: con 11
    moleculas en paralelo, una acabo en el ranking como fallida con "Error
    reading SSH protocol banner" sin tener nada de malo.
    """
    intentos = _paramiko_falso(monkeypatch, [
        paramiko.SSHException("Error reading SSH protocol banner"),
        paramiko.SSHException("Error reading SSH protocol banner"),
    ])

    _ejecutor_configurado()._conectar()

    assert len(intentos) == 3, "deberia haber reintentado hasta conectar"


def test_una_clave_de_host_que_no_cuadra_no_se_reintenta(monkeypatch):
    """
    Insistir aqui seria justo lo contrario de lo que se quiere: esa excepcion
    es la senal que RejectPolicy existe para dar.
    """
    intentos = _paramiko_falso(monkeypatch, [
        paramiko.BadHostKeyException("bullxual", _clave("otra"), _clave("la buena")),
    ])

    with pytest.raises(paramiko.BadHostKeyException):
        _ejecutor_configurado()._conectar()

    assert len(intentos) == 1


def test_unas_credenciales_que_no_valen_no_se_reintentan(monkeypatch):
    intentos = _paramiko_falso(monkeypatch, [
        paramiko.AuthenticationException("Authentication failed."),
    ])

    with pytest.raises(paramiko.AuthenticationException):
        _ejecutor_configurado()._conectar()

    assert len(intentos) == 1


def test_si_no_hay_manera_el_error_dice_cuantos_intentos_se_hicieron(monkeypatch):
    """Que el mensaje distinga "no contesta" de "contesta y rechaza"."""
    intentos = _paramiko_falso(monkeypatch, [
        paramiko.SSHException("Error reading SSH protocol banner")] * 10)

    with pytest.raises(ConnectionError) as error:
        _ejecutor_configurado()._conectar()

    assert len(intentos) == slurm_executor._INTENTOS_CONEXION
    assert "4 intentos" in str(error.value)


# ---------------------------------------------------------------------------
# 8. Lote: un job array para N invocaciones
# ---------------------------------------------------------------------------


class FakeSSHArray:
    """
    Doble de SSH para ejecutar_lote.

    Entiende las tres ordenes propias del camino en lote: el mkdir con
    expansion de llaves, el sbatch del array y el bucle que recoge los codigos
    de salida de las N tareas.
    """

    JOB_ID = "777"

    def __init__(self, sftp, codigos, genera=None):
        self._sftp = sftp
        self.comandos = []
        self.codigos = list(codigos)
        self.genera = genera or {}       # indice de tarea -> {nombre: contenido}
        self.lote_dir = None

    def open_sftp(self):
        return self._sftp

    def exec_command(self, comando):
        self.comandos.append(comando)
        salida, error, codigo = "", "", 0

        if comando.startswith("mkdir -p"):
            self.lote_dir = comando.split(" ", 2)[2].split("/tarea_")[0].strip("\"'")
        elif comando.startswith("sbatch"):
            # A partir de aqui el array "ha corrido": cada tarea deja sus
            # ficheros de SLURM y lo que haya generado el algoritmo.
            for i in range(len(self.codigos)):
                directorio = self.lote_dir + "/tarea_" + str(i)
                self._sftp.remotos[directorio + "/slurm-" + self.JOB_ID + "_" + str(i) + ".out"] = b"log de la tarea"
                self._sftp.remotos[directorio + "/slurm-" + self.JOB_ID + "_" + str(i) + ".err"] = b""
                for nombre, contenido in self.genera.get(i, {}).items():
                    self._sftp.remotos[directorio + "/" + nombre] = contenido
            salida = "Submitted batch job " + self.JOB_ID
        elif comando.startswith("squeue"):
            salida = ""              # el array ya no esta en la cola
        elif comando.startswith("for i in $(seq"):
            salida = chr(10).join(self.codigos) + chr(10)

        canal = SimpleNamespace(recv_exit_status=lambda: codigo)
        stdout = SimpleNamespace(read=lambda: salida.encode(), channel=canal)
        stderr = SimpleNamespace(read=lambda: error.encode())
        return None, stdout, stderr

    def close(self):
        pass


@pytest.fixture()
def ejecutor_lote(monkeypatch):
    """SlurmExecutor preparado para ejecutar_lote, con el SSH sustituido."""

    def _construir(codigos, genera=None):
        sftp = FakeSFTP()
        ssh = FakeSSHArray(sftp, codigos, genera)
        ejec = SlurmExecutor()
        ejec.remote_base = "/remoto/jobs"
        ejec.poll_interval = 0
        conexiones = []

        def _conectar():
            conexiones.append(ssh)
            return ssh

        monkeypatch.setattr(ejec, "_conectar", _conectar)
        return ejec, ssh, sftp, conexiones

    return _construir


def _invocacion(tmp_path, nombre, flags=()):
    entrada = tmp_path / (nombre + "_entrada.sdf")
    entrada.write_bytes(b"molecula")
    salida = tmp_path / (nombre + "_salida.json")
    return (str(tmp_path / "algo.py"), [str(entrada), str(salida)], list(flags))


def _run_sh(sftp, indice):
    """El run.sh que se subio para la tarea `indice`, ya troceado."""
    for ruta, fichero in sftp.escritos.items():
        if ruta.endswith("/tarea_" + str(indice) + "/run.sh"):
            for linea in fichero.read().decode().splitlines():
                if linea.startswith("python3"):
                    return shlex.split(linea)[1:]
    raise AssertionError("no se subio run.sh para la tarea " + str(indice))


def test_las_n_invocaciones_viajan_en_un_solo_array(ejecutor_lote, tmp_path):
    """
    Lo que justifica todo el camino en lote: una conexion, un sbatch y una
    espera para las N moleculas, en vez de N de cada.
    """
    ejec, ssh, sftp, conexiones = ejecutor_lote(["0", "0", "0"])

    resultados = ejec.ejecutar_lote([_invocacion(tmp_path, "m%d" % i) for i in range(3)])

    assert [r["exito"] for r in resultados] == [True, True, True]
    assert len(conexiones) == 1, "una sola conexion SSH para todo el lote"
    assert sum(1 for c in ssh.comandos if c.startswith("sbatch")) == 1

    sbatch = [f.read().decode() for r, f in sftp.escritos.items() if r.endswith(".sbatch")][0]
    assert "--array=0-2" in sbatch


def test_cada_tarea_del_array_recibe_sus_propios_argumentos(ejecutor_lote, tmp_path):
    """
    Un array comparte script, asi que el riesgo propio de este camino es que
    las tareas se mezclen los argumentos. Cada una lleva los suyos en su
    run.sh.
    """
    ejec, _, sftp, _ = ejecutor_lote(["0", "0"])

    ejec.ejecutar_lote([
        _invocacion(tmp_path, "primera", flags=["--scoring", "vinardo"]),
        _invocacion(tmp_path, "segunda", flags=["--scoring", "vina"]),
    ])

    argumentos_0 = _run_sh(sftp, 0)
    argumentos_1 = _run_sh(sftp, 1)

    assert any(a.endswith("primera_entrada.sdf") for a in argumentos_0)
    assert not any("segunda" in a for a in argumentos_0)
    assert "vinardo" in argumentos_0 and "vina" in argumentos_1
    # Y las opciones siguen sin convertirse en rutas remotas.
    assert "--scoring" in argumentos_0


def test_el_veredicto_de_cada_tarea_es_el_suyo(ejecutor_lote, tmp_path):
    """
    Que una tarea falle no invalida a las demas: cada molecula tiene su propio
    centinela y el orden de los resultados es el de las invocaciones.
    """
    ejec, _, _, _ = ejecutor_lote(
        ["0", "3", "0"],
        genera={0: {"m0_salida.json": b"{}"}, 2: {"m2_salida.json": b"{}"}})

    invocaciones = [_invocacion(tmp_path, "m%d" % i) for i in range(3)]
    resultados = ejec.ejecutar_lote(invocaciones)

    assert [r["exito"] for r in resultados] == [True, False, True]
    assert "codigo 3" in resultados[1]["error"]
    # La que fallo no deja resultado; las otras dos si.
    assert (tmp_path / "m0_salida.json").exists()
    assert (tmp_path / "m2_salida.json").exists()
    assert not (tmp_path / "m1_salida.json").exists()


def test_los_ficheros_de_slurm_no_se_bajan_como_resultados(ejecutor_lote, tmp_path):
    """
    En un array los logs se llaman slurm-<array>_<tarea>.out, no
    slurm-<job>.out. Con el nombre de un job suelto no se reconocerian y
    acabarian en uploads/ como si fueran salidas del algoritmo.
    """
    ejec, _, _, _ = ejecutor_lote(["0"], genera={0: {"m0_salida.json": b"{}"}})

    ejec.ejecutar_lote([_invocacion(tmp_path, "m0")])

    for ruta in tmp_path.iterdir():
        assert not ruta.name.startswith("slurm-"), ruta.name
        assert ruta.name != "job.rc"
        assert ruta.name != "run.sh"


def test_un_lote_mas_grande_que_el_maximo_se_parte_en_varios(ejecutor_lote, tmp_path, monkeypatch):
    """
    SLURM rechaza de entrada un array por encima de MaxArraySize (1001 en el
    bullx), y rechaza el lote ENTERO: sin partirlo, una biblioteca grande no
    se cribaria a medias sino nada.
    """
    monkeypatch.setattr(slurm_executor, "_MAX_TAREAS_ARRAY", 2)
    ejec, ssh, _, _ = ejecutor_lote(["0", "0"])

    resultados = ejec.ejecutar_lote([_invocacion(tmp_path, "m%d" % i) for i in range(4)])

    assert len(resultados) == 4
    assert sum(1 for c in ssh.comandos if c.startswith("sbatch")) == 2


def test_un_lote_vacio_no_toca_el_cluster(ejecutor_lote, tmp_path):
    ejec, ssh, _, conexiones = ejecutor_lote([])

    assert ejec.ejecutar_lote([]) == []
    assert conexiones == []
