"""
Tests del banco de pruebas de algoritmos (app/banco_pruebas.py).

Antes, subir un algoritmo era un acto de fe: el metadato TIPO_ALGORITMO lo
declaraba el autor y nadie comprobaba que el script llegara siquiera a
ejecutarse. Un algoritmo roto entraba en el catalogo igual que uno correcto, y
el fallo aparecia horas despues dentro de un cribado, como una molecula
fallida entre mil.

Ahora el autor DECLARA que hace su algoritmo --lo que permite saber como
invocarlo-- y la plataforma lo VERIFICA ejecutandolo contra dos moleculas de
referencia antes de aceptarlo.
"""
import os

import pytest

from app.banco_pruebas import (LIGANDO_A, LIGANDO_B, RECEPTOR, _entorno_minimo,
                               elegir_clave_score, probar_algoritmo)


def _escribir(tmp_path, nombre, codigo):
    ruta = tmp_path / nombre
    ruta.write_text(codigo, encoding="utf-8")
    return str(ruta)


# --------------------------------------------------------------- referencias
def test_las_moleculas_de_referencia_existen():
    for ruta in (LIGANDO_A, LIGANDO_B, RECEPTOR):
        assert os.path.exists(ruta), f"falta el fichero de referencia {ruta}"
        assert os.path.getsize(ruta) > 0


