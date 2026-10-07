"""
Tests de permisos.resultado_disponible (spec 002, RF-2).

El visor solo ofrece los resultados de ejecuciones y peticiones que han
terminado bien: el de una ejecucion en curso puede estar a medio escribir, y
el de una cancelada o con error, incompleto. Los ficheros subidos (biblioteca)
se ofrecen siempre.
"""
import uuid

import pytest

from app import models, permisos


def _archivo(db, visibilidad, ejecucion_id=None, peticion_id=None):
    archivo = models.Archivo(
        nombre="test_disponible_{}.sdf".format(uuid.uuid4().hex[:10]),
        visibilidad=visibilidad,
        tipo=models.TipoArchivo.resultado if visibilidad == models.VisibilidadArchivo.resultado
        else models.TipoArchivo.molecula,
        ejecucion_id=ejecucion_id,
        peticion_id=peticion_id,
    )
    db.add(archivo)
    db.commit()
    return archivo


def _ejecucion(db, estado):
    ejecucion = models.WorkflowExecution(workflow_id=None, usuario_id=None, estado=estado)
    db.add(ejecucion)
    db.commit()
    return ejecucion.id


def _peticion(db, estado):
    peticion = models.Peticion(estado=estado, ruta_mol_original="x.sdf")
    db.add(peticion)
    db.commit()
    return peticion.id


def test_un_fichero_subido_esta_siempre_disponible(db_session):
    archivo = _archivo(db_session, models.VisibilidadArchivo.biblioteca)

    assert permisos.resultado_disponible(archivo, db_session) is True


def test_el_resultado_de_una_ejecucion_completada_esta_disponible(db_session):
    archivo = _archivo(db_session, models.VisibilidadArchivo.resultado,
                       ejecucion_id=_ejecucion(db_session, "completado"))

    assert permisos.resultado_disponible(archivo, db_session) is True


@pytest.mark.parametrize("estado", ["pendiente", "procesando", "cancelado", "error"])
def test_el_resultado_de_una_ejecucion_sin_terminar_bien_no_esta_disponible(db_session, estado):
    archivo = _archivo(db_session, models.VisibilidadArchivo.resultado,
                       ejecucion_id=_ejecucion(db_session, estado))

    assert permisos.resultado_disponible(archivo, db_session) is False


def test_el_resultado_de_una_peticion_completada_esta_disponible(db_session):
    archivo = _archivo(db_session, models.VisibilidadArchivo.resultado,
                       peticion_id=_peticion(db_session, "COMPLETADO"))

    assert permisos.resultado_disponible(archivo, db_session) is True


@pytest.mark.parametrize("estado", ["PENDIENTE", "PROCESANDO", "ERROR"])
def test_el_resultado_de_una_peticion_sin_terminar_bien_no_esta_disponible(db_session, estado):
    archivo = _archivo(db_session, models.VisibilidadArchivo.resultado,
                       peticion_id=_peticion(db_session, estado))

    assert permisos.resultado_disponible(archivo, db_session) is False


def test_el_filtro_de_la_consulta_dice_lo_mismo_que_la_funcion(db_session):
    """
    La lista del visor filtra en SQL (una consulta, no una por fichero) con
    solo_disponibles(); las lecturas sueltas usan resultado_disponible(). Es
    la misma regla escrita dos veces, asi que se comprueba que coinciden en
    todos los casos.
    """
    casos = [_archivo(db_session, models.VisibilidadArchivo.biblioteca),
             _archivo(db_session, models.VisibilidadArchivo.resultado)]
    for estado in ("completado", "pendiente", "procesando", "cancelado", "error"):
        casos.append(_archivo(db_session, models.VisibilidadArchivo.resultado,
                              ejecucion_id=_ejecucion(db_session, estado)))
    for estado in ("COMPLETADO", "PENDIENTE", "PROCESANDO", "ERROR"):
        casos.append(_archivo(db_session, models.VisibilidadArchivo.resultado,
                              peticion_id=_peticion(db_session, estado)))
    ids = [a.id for a in casos]

    por_consulta = {a.id for a in permisos.solo_disponibles(
        db_session.query(models.Archivo).filter(models.Archivo.id.in_(ids)))}

    assert por_consulta == {a.id for a in casos if permisos.resultado_disponible(a, db_session)}


def test_un_resultado_sin_ejecucion_ni_peticion_esta_disponible(db_session):
    """
    Los resultados anteriores a que se anotara su origen no dicen de que
    ejecucion vienen. No hay estado que mirar, asi que se ofrecen, igual que
    los sigue ofreciendo el resto de la plataforma.
    """
    archivo = _archivo(db_session, models.VisibilidadArchivo.resultado)

    assert permisos.resultado_disponible(archivo, db_session) is True
