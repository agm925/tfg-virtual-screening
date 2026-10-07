"""
Spec 006: ningun secreto dentro de las imagenes de Docker.

Dockerfile.backend copia la carpeta entera (`COPY . .`) y el .dockerignore no
excluia secrets/: la clave privada del cluster acababa en /app/secrets/ssh/ de
la imagen, con permisos de lectura para todos, y la podia leer cualquier
algoritmo subido (corre como nobody). La plataforma no la necesitaba ahi: la
recibe montada en /root/ssh_montado al arrancar (docker-compose.yml).

Estas pruebas leen los ficheros como texto: no necesitan Docker. La
construccion real se comprueba en docs/specs/006-secretos-imagen/comprobaciones.md.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


def _patrones_dockerignore():
    lineas = (RAIZ / ".dockerignore").read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lineas if l.strip() and not l.strip().startswith("#")]


@pytest.mark.parametrize("patron", [
    "secrets/", ".claude/", "docs/", "CLAUDE.md", "MEMORY.md", "tests/", "*.stackdump", ".env.*",
])
def test_el_contexto_de_construccion_excluye(patron):
    assert patron in _patrones_dockerignore(), patron


def test_env_example_si_entra_porque_no_tiene_secretos():
    # Una excepcion explicita: sin ella, `.env.*` lo dejaria fuera.
    patrones = _patrones_dockerignore()
    assert "!.env.example" in patrones
    # Las excepciones de .dockerignore solo valen si van despues del patron.
    assert patrones.index("!.env.example") > patrones.index(".env.*")


def _dockerfile_backend():
    return (RAIZ / "Dockerfile.backend").read_text(encoding="utf-8")


def test_la_imagen_no_se_construye_si_se_cuela_un_secreto():
    lineas = _dockerfile_backend().splitlines()
    copia = lineas.index("COPY . .")
    siguiente_run = next(l for l in lineas[copia + 1:] if l.startswith("RUN "))
    # Justo despues de copiar, antes de cualquier otro paso.
    bloque = "\n".join(lineas[copia + 1:copia + 25])
    assert siguiente_run.startswith("RUN "), siguiente_run
    for buscado in ("secrets", "id_rsa", "id_ed25519", "id_ecdsa", ".env", "exit 1"):
        assert buscado in bloque, buscado


def test_la_imagen_no_crea_una_carpeta_secrets():
    # Nada usa /app/secrets: la clave llega montada en /root/ssh_montado.
    assert "mkdir -p uploads algoritmos secrets" not in _dockerfile_backend()


@pytest.mark.skipif(shutil.which("git") is None, reason="sin git")
def test_uploads_no_esta_en_el_repositorio():
    resultado = subprocess.run(["git", "ls-files", "uploads/"], cwd=RAIZ,
                               capture_output=True, text=True)
    if resultado.returncode != 0:
        pytest.skip("no es un repositorio de git")
    assert resultado.stdout.strip() == "", resultado.stdout
