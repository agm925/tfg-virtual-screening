"""
Spec 004, R7: los correos que manda la plataforma.

Antes decian «VirtualScreening», el de workflow terminado remitia al «KNIME
Builder», los de error copiaban el mensaje tecnico del algoritmo (trazas,
rutas del servidor) y los nombres de usuario, workflow y algoritmo se metian
en el HTML sin escapar.
"""
import inspect
import re

import pytest

from app import email_utils

URL_RTX = "https://rt.hpca.ual.es/molserver"


@pytest.fixture()
def enviados(monkeypatch):
    """(asunto, cuerpo) de cada correo, con la direccion publica del servidor."""
    capturados = []
    monkeypatch.setattr(email_utils, "PUBLIC_URL", URL_RTX)
    monkeypatch.setattr(email_utils, "enviar_correo",
                        lambda destinatario, asunto, cuerpo_html: capturados.append((asunto, cuerpo_html)) or True)
    return capturados


# Los cinco correos, con datos normales. El numero (12 o 34) es el de la
# peticion o la ejecucion.
CORREOS = {
    "verificacion":   lambda: email_utils.correo_verificacion("Ana", "ana@ual.es", "tok-1"),
    "peticion_ok":    lambda: email_utils.correo_completado("Ana", "ana@ual.es", 12, "filtroLipinski"),
    "peticion_error": lambda: email_utils.correo_error("Ana", "ana@ual.es", 12, "filtroLipinski"),
    "workflow_ok":    lambda: email_utils.correo_workflow_completado("Ana", "ana@ual.es", 34, "Docking HIV", 12.5),
    "workflow_error": lambda: email_utils.correo_workflow_error("Ana", "ana@ual.es", 34, "Docking HIV"),
}
DE_RESULTADO = {"peticion_ok": 12, "peticion_error": 12, "workflow_ok": 34, "workflow_error": 34}


@pytest.mark.parametrize("correo", CORREOS)
def test_todos_dicen_molserver_y_nada_de_knime(enviados, correo):
    CORREOS[correo]()
    asunto, cuerpo = enviados[0]

    assert "MolServer" in asunto and "MolServer" in cuerpo
    texto = (asunto + cuerpo).lower()
    for palabra in ("virtualscreening", "knime", "localhost"):
        assert palabra not in texto, palabra


@pytest.mark.parametrize("correo", DE_RESULTADO)
def test_los_de_resultado_llevan_a_la_seccion_resultados(enviados, correo):
    CORREOS[correo]()
    _, cuerpo = enviados[0]

    assert f'href="{URL_RTX}/"' in cuerpo
    assert "Resultados" in cuerpo
    assert re.search(rf"nº\s*{DE_RESULTADO[correo]}\b", cuerpo), "falta el número"


@pytest.mark.parametrize("funcion", [email_utils.correo_error, email_utils.correo_workflow_error])
def test_los_de_error_no_pueden_recibir_el_detalle_tecnico(funcion):
    # Principio 7: el mensaje del algoritmo o del motor puede llevar trazas y
    # rutas del servidor. Si la funcion no lo admite, no puede acabar en el
    # correo; el motivo se ve en la plataforma.
    parametros = set(inspect.signature(funcion).parameters)
    assert not parametros & {"detalle", "errores", "error"}, parametros


def test_los_de_error_dicen_donde_ver_el_motivo(enviados):
    email_utils.correo_workflow_error("Ana", "ana@ual.es", 34, "Docking HIV")
    _, cuerpo = enviados[0]

    assert "motivo" in cuerpo
    assert "Traceback" not in cuerpo and "/app/" not in cuerpo


def test_los_nombres_llegan_escapados(enviados):
    email_utils.correo_workflow_completado("<i>Ana</i>", "ana@ual.es", 34, "<b>x</b>", 1.0)
    _, cuerpo = enviados[0]

    assert "&lt;b&gt;x&lt;/b&gt;" in cuerpo and "<b>x</b>" not in cuerpo
    assert "&lt;i&gt;Ana&lt;/i&gt;" in cuerpo and "<i>Ana</i>" not in cuerpo


def test_un_salto_de_linea_en_el_nombre_no_cuela_cabeceras(enviados):
    # El asunto lleva el nombre del workflow, que escribe el usuario.
    email_utils.correo_workflow_error("Ana", "ana@ual.es", 34, "Docking\r\nBcc: alguien@ejemplo.com")
    asunto, _ = enviados[0]

    assert "\n" not in asunto and "\r" not in asunto


def test_los_colores_son_los_de_la_ual(enviados):
    email_utils.correo_completado("Ana", "ana@ual.es", 12, "filtroLipinski")
    _, cuerpo = enviados[0]

    assert "#0A4382" in cuerpo
    assert "#667eea" not in cuerpo.lower()
