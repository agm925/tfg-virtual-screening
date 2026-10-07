"""
Tests de integracion de los endpoints /visor/... (spec 002).

Lo que importa aqui es quien ve que: el visor ofrece lo subido por cualquiera
y los resultados propios terminados, nunca los resultados de otro, y un
administrador recibe la misma lista que un biologo (RF-2). Lo que el visor
cuenta de cada molecula ya lo prueba tests/test_visor.py.
"""
import os
import uuid
from datetime import datetime

import pytest

from app import models

SDF_DOS = b"mol1\n\n\n  0  0\nM  END\n$$$$\nmol2\n\n\n  0  0\nM  END\n$$$$\n"


def _subir(client, usuario, nombre, contenido=SDF_DOS, tipo="base_de_datos"):
    respuesta = client.post(
        "/moleculas/subir",
        data={"tipo": tipo},
        files={"archivo": (nombre, contenido, "application/octet-stream")},
        headers=usuario["headers"],
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["nombre"]


def _resultado(db, usuario, estado_ejecucion, nombre=None, contenido=SDF_DOS, fecha=None):
    """Un resultado de una ejecucion en el estado dado, en disco y en el registro."""
    nombre = nombre or "test_visor_res_{}.sdf".format(uuid.uuid4().hex[:10])
    with open(os.path.join("uploads", nombre), "wb") as f:
        f.write(contenido)
    ejecucion = models.WorkflowExecution(usuario_id=usuario["usuario"]["id"], estado=estado_ejecucion)
    db.add(ejecucion)
    db.commit()
    db.add(models.Archivo(
        nombre=nombre, visibilidad=models.VisibilidadArchivo.resultado,
        tipo=models.TipoArchivo.resultado, propietario_id=usuario["usuario"]["id"],
        ejecucion_id=ejecucion.id, fecha_creacion=fecha or datetime.utcnow(),
    ))
    db.commit()
    return nombre


def _nombres(client, usuario, **params):
    respuesta = client.get("/visor/ficheros", params=params, headers=usuario["headers"])
    assert respuesta.status_code == 200, respuesta.text
    return [f["nombre"] for f in respuesta.json()]


# ---------------------------------------------------------------------------
# GET /visor/ficheros (T16, RF-2, RF-3)
# ---------------------------------------------------------------------------

def test_el_visor_ofrece_lo_subido_por_otros(client, usuario_autenticado, otro_usuario_autenticado):
    ajeno = _subir(client, otro_usuario_autenticado, "test_visor_ajeno.sdf")

    assert ajeno in _nombres(client, usuario_autenticado)


def test_el_visor_ofrece_los_resultados_propios_terminados(client, db_session, usuario_autenticado):
    propio = _resultado(db_session, usuario_autenticado, "completado")

    assert propio in _nombres(client, usuario_autenticado)


def test_el_visor_no_ofrece_los_resultados_de_otro(client, db_session, usuario_autenticado,
                                                   otro_usuario_autenticado):
    ajeno = _resultado(db_session, otro_usuario_autenticado, "completado")

    assert ajeno not in _nombres(client, usuario_autenticado)


@pytest.mark.parametrize("estado", ["pendiente", "procesando", "cancelado", "error"])
def test_el_visor_no_ofrece_resultados_sin_terminar_bien(client, db_session, usuario_autenticado, estado):
    propio = _resultado(db_session, usuario_autenticado, estado)

    assert propio not in _nombres(client, usuario_autenticado)


def test_el_administrador_recibe_la_misma_lista_que_un_biologo(client, db_session, usuario_autenticado,
                                                              admin_autenticado):
    """
    Aunque las reglas de acceso le dejen leer cualquier fichero, en el visor
    ve lo que veria un biologo: lo subido y lo suyo (RF-2). Los resultados de
    otros, en su panel de Administracion.
    """
    ajeno = _resultado(db_session, usuario_autenticado, "completado")
    subido = _subir(client, usuario_autenticado, "test_visor_admin.sdf")

    nombres = _nombres(client, admin_autenticado)

    assert subido in nombres
    assert ajeno not in nombres


def test_cada_grupo_va_del_mas_reciente_al_mas_antiguo(client, db_session, usuario_autenticado):
    antiguo = _resultado(db_session, usuario_autenticado, "completado", fecha=datetime(2026, 1, 1))
    reciente = _resultado(db_session, usuario_autenticado, "completado", fecha=datetime(2026, 2, 1))

    respuesta = client.get("/visor/ficheros", headers=usuario_autenticado["headers"])
    resultados = [f["nombre"] for f in respuesta.json() if f["grupo"] == "resultado"]

    assert resultados.index(reciente) < resultados.index(antiguo)
    grupos = [f["grupo"] for f in respuesta.json()]
    # Los grupos no se mezclan: moleculas, bibliotecas y resultados, en ese orden.
    assert grupos == sorted(grupos, key=["molecula", "biblioteca", "resultado"].index)


def test_el_buscador_filtra_por_nombre(client, usuario_autenticado):
    buscado = _subir(client, usuario_autenticado, "test_visor_Cafeína_{}.sdf".format(uuid.uuid4().hex[:6]))

    nombres = _nombres(client, usuario_autenticado, q="CAFEINA")

    assert buscado in nombres
    assert all("cafe" in n.lower().replace("í", "i") for n in nombres)


def test_el_visor_exige_sesion(client):
    assert client.get("/visor/ficheros").status_code == 401


# ---------------------------------------------------------------------------
# 404 uniforme (T17, RF-2, RF-13): no revelar si un fichero existe
# ---------------------------------------------------------------------------

def _usuario_db(db, usuario):
    return db.get(models.Usuario, usuario["usuario"]["id"])


def _error_al_pedir(nombre, db, usuario):
    from fastapi import HTTPException

    from app.main import fichero_del_visor
    with pytest.raises(HTTPException) as error:
        fichero_del_visor(nombre, db, _usuario_db(db, usuario))
    return error.value.status_code, error.value.detail


def test_inexistente_ajeno_y_sin_terminar_dan_el_mismo_error(db_session, usuario_autenticado,
                                                             otro_usuario_autenticado):
    """
    Quien pide un fichero que no puede ver no debe distinguir si existe: el
    mismo codigo y el mismo texto para los tres casos (RF-2).
    """
    ajeno = _resultado(db_session, otro_usuario_autenticado, "completado")
    en_curso = _resultado(db_session, usuario_autenticado, "procesando")

    errores = {
        _error_al_pedir("test_visor_no_existe_{}.sdf".format(uuid.uuid4().hex[:8]), db_session, usuario_autenticado),
        _error_al_pedir(ajeno, db_session, usuario_autenticado),
        _error_al_pedir(en_curso, db_session, usuario_autenticado),
    }

    assert errores == {(404, "Ese fichero no existe o no tienes acceso a él.")}


def test_un_fichero_visible_da_su_ruta(client, db_session, usuario_autenticado, otro_usuario_autenticado):
    from app.main import fichero_del_visor

    ajeno_subido = _subir(client, otro_usuario_autenticado, "test_visor_ruta.sdf")
    propio = _resultado(db_session, usuario_autenticado, "completado")

    for nombre in (ajeno_subido, propio):
        assert fichero_del_visor(nombre, db_session, _usuario_db(db_session, usuario_autenticado)) \
            == os.path.join("uploads", nombre)


def _sdf(nombres):
    return "".join("{}\n\n\n  0  0\nM  END\n$$$$\n".format(n) for n in nombres).encode()


def _respuestas_iguales(client, usuario, ruta_inexistente, ruta_ajena):
    """El 404 de un fichero que no existe y el de uno ajeno, byte a byte."""
    a = client.get(ruta_inexistente, headers=usuario["headers"])
    b = client.get(ruta_ajena, headers=usuario["headers"])
    assert a.status_code == b.status_code == 404
    assert a.content == b.content
    # Y es el 404 del visor, no el de una ruta que no existe.
    assert a.json()["detail"] == "Ese fichero no existe o no tienes acceso a él."


# ---------------------------------------------------------------------------
# GET /visor/ficheros/{nombre}/moleculas (T18, RF-6)
# ---------------------------------------------------------------------------

@pytest.fixture
def biblioteca_30(client, usuario_autenticado):
    """30 moleculas M1..M30, con CHEMBL25 en la posicion 3."""
    nombres = ["M{}".format(i) for i in range(1, 31)]
    nombres[2] = "CHEMBL25"
    return _subir(client, usuario_autenticado, "test_visor_lista.sdf", _sdf(nombres))


def _lista(client, usuario, nombre, **params):
    respuesta = client.get("/visor/ficheros/{}/moleculas".format(nombre), params=params,
                           headers=usuario["headers"])
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def test_la_lista_pagina_con_offset_y_limit(client, usuario_autenticado, biblioteca_30):
    primera = _lista(client, usuario_autenticado, biblioteca_30, limit=20)
    segunda = _lista(client, usuario_autenticado, biblioteca_30, offset=20, limit=20)

    assert primera["total"] == 30
    assert [c["posicion"] for c in primera["coincidencias"]] == list(range(1, 21))
    assert primera["hay_mas"] is True
    assert [c["posicion"] for c in segunda["coincidencias"]] == list(range(21, 31))
    assert segunda["hay_mas"] is False


def test_la_lista_por_defecto_trae_50(client, usuario_autenticado):
    grande = _subir(client, usuario_autenticado, "test_visor_grande.sdf",
                    _sdf("N{}".format(i) for i in range(120)))

    assert len(_lista(client, usuario_autenticado, grande)["coincidencias"]) == 50


def test_buscar_25_da_la_posicion_y_el_nombre(client, usuario_autenticado, biblioteca_30):
    resultado = _lista(client, usuario_autenticado, biblioteca_30, q="25")

    assert [(c["posicion"], c["nombre"]) for c in resultado["coincidencias"]] == [(25, "M25"), (3, "CHEMBL25")]


def test_una_posicion_que_no_existe_se_avisa(client, usuario_autenticado, biblioteca_30):
    resultado = _lista(client, usuario_autenticado, biblioteca_30, q="99")

    assert resultado["fuera_de_rango"] is True
    assert resultado["total"] == 30


def test_la_lista_de_un_sdf_ajeno_da_el_404_de_siempre(client, db_session, usuario_autenticado,
                                                       otro_usuario_autenticado):
    ajeno = _resultado(db_session, otro_usuario_autenticado, "completado")

    _respuestas_iguales(client, usuario_autenticado,
                        "/visor/ficheros/test_visor_no_existe.sdf/moleculas",
                        "/visor/ficheros/{}/moleculas".format(ajeno))


def test_la_lista_de_un_fichero_que_no_es_sdf_se_rechaza(client, usuario_autenticado):
    """Solo un SDF se recorre por moleculas; lo demas se abre entero (RF-5)."""
    pdb = _subir(client, usuario_autenticado, "test_visor_lista.pdb",
                 b"HETATM    1  C1  LIG X   1       0.000   0.000   0.000  1.00  0.00           C\nEND\n",
                 tipo="molecula")

    respuesta = client.get("/visor/ficheros/{}/moleculas".format(pdb), headers=usuario_autenticado["headers"])

    assert respuesta.status_code == 400


# ---------------------------------------------------------------------------
# GET /visor/ficheros/{nombre}/molecula (T19, RF-5, RF-9, RF-10, RF-12)
# ---------------------------------------------------------------------------

ETANOL = (
    "etanol\n  prueba          3D\n\n"
    "  3  2  0  0  0  0  0  0  0  0999 V2000\n"
    "   -0.8883    0.1670    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "    0.4931   -0.3966    0.2150 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "    1.3952    0.6316   -0.1200 O   0  0  0  0  0  0  0  0  0  0  0  0\n"
    "  1  2  1  0\n  2  3  1  0\nM  END\n"
    "> <afinidad>\n-7.4\n\n$$$$\n"
)

PDB_PROTEINA = (
    "SEQRES   1 A    1  ALA\n"
    "ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N\n"
    "ATOM      2  CA  ALA A   1       1.400   0.000   0.100  1.00  0.00           C\n"
    "END\n"
)


def _molecula(client, usuario, nombre, **params):
    return client.get("/visor/ficheros/{}/molecula".format(nombre), params=params, headers=usuario["headers"])


def test_una_molecula_de_una_biblioteca(client, usuario_autenticado):
    lote = _subir(client, usuario_autenticado, "test_visor_mol.sdf", (ETANOL * 2).encode())

    respuesta = _molecula(client, usuario_autenticado, lote, posicion=2)

    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["nombre"] == "etanol"
    assert datos["posicion"] == 2
    assert datos["num_atomos"] == 3
    assert datos["campos"] == [{"nombre": "afinidad", "valor": "-7.4"}]
    assert datos["es_proteina"] is False
    assert datos["dibujable"] is True
    assert datos["contenido"].count("$$$$") == 1


def test_un_pdb_se_abre_entero_y_declara_proteina(client, usuario_autenticado):
    pdb = _subir(client, usuario_autenticado, "test_visor_receptor.pdb", PDB_PROTEINA.encode(), tipo="molecula")

    datos = _molecula(client, usuario_autenticado, pdb).json()

    assert datos["es_proteina"] is True
    assert datos["num_atomos"] == 2
    assert datos["posicion"] is None


def test_un_smiles_no_se_puede_dibujar(client, usuario_autenticado):
    smi = _subir(client, usuario_autenticado, "test_visor_cafeina.smi",
                 b"CN1C=NC2=C1C(=O)N(C(=O)N2C)C cafeina\n", tipo="molecula")

    datos = _molecula(client, usuario_autenticado, smi).json()

    assert datos["dibujable"] is False
    assert "3D" in datos["motivo"]


def test_una_biblioteca_sin_posicion_pide_elegir(client, usuario_autenticado):
    lote = _subir(client, usuario_autenticado, "test_visor_sinpos.sdf", (ETANOL * 2).encode())

    respuesta = _molecula(client, usuario_autenticado, lote)

    assert respuesta.status_code == 400


def test_una_posicion_que_no_existe_da_404(client, usuario_autenticado):
    lote = _subir(client, usuario_autenticado, "test_visor_fuera.sdf", (ETANOL * 2).encode())

    respuesta = _molecula(client, usuario_autenticado, lote, posicion=3)

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "Esa molécula no existe en el fichero."


def test_una_molecula_ajena_da_el_404_de_siempre(client, db_session, usuario_autenticado,
                                                otro_usuario_autenticado):
    ajeno = _resultado(db_session, otro_usuario_autenticado, "completado")

    _respuestas_iguales(client, usuario_autenticado,
                        "/visor/ficheros/test_visor_no_existe.sdf/molecula?posicion=1",
                        "/visor/ficheros/{}/molecula?posicion=1".format(ajeno))


# ---------------------------------------------------------------------------
# GET /visor/ficheros/{nombre}/descarga (T20, RF-11)
# ---------------------------------------------------------------------------

def _descarga(client, usuario, nombre, **params):
    return client.get("/visor/ficheros/{}/descarga".format(nombre), params=params, headers=usuario["headers"])


def test_descargar_un_registro_trae_solo_ese_con_sus_campos(client, usuario_autenticado):
    otro = ETANOL.replace("etanol\n", "metanol\n", 1).replace("-7.4", "-5.1")
    lote = _subir(client, usuario_autenticado, "test_visor_desc.sdf", (ETANOL + otro).encode())

    respuesta = _descarga(client, usuario_autenticado, lote, posicion=2)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.content.count(b"$$$$") == 1
    assert respuesta.content.startswith(b"metanol")
    assert b"> <afinidad>\n-5.1" in respuesta.content
    assert 'filename="test_visor_desc_metanol_n2.sdf"' in respuesta.headers["content-disposition"]


def test_descargar_un_fichero_entero_lo_trae_byte_a_byte(client, usuario_autenticado):
    pdb = _subir(client, usuario_autenticado, "test_visor_desc.pdb", PDB_PROTEINA.encode(), tipo="molecula")

    respuesta = _descarga(client, usuario_autenticado, pdb)

    assert respuesta.status_code == 200
    assert respuesta.content == PDB_PROTEINA.encode()


def test_el_nombre_de_la_descarga_no_sale_de_la_carpeta(client, usuario_autenticado):
    """El nombre sale del titulo del registro, que escribe quien sube el SDF."""
    malicioso = ETANOL.replace("etanol\n", "../../..\\windows/x\n", 1)
    lote = _subir(client, usuario_autenticado, "test_visor_mal.sdf", (malicioso * 2).encode())

    disposicion = _descarga(client, usuario_autenticado, lote, posicion=1).headers["content-disposition"]
    nombre = disposicion.split('filename="', 1)[1].rstrip('"')

    assert "/" not in nombre and "\\" not in nombre and ".." not in nombre


def test_descargar_algo_ajeno_da_el_404_de_siempre(client, db_session, usuario_autenticado,
                                                  otro_usuario_autenticado):
    ajeno = _resultado(db_session, otro_usuario_autenticado, "completado")

    _respuestas_iguales(client, usuario_autenticado,
                        "/visor/ficheros/test_visor_no_existe.sdf/descarga?posicion=1",
                        "/visor/ficheros/{}/descarga?posicion=1".format(ajeno))


def test_un_nombre_con_ruta_se_rechaza(db_session, usuario_autenticado):
    """Un intento de salir de uploads/ se rechaza explicitamente (400), como en /uploads."""
    from fastapi import HTTPException

    from app.main import fichero_del_visor
    with pytest.raises(HTTPException) as error:
        fichero_del_visor("../app/main.py", db_session, _usuario_db(db_session, usuario_autenticado))
    assert error.value.status_code == 400
