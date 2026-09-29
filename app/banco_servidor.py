"""
Servicio aislado que ejecuta el banco de pruebas de algoritmos.

Es un proceso diminuto --un solo endpoint útil-- cuya razón de ser no es lo que
hace sino DÓNDE lo hace. Corre en el contenedor `banco` del
`docker-compose.yml`, que a diferencia del backend:

  · no monta `uploads/` ni `algoritmos/`: no ve ningún fichero de ningún
    usuario ni puede reescribir el catálogo. Las moléculas de referencia van
    horneadas en la imagen;
  · no recibe ninguna variable de entorno con secretos (ni `DATABASE_URL`, ni
    `JWT_SECRET_KEY`, ni credenciales de correo o del clúster);
  · está en una red `internal`, sin salida a internet y sin acceso a PostgreSQL
    ni a Redis: solo el backend puede hablar con él;
  · corre como usuario sin privilegios, con el sistema de ficheros en solo
    lectura salvo un `tmpfs`, sin capacidades y con límites de memoria y de
    número de procesos.

Así, el peor caso de un algoritmo malicioso deja de ser «firmarse un token de
administrador y exfiltrar la base de datos» y pasa a ser «gastar CPU dentro de
un contenedor sin nada que robar hasta que salte el límite de tiempo».

No expone puerto al anfitrión: solo es alcanzable desde la red interna.
"""
import os
import tempfile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from app.banco_pruebas import INVOCACIONES, probar_en_proceso

# El mismo tope que aplica el endpoint de subida. Se repite aquí a propósito:
# este servicio no debe confiar en que quien le llama ya haya validado nada.
MAX_BYTES = int(os.getenv("MAX_ALGORITMO_KB", "512")) * 1024

app = FastAPI(
    title="Banco de pruebas de algoritmos",
    description="Ejecuta algoritmos no verificados en aislamiento.",
    # Sin documentación interactiva: no es una API pública y no hay ninguna
    # razón para servir superficie de más en el proceso que ejecuta código
    # ajeno.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/salud")
def salud():
    """Sonda de vida. El backend la usa para no aceptar subidas si esto no responde."""
    return {"estado": "ok", "tipos": sorted(INVOCACIONES)}


@app.post("/probar")
async def probar(tipo: str = Form(...), archivo: UploadFile = File(...)):
    """
    Ejecuta el algoritmo recibido contra las moléculas de referencia.

    Devuelve el veredicto tal cual lo produce el banco, incluida la salida del
    script: el autor la necesita para corregirlo y aquí no hay nada sensible
    que filtrar, precisamente porque este proceso no conoce ningún secreto.
    """
    contenido = await archivo.read(MAX_BYTES + 1)
    if len(contenido) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"El script supera el tamaño máximo permitido ({MAX_BYTES // 1024} KB).",
        )
    if not contenido:
        raise HTTPException(status_code=400, detail="El script está vacío.")

    if tipo not in INVOCACIONES:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de algoritmo desconocido: '{tipo}'.",
        )

    # basename: el nombre lo elige quien sube el fichero, así que no se usa
    # para construir ninguna ruta sin sanear, ni siquiera dentro del sandbox.
    nombre = os.path.basename(archivo.filename or "algoritmo.py")
    if not nombre.endswith(".py"):
        nombre = "algoritmo.py"

    with tempfile.TemporaryDirectory(prefix="recibido_") as tmp:
        ruta = os.path.join(tmp, nombre)
        with open(ruta, "wb") as f:
            f.write(contenido)
        return probar_en_proceso(ruta, tipo).como_dict()
