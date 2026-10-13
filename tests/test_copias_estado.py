"""
Spec 009, R7: app/copias_estado.py resume el estado.json que deja el servicio
de copias para la pagina Sistema. Si nadie mira las copias, nadie se entera
de que han dejado de hacerse.
"""
import json
from datetime import datetime, timedelta, timezone

from app import copias_estado

AHORA = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)


def _buena(hace):
    fecha = (AHORA - hace).astimezone(timezone(timedelta(hours=2)))   # hora de Madrid
    return {"copia": fecha.strftime("%Y-%m-%d_%H%M"), "fecha": fecha.isoformat(timespec="minutes"),
            "ficheros": 540, "bytes": 211686423, "volcado_bytes": 41232}


def test_sin_estado_no_hay_copias():
    assert copias_estado.resumir(None, AHORA)["estado"] == "sin_copias"
    assert copias_estado.resumir({}, AHORA)["estado"] == "sin_copias"


def test_una_copia_reciente_esta_bien():
    ultima = _buena(timedelta(hours=7))
    resumen = copias_estado.resumir({"ok": True, "error": None, "ultima_buena": ultima,
                                     "ultimo_intento": ultima["fecha"]}, AHORA)
    assert resumen["estado"] == "ok"
    assert resumen["ultima"] == ultima


def test_mas_de_26_horas_sin_copia_esta_atrasada():
    # Ni siquiera ha fallado: el servicio puede estar parado.
    ultima = _buena(timedelta(hours=27))
    resumen = copias_estado.resumir({"ok": True, "ultima_buena": ultima,
                                     "ultimo_intento": ultima["fecha"]}, AHORA)
    assert resumen["estado"] == "atrasada"


def test_si_el_ultimo_intento_fallo_esta_fallida_aunque_haya_una_buena():
    ultima = _buena(timedelta(hours=31))
    resumen = copias_estado.resumir({"ok": False, "error": "pg_dump ha fallado: x",
                                     "ultima_buena": ultima,
                                     "ultimo_intento": "2026-10-12T03:00+02:00"}, AHORA)
    assert resumen["estado"] == "fallida"
    assert resumen["error"] == "pg_dump ha fallado: x"
    assert resumen["ultima"] == ultima


def test_leer_tolera_un_fichero_que_no_existe_o_esta_roto(tmp_path):
    assert copias_estado.leer(tmp_path / "no_hay.json") is None
    roto = tmp_path / "estado.json"
    roto.write_text("{a medias", encoding="utf-8")
    assert copias_estado.leer(roto) is None
    roto.write_text(json.dumps({"ok": True}), encoding="utf-8")
    assert copias_estado.leer(roto) == {"ok": True}