def test_las_dos_referencias_son_la_misma_molecula_en_distinta_conformacion():
    """
    Lo exigen los algoritmos mas restrictivos del catalogo: rmsdConformaciones
    necesita la MISMA molecula (GetBestRMS falla si difieren) y alinearMCS
    necesita una subestructura comun. Y deben diferir de verdad: con dos
    ficheros identicos, un algoritmo de RMSD roto que devolviera 0 tambien
    pasaria la prueba.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    a = next(Chem.SDMolSupplier(LIGANDO_A, removeHs=False))
    b = next(Chem.SDMolSupplier(LIGANDO_B, removeHs=False))

    assert Chem.MolToSmiles(a) == Chem.MolToSmiles(b), "deben ser la misma molecula"
    assert AllChem.GetBestRMS(a, b) > 0.1, "las conformaciones deben diferir"


# ------------------------------------------------------------------ rechazos
def test_se_rechaza_un_algoritmo_que_revienta(tmp_path):
    ruta = _escribir(tmp_path, "revienta.py",
                     "# TIPO_ALGORITMO: preprocesado\n"
                     "raise RuntimeError('me he roto')\n")
    r = probar_algoritmo(ruta, "preprocesado")
    assert not r.valido
    assert "error" in r.motivo.lower()
    assert "me he roto" in (r.detalle or "")


def test_se_rechaza_un_algoritmo_que_no_escribe_nada(tmp_path):
    """El caso mas insidioso: termina con codigo 0 y parece que ha funcionado."""
    ruta = _escribir(tmp_path, "silencioso.py",
                     "# TIPO_ALGORITMO: preprocesado\n"
                     "print('digo que he trabajado')\n")
    r = probar_algoritmo(ruta, "preprocesado")
    assert not r.valido
    assert "no escribió" in r.motivo or "no escribio" in r.motivo


def test_se_rechaza_un_algoritmo_que_devuelve_un_json_de_error(tmp_path):
    ruta = _escribir(tmp_path, "json_error.py",
                     "# TIPO_ALGORITMO: comparacion\n"
                     "import json, sys\n"
                     "json.dump({'exito': False, 'error': 'no pude'}, open(sys.argv[-1], 'w'))\n")
    r = probar_algoritmo(ruta, "comparacion")
    assert not r.valido
    assert "no pude" in (r.detalle or "")


def test_se_rechaza_un_json_sin_ningun_numero(tmp_path):
    """El cribado por lotes necesita una puntuacion para ordenar el ranking."""
    ruta = _escribir(tmp_path, "sin_numeros.py",
                     "# TIPO_ALGORITMO: comparacion\n"
                     "import json, sys\n"
                     "json.dump({'comentario': 'todo bien'}, open(sys.argv[-1], 'w'))\n")
    r = probar_algoritmo(ruta, "comparacion")
    assert not r.valido
    assert "numérico" in r.motivo or "numerico" in r.motivo


def test_se_rechaza_un_tipo_desconocido(tmp_path):
    ruta = _escribir(tmp_path, "x.py", "# TIPO_ALGORITMO: preprocesado\n")
    r = probar_algoritmo(ruta, "telepatia")
    assert not r.valido


# ----------------------------------------------------------------- aceptados
def test_se_acepta_un_algoritmo_que_devuelve_una_molecula(tmp_path):
    ruta = _escribir(tmp_path, "copia.py",
                     "# TIPO_ALGORITMO: preprocesado\n"
                     "import shutil, sys\n"
                     "shutil.copyfile(sys.argv[1], sys.argv[-1])\n")
    r = probar_algoritmo(ruta, "preprocesado")
    assert r.valido, r.motivo
    assert r.formato_salida == "molecula"


def test_se_acepta_un_algoritmo_de_metricas_y_se_anota_su_clave(tmp_path):
    """
    Esta es la razon de ser del banco mas alla de aceptar o rechazar: observar
    QUE CLAVE contiene la puntuacion. Anotarla evita que el motor tenga que
    adivinarla por su nombre, que fue el origen de cuatro fallos distintos.
    """
    ruta = _escribir(tmp_path, "metrica.py",
                     "# TIPO_ALGORITMO: comparacion\n"
                     "import json, sys\n"
                     "json.dump({'exito': True, 'mi_metrica_rara': 0.77},\n"
                     "          open(sys.argv[-1], 'w'))\n")
    r = probar_algoritmo(ruta, "comparacion")
    assert r.valido, r.motivo
    assert r.formato_salida == "json"
    assert r.clave_score == "mi_metrica_rara"


def test_se_detecta_una_clave_anidada(tmp_path):
    """filtroLipinski envuelve sus resultados en {"moleculas": [{...}]}."""
    ruta = _escribir(tmp_path, "anidado.py",
                     "# TIPO_ALGORITMO: preprocesado\n"
                     "import json, sys\n"
                     "json.dump({'moleculas': [{'MW': 236.27}]}, open(sys.argv[-1], 'w'))\n")
    r = probar_algoritmo(ruta, "preprocesado")
    assert r.valido, r.motivo
    assert r.clave_score == "moleculas.MW"


def test_un_booleano_no_se_confunde_con_una_puntuacion(tmp_path):
    ruta = _escribir(tmp_path, "bool.py",
                     "# TIPO_ALGORITMO: comparacion\n"
                     "import json, sys\n"
                     "json.dump({'exito': True, 'valor': 3.5}, open(sys.argv[-1], 'w'))\n")
    r = probar_algoritmo(ruta, "comparacion")
    assert r.valido, r.motivo
    assert r.clave_score == "valor", "'exito': true no es una puntuacion"


# ------------------------------------------------------- eleccion de la clave
@pytest.mark.parametrize("claves,esperada", [
    (["exito", "similitud", "num_atomos"], "similitud"),
    (["rmsd_angstroms", "otra"], "rmsd_angstroms"),
    (["energias.mejor_afinidad"], "energias.mejor_afinidad"),
    (["moleculas.MW", "moleculas.LogP"], "moleculas.MW"),
    (["cualquiera"], "cualquiera"),
    ([], None),
])
def test_eleccion_de_la_clave_de_puntuacion(claves, esperada):
    assert elegir_clave_score(claves) == esperada


# --------------------------------------------- integracion con el endpoint
def test_un_algoritmo_rechazado_no_deja_rastro_en_el_catalogo(
    client, db_session, otro_usuario_autenticado
):
    """
    Si no supera la prueba, no debe quedar ni el fichero en algoritmos/ ni la
    fila en la base de datos: por eso se escribe primero a un temporal.
    """
    from app import models

    antes = db_session.query(models.Algoritmo).count()
    nombre_fichero = "test_banco_rechazado.py"

    respuesta = client.post(
        "/algoritmos",
        data={"nombre": "Roto", "descripcion": "no funciona", "tipo": "preprocesado"},
        files={"archivo": (nombre_fichero,
                           b"# TIPO_ALGORITMO: preprocesado\nraise SystemExit(3)\n",
                           "text/x-python")},
        headers=otro_usuario_autenticado["headers"],
    )

    assert respuesta.status_code == 422
    assert db_session.query(models.Algoritmo).count() == antes, "no debe crearse la fila"
    assert not os.path.exists(os.path.join("algoritmos", nombre_fichero)), \
        "no debe quedar el fichero en el catalogo"


def test_un_algoritmo_valido_se_acepta_y_guarda_lo_observado(
    client, db_session, otro_usuario_autenticado
):
    from app import models

    respuesta = client.post(
        "/algoritmos",
        data={"nombre": "Metrica valida", "descripcion": "ok", "tipo": "comparacion"},
        files={"archivo": ("test_banco_valido.py",
                           b"# TIPO_ALGORITMO: comparacion\n"
                           b"import json, sys\n"
                           b"json.dump({'similitud': 0.9}, open(sys.argv[-1], 'w'))\n",
                           "text/x-python")},
        headers=otro_usuario_autenticado["headers"],
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["formato_salida"] == "json"
    assert cuerpo["clave_score"] == "similitud"
    assert cuerpo["verificado"] is True


# ------------------------------------------------------------- aislamiento
#
# Probar un algoritmo es ejecutar codigo que acaba de llegar y que todavia no
# se ha aceptado. Estos tests no comprueban una funcionalidad: fijan una
# PROPIEDAD DE SEGURIDAD, para que no se pierda en un cambio futuro sin que
# nadie se entere. La primera version del banco ejecutaba el script en el
# proceso del backend, como root y con su entorno completo --incluida la clave
# de firma de los JWT--, y el fallo no se vio hasta que alguien lo pregunto.

SENSIBLES = ("JWT_SECRET_KEY", "DATABASE_URL", "SMTP_PASSWORD", "SLURM_PASSWORD")


def test_el_entorno_del_subproceso_no_arrastra_secretos(monkeypatch):
    for clave in SENSIBLES:
        monkeypatch.setenv(clave, "valor-secreto-de-prueba")

    entorno = _entorno_minimo()

    for clave in SENSIBLES:
        assert clave not in entorno, f"{clave} no debe llegar al algoritmo"
    # Y sigue siendo utilizable: sin PATH no encontraria obabel ni smina.
    assert entorno.get("PATH")


def test_un_algoritmo_no_puede_leer_los_secretos_del_proceso(tmp_path, monkeypatch):
    """Lo mismo, pero de extremo a extremo: ejecutando de verdad."""
    monkeypatch.setenv("JWT_SECRET_KEY", "clave-que-no-debe-verse")

    ruta = _escribir(tmp_path, "fisgon.py",
                     "# TIPO_ALGORITMO: preprocesado\n"
                     "import json, os, sys\n"
                     "json.dump({'visto': os.environ.get('JWT_SECRET_KEY', 'NADA'), 'n': 1.0},\n"
                     "          open(sys.argv[-1], 'w'))\n"
                     "print('JWT_SECRET_KEY =', os.environ.get('JWT_SECRET_KEY', 'NADA'))\n")

    r = probar_algoritmo(ruta, "preprocesado")
    assert r.valido, r.motivo
    assert "clave-que-no-debe-verse" not in (r.log or "")
    assert "NADA" in (r.log or "")


def test_si_el_servicio_aislado_no_responde_el_script_no_se_ejecuta_aqui(tmp_path, monkeypatch):
    """
    El comportamiento tiene que ser FALLAR CERRADO.

    Recurrir a ejecutar el script en el proceso que llama, cuando el sandbox no
    esta disponible, reintroduciria el problema entero justo en el momento en
    que nadie esta mirando. Es preferible rechazar la subida.
    """
    import app.banco_pruebas as bp

    testigo = tmp_path / "se_ejecuto.txt"
    ruta = _escribir(tmp_path, "con_testigo.py",
                     "# TIPO_ALGORITMO: preprocesado\n"
                     "import json, sys\n"
                     f"open(r'{testigo}', 'w').write('si')\n"
                     "json.dump({'n': 1.0}, open(sys.argv[-1], 'w'))\n")

    monkeypatch.setattr(bp, "BANCO_SOCKET", "/tmp/no-existe-este-socket.sock")
    monkeypatch.setattr(bp, "BANCO_URL", "")

    r = probar_algoritmo(ruta, "preprocesado")

    assert not r.valido
    assert "no está disponible" in (r.motivo or "")
    assert not testigo.exists(), "el script NO debe haberse ejecutado en este proceso"
