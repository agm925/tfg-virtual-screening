"""
Guarda contra la reaparicion de un N+1 en los listados.

Un N+1 no se ve leyendo el codigo: `p.algoritmo.nombre` parece un acceso a un
atributo, pero cada iteracion dispara su propio SELECT. Tampoco se detecta con
un test funcional, porque la respuesta es correcta -- solo cambia el numero de
consultas.

Estos tests no fijan un numero magico de consultas, que seria fragil ante
cualquier refactor: comprueban la propiedad que de verdad importa, que el
numero de consultas NO CREZCA con el numero de filas devueltas. Es lo que
distingue una carga con joinedload de una carga perezosa fila a fila.

Se usan algoritmos y workflows DISTINTOS a proposito. Con una sola entidad
relacionada compartida el problema no se manifiesta, porque el identity map de
SQLAlchemy la reutiliza tras la primera carga; el N+1 solo aparece cuando cada
fila apunta a una entidad distinta.
"""
from sqlalchemy import event

from app import models
from app.database import engine


SCRIPT_DUMMY = b"# TIPO_ALGORITMO: preprocesado\nprint('dummy')\n"


class ContadorDeConsultas:
    """Cuenta los SELECT que llegan al motor mientras dura el bloque."""

    def __init__(self):
        self.sentencias = []

    def __enter__(self):
        event.listen(engine, "before_cursor_execute", self._anotar)
        return self

    def __exit__(self, *exc):
        event.remove(engine, "before_cursor_execute", self._anotar)
        return False

    def _anotar(self, conn, cursor, statement, parameters, context, executemany):
        self.sentencias.append(statement)

    @property
    def selects(self):
        return [s for s in self.sentencias if s.lstrip().upper().startswith("SELECT")]


def _crear_peticiones(db_session, usuario_id, cuantas, prefijo):
    """Crea `cuantas` peticiones, cada una con su PROPIO algoritmo."""
    for i in range(cuantas):
        algoritmo = models.Algoritmo(
            nombre=f"{prefijo}_alg_{i}",
            descripcion="dummy",
            tipo=models.TipoAlgoritmo.preprocesado,
            ruta_archivo=f"{prefijo}_{i}.py",
            es_publico=True,
            autor_id=usuario_id,
        )
        db_session.add(algoritmo)
        db_session.flush()
        db_session.add(models.Peticion(
            estado="COMPLETADO",
            ruta_mol_original=f"{prefijo}_{i}.mol2",
            usuario_id=usuario_id,
            algoritmo_id=algoritmo.id,
        ))
    db_session.commit()


def _crear_ejecuciones(db_session, usuario_id, cuantas, prefijo):
    """Crea `cuantas` ejecuciones, cada una de su PROPIO workflow."""
    for i in range(cuantas):
        workflow = models.Workflow(
            nombre=f"{prefijo}_wf_{i}",
            descripcion="dummy",
            grafo_json={"nodes": [], "edges": []},
            usuario_id=usuario_id,
            estado="completado",
        )
        db_session.add(workflow)
        db_session.flush()
        db_session.add(models.WorkflowExecution(
            workflow_id=workflow.id,
            usuario_id=usuario_id,
            estado="completado",
            resultados_json={"resultados": {}},
        ))
    db_session.commit()


def test_historial_de_peticiones_no_crece_en_consultas_con_las_filas(
    client, db_session, usuario_autenticado
):
    usuario_id = usuario_autenticado["usuario"]["id"]
    headers = usuario_autenticado["headers"]
    ruta = f"/peticiones/usuario/{usuario_id}"

    _crear_peticiones(db_session, usuario_id, 2, "test_n1_pet_a")
    with ContadorDeConsultas() as pocas:
        assert client.get(ruta, headers=headers).status_code == 200

    _crear_peticiones(db_session, usuario_id, 6, "test_n1_pet_b")
    with ContadorDeConsultas() as muchas:
        respuesta = client.get(ruta, headers=headers)
        assert respuesta.status_code == 200

    assert len(respuesta.json()) >= 8, "el listado deberia traer las 8 peticiones"
    assert len(muchas.selects) == len(pocas.selects), (
        f"El numero de consultas crecio con las filas "
        f"({len(pocas.selects)} -> {len(muchas.selects)}): ha vuelto el N+1. "
        f"Comprueba el joinedload de listar_peticiones_usuario."
    )


def test_historial_de_ejecuciones_no_crece_en_consultas_con_las_filas(
    client, db_session, usuario_autenticado
):
    usuario_id = usuario_autenticado["usuario"]["id"]
    headers = usuario_autenticado["headers"]
    ruta = f"/ejecuciones/usuario/{usuario_id}"

    _crear_ejecuciones(db_session, usuario_id, 2, "test_n1_eje_a")
    with ContadorDeConsultas() as pocas:
        assert client.get(ruta, headers=headers).status_code == 200

    _crear_ejecuciones(db_session, usuario_id, 6, "test_n1_eje_b")
    with ContadorDeConsultas() as muchas:
        respuesta = client.get(ruta, headers=headers)
        assert respuesta.status_code == 200

    assert len(respuesta.json()) >= 8, "el listado deberia traer las 8 ejecuciones"
    assert len(muchas.selects) == len(pocas.selects), (
        f"El numero de consultas crecio con las filas "
        f"({len(pocas.selects)} -> {len(muchas.selects)}): ha vuelto el N+1. "
        f"Comprueba el joinedload de listar_ejecuciones_usuario."
    )


def test_los_indices_declarados_existen_en_la_base_de_datos():
    """
    create_all() solo crea indices al crear la tabla: sobre una base ya
    existente, los indices anadidos despues a los modelos no se aplicarian
    nunca. scripts/migrate.py los crea con checkfirst; esta prueba comprueba
    que el esquema real coincide con el declarado.
    """
    from sqlalchemy import inspect

    inspector = inspect(engine)
    for tabla in models.Base.metadata.sorted_tables:
        declarados = {i.name for i in tabla.indexes}
        if not declarados:
            continue
        existentes = {i["name"] for i in inspector.get_indexes(tabla.name)}
        faltan = declarados - existentes
        assert not faltan, f"faltan indices en {tabla.name}: {sorted(faltan)}"
