"""
Quien puede tocar cada fichero de uploads/.

Existe como modulo aparte, y no dentro de app/main.py, porque el motor de
workflows necesita las mismas reglas y no puede importar main: main importa
las tareas de Celery, que a su vez importan el motor. La consecuencia de esa
separacion era que la regla vivia solo en los endpoints HTTP y el motor
resolvia `uploads/<nombre>` a pelo, de modo que un nodo del grafo --que lo
manda el cliente-- podia nombrar el resultado privado de otro usuario y
hacer que la plataforma se lo procesara. La comprobacion tiene que estar
donde se abre el fichero, no solo en la puerta por la que se descarga.

Reglas (las mismas que aplicaba app/main.py):
  - resultado    -> solo su propietario o un admin.
  - biblioteca   -> cualquier usuario autenticado puede leerla; solo su
                    propietario o un admin puede borrarla.
  - sin registrar-> fichero anterior al registro de propiedad. Se trata como
                    biblioteca compartida; scripts/migrate.py los da de alta
                    en el primer arranque.
"""
from typing import Any, Dict, Iterable

from sqlalchemy.orm import Session

from app import models


class AccesoDenegado(Exception):
    """El usuario no puede leer --o borrar-- este fichero de uploads/."""

    def __init__(self, mensaje: str, nombre_archivo: str = ""):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.nombre_archivo = nombre_archivo


def archivo_registrado(nombre_archivo: str, db: Session):
    """Devuelve la fila de `archivos` para este nombre, o None si no consta."""
    return db.query(models.Archivo).filter(models.Archivo.nombre == nombre_archivo).first()


def comprobar_acceso_a_archivo(nombre_archivo: str, db: Session, usuario_id: int,
                               usuario_es_admin: bool = False,
                               para_borrar: bool = False) -> None:
    """
    Lanza AccesoDenegado si `usuario_id` no puede leer --o borrar-- el fichero.

    Se recibe el id del usuario y no el objeto, porque el motor de workflows
    corre en un worker de Celery y ahi lo unico que llega de la peticion
    original es el id.
    """
    archivo = archivo_registrado(nombre_archivo, db)
    if archivo is None:
        return

    if usuario_es_admin:
        return

    es_propietario = archivo.propietario_id == usuario_id

    if archivo.visibilidad == models.VisibilidadArchivo.resultado and not es_propietario:
        raise AccesoDenegado(
            "Este archivo es el resultado de una ejecución de otro usuario.",
            nombre_archivo,
        )

    if para_borrar and archivo.propietario_id is not None and not es_propietario:
        raise AccesoDenegado(
            "Solo el propietario puede borrar este archivo.",
            nombre_archivo,
        )


def nombres_de_archivo_del_grafo(grafo_json: Dict[str, Any]) -> Iterable[str]:
    """
    Nombres de uploads/ que el grafo referencia.

    Es `data.nombre_archivo` de los nodos de entrada (upload, selectMol y
    selectDB): es el UNICO campo del grafo que el motor convierte en una ruta
    dentro de uploads/ --ver los `os.path.join("uploads", ...)` de
    app/workflow_executor.py--. El resto de campos de `data` son parametros
    del algoritmo o apuntan al catalogo de algoritmos/, que es otro deposito.

    Se recorren TODOS los nodos y no solo los tres tipos conocidos: el tipo
    tambien lo elige el cliente, asi que filtrar por tipo seria fiarse de lo
    mismo que se esta comprobando. Si un nodo nuevo estrena el campo, queda
    cubierto desde el primer dia.
    """
    nombres = []
    for nodo in (grafo_json or {}).get("nodes", []):
        if not isinstance(nodo, dict):
            continue
        datos = nodo.get("data")
        if not isinstance(datos, dict):
            continue
        nombre = datos.get("nombre_archivo")
        if isinstance(nombre, str) and nombre:
            nombres.append(nombre)
    # Sin duplicados y en orden estable, para que el mensaje de error no
    # dependa de en que nodo se repitio la misma molecula.
    return sorted(set(nombres))


def comprobar_acceso_al_grafo(grafo_json: Dict[str, Any], db: Session, usuario_id: int,
                              usuario_es_admin: bool = False) -> None:
    """
    Lanza AccesoDenegado si el grafo referencia algun fichero que este usuario
    no puede leer.

    Se comprueba el grafo entero de una vez, antes de ejecutar nada, y no nodo
    a nodo durante la ejecucion: asi el flujo se rechaza sin haber llegado a
    abrir el fichero ajeno ni a dejar salidas a medias en uploads/.
    """
    for nombre in nombres_de_archivo_del_grafo(grafo_json):
        comprobar_acceso_a_archivo(nombre, db, usuario_id, usuario_es_admin)
