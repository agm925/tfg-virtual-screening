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
"""
import os
import shlex
import stat
from types import SimpleNamespace

import pytest

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

    def open_sftp(self):
        return self._sftp

    def exec_command(self, comando):
        self.comandos.append(comando)

        if comando.startswith("mkdir -p"):
            self.remote_dir = comando.split(" ", 2)[2].strip("'\"")
            salida = ""
        elif comando.startswith("sbatch"):
            # A partir de aqui el job "ha corrido": deja sus ficheros.
            self._sftp.sembrar_salida_del_job(self.remote_dir)
            self._sftp.remotos[f"{self.remote_dir}/slurm-12345.out"] = b"log del job"
            self._sftp.remotos[f"{self.remote_dir}/slurm-12345.err"] = b""
            salida = "Submitted batch job 12345"
        elif comando.startswith("sacct"):
            salida = "COMPLETED\n"
        else:
            salida = ""

        canal = SimpleNamespace(recv_exit_status=lambda: 0)
        stdout = SimpleNamespace(read=lambda: salida.encode(), channel=canal)
        stderr = SimpleNamespace(read=lambda: b"")
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

    for no_deseado in ("job.sbatch", "slurm-12345.out", "slurm-12345.err"):
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
