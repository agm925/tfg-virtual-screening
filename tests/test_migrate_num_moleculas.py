"""
Spec 008, R2: scripts/migrate.py rellena `num_moleculas` de los SDF que ya
estaban registrados sin el (los resultados, que hasta la spec 008 no se
contaban nunca), para que el visor 3D deje de decir «Contando moleculas…».
"""
import os

from app import models
from scripts import migrate

SDF_DOS = b"mol1\n\n\n  0  0\nM  END\n$$$$\nmol2\n\n\n  0  0\nM  END\n$$$$\n"


def _fila(db, nombre, num_moleculas=None):
    archivo = models.Archivo(
        nombre=nombre,
        visibilidad=models.VisibilidadArchivo.resultado,
        tipo=models.TipoArchivo.resultado,
        num_moleculas=num_moleculas,
    )
    db.add(archivo)
    db.commit()
    return archivo


def _num(db, nombre):
    db.expire_all()
    return db.query(models.Archivo).filter(models.Archivo.nombre == nombre).one().num_moleculas


def test_rellena_los_sdf_sin_recuento_y_no_toca_el_resto(db_session):
    sin_contar = "test_dummy_migrate_sin_contar.sdf"
    contado = "test_dummy_migrate_contado.sdf"
    huerfano = "test_dummy_migrate_huerfano.sdf"
    for nombre in (sin_contar, contado):
        with open(os.path.join("uploads", nombre), "wb") as f:
            f.write(SDF_DOS)
    _fila(db_session, sin_contar)
    _fila(db_session, contado, num_moleculas=7)
    _fila(db_session, huerfano)

    migrate.backfill_num_moleculas()

    assert _num(db_session, sin_contar) == 2
    # Ya contado: se respeta aunque no coincida con el fichero.
    assert _num(db_session, contado) == 7
    # Sin fichero en disco no hay nada que contar.
    assert _num(db_session, huerfano) is None

    # Idempotente: una segunda pasada no cambia nada.
    migrate.backfill_num_moleculas()
    assert _num(db_session, sin_contar) == 2
    assert _num(db_session, huerfano) is None
