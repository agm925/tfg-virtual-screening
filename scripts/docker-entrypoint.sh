#!/bin/bash
# Entrypoint de los contenedores backend y worker.
#
# Su única tarea extra es preparar known_hosts cuando EXECUTION_MODE=slurm.
#
# Por qué hace falta: SlurmExecutor._conectar usa paramiko.RejectPolicy(), que
# rechaza cualquier host cuya clave no esté ya en known_hosts. Eso está bien y
# debe quedarse así -- es lo que impide que alguien en la misma red se haga
# pasar por SLURM_HOST -- pero significa que un contenedor recién creado no
# puede conectar al clúster hasta que conoce su clave.
#
# Aquí se resuelve con ssh-keyscan, es decir, confiando en la clave que ofrezca
# el host la primera vez. Eso es aceptable ÚNICAMENTE en esta simulación local:
# el contenedor slurm vive en la red interna de Docker Compose y se destruye con
# ella. Contra Picasso NO se hace así: allí la huella se verifica por un canal
# de confianza y se añade a mano al known_hosts, como haría cualquier cliente
# SSH la primera vez.
set -euo pipefail

if [ "${EXECUTION_MODE:-local}" = "slurm" ] && [ -n "${SLURM_HOST:-}" ]; then
    puerto="${SLURM_PORT:-22}"
    mkdir -p /root/.ssh
    chmod 700 /root/.ssh

    echo "[entrypoint] EXECUTION_MODE=slurm — registrando la clave de ${SLURM_HOST}:${puerto}"
    for _ in $(seq 1 60); do
        if ssh-keyscan -p "${puerto}" -H "${SLURM_HOST}" 2>/dev/null | grep -q .; then
            break
        fi
        sleep 2
    done

    ssh-keyscan -p "${puerto}" -H "${SLURM_HOST}" >> /root/.ssh/known_hosts 2>/dev/null || true
    # Reejecutar el contenedor no debe duplicar entradas.
    sort -u /root/.ssh/known_hosts -o /root/.ssh/known_hosts
    chmod 600 /root/.ssh/known_hosts

    if grep -q . /root/.ssh/known_hosts 2>/dev/null; then
        echo "[entrypoint] clave registrada"
    else
        echo "[entrypoint] AVISO: no se pudo obtener la clave de ${SLURM_HOST}; las conexiones SSH fallarán"
    fi
fi

exec "$@"
