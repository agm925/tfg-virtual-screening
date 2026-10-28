"""
scripts/migrate.py no registra los temporales de un cribado en lote
(_btmp_, _btrozo_, _bfrag_) y quita los que ya se habian colado: aparecian en
«Elegir molecula» despues de borrarse y el workflow que elegia uno fallaba.
"""
from app import models
from scripts import migrate


def _nombres(db):
    db.expire_all()
    return {n for (n,) in db.query(models.Archivo.nombre).all()}


def test_no_registra_temporales_de_cribado(db_session, tmp_path):
    for nombre in ("_btmp_e1_test_dummy_0.sdf", "_btrozo_e1_0.sdf",
                   "_bfrag_e1_0.json", "test_dummy_migrate_biblioteca.sdf"):
        (tmp_path / nombre).write_bytes(b"x")

    migrate.registrar_archivos_existentes(str(tmp_path))

    nombres = _nombres(db_session)
    assert "test_dummy_migrate_biblioteca.sdf" in nombres
    assert not any(n.startswith(migrate.TEMPORALES_DE_CRIBADO) for n in nombres)


def test_borra_del_registro_los_temporales_que_ya_estaban(db_session):
    for nombre in ("_btmp_e2_test_dummy_0.sdf", "test_dummy_migrate_conservar.sdf",
                   "x_btmp_test_dummy.sdf"):
        db_session.add(models.Archivo(
            nombre=nombre, visibilidad=models.VisibilidadArchivo.biblioteca))
    db_session.commit()

    migrate.borrar_temporales_registrados()

    nombres = _nombres(db_session)
    assert "_btmp_e2_test_dummy_0.sdf" not in nombres
    # Solo el prefijo cuenta: un nombre que lo lleva en medio se queda.
    assert {"test_dummy_migrate_conservar.sdf", "x_btmp_test_dummy.sdf"} <= nombres
