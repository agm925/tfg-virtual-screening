#!/bin/bash
# Entrypoint de los contenedores backend y worker.
#
# Su única tarea extra es preparar /root/.ssh cuando EXECUTION_MODE=slurm:
# instalar las credenciales del clúster y dejar su clave de host en known_hosts.
#
# Por qué hace falta: SlurmExecutor._conectar usa paramiko.RejectPolicy(), que
# rechaza cualquier host cuya clave no esté ya en known_hosts. Eso está bien y
# debe quedarse así -- es lo que impide que alguien en la misma red se haga
# pasar por SLURM_HOST -- pero significa que un contenedor recién creado no
# puede conectar al clúster hasta que conoce su clave.
#
# Hay dos caminos, y el que se toma depende de lo que venga montado:
#
#   · Si en el directorio montado en /ssh_ro (ver docker-compose.yml) viene un
#     known_hosts, se usa ese. Es el camino del clúster REAL: la huella se
#     verifica por un canal de confianza fuera de aquí y se deja en
#     secrets/ssh/known_hosts, igual que haría cualquier cliente SSH la
#     primera vez.
#
#   · Si no viene ninguno, se cae a ssh-keyscan, es decir, a confiar en la
#     clave que ofrezca el host la primera vez. Eso es aceptable ÚNICAMENTE en
#     la simulación local: el contenedor slurm vive en la red interna de Docker
#     Compose y se destruye con ella. Contra el bullx el aviso que se imprime
#     abajo hay que tomárselo en serio.
set -euo pipefail

if [ "${EXECUTION_MODE:-local}" = "slurm" ] && [ -n "${SLURM_HOST:-}" ]; then
    puerto="${SLURM_PORT:-22}"
    mkdir -p /root/.ssh
    chmod 700 /root/.ssh

    # --- Credenciales montadas (clave privada, known_hosts) -----------------
    #
    # Se copian en vez de usarse en su sitio porque el montaje es de solo
    # lectura y llega con los permisos que le dé el host: un bind mount desde
    # Windows aparece como 0777, y con eso el cliente ssh se niega a usar la
    # clave ("UNPROTECTED PRIVATE KEY FILE"). Aquí se les pone 600.
    if [ -d /ssh_ro ] && [ -n "$(ls -A /ssh_ro 2>/dev/null)" ]; then
        for origen in /ssh_ro/*; do
            [ -f "${origen}" ] || continue
            destino="/root/.ssh/$(basename "${origen}")"
            # known_hosts se acumula más abajo; el resto se copia tal cual.
            if [ "$(basename "${origen}")" = "known_hosts" ]; then
                continue
            fi
            cp "${origen}" "${destino}"
            chmod 600 "${destino}"
        done
        echo "[entrypoint] credenciales instaladas desde /ssh_ro"
    fi

    # --- Clave del host ------------------------------------------------------
    if [ -f /ssh_ro/known_hosts ] && grep -q . /ssh_ro/known_hosts; then
        cat /ssh_ro/known_hosts >> /root/.ssh/known_hosts
        echo "[entrypoint] known_hosts tomado del montaje (huella verificada fuera del contenedor)"
    else
        echo "[entrypoint] sin known_hosts montado — registrando la clave de ${SLURM_HOST}:${puerto} con ssh-keyscan"
        echo "[entrypoint] AVISO: esto confía en la clave que ofrezca el host AHORA. Solo es aceptable"
        echo "[entrypoint]        contra la simulación local; contra un clúster real, verifica la huella"
        echo "[entrypoint]        y déjala en secrets/ssh/known_hosts."
        for _ in $(seq 1 60); do
            if ssh-keyscan -p "${puerto}" -H "${SLURM_HOST}" 2>/dev/null | grep -q .; then
                break
            fi
            sleep 2
        done
        ssh-keyscan -p "${puerto}" -H "${SLURM_HOST}" >> /root/.ssh/known_hosts 2>/dev/null || true
    fi

    # Reejecutar el contenedor no debe duplicar entradas.
    if [ -f /root/.ssh/known_hosts ]; then
        sort -u /root/.ssh/known_hosts -o /root/.ssh/known_hosts
        chmod 600 /root/.ssh/known_hosts
    fi

    if grep -q . /root/.ssh/known_hosts 2>/dev/null; then
        echo "[entrypoint] clave registrada"
    else
        echo "[entrypoint] AVISO: no se pudo obtener la clave de ${SLURM_HOST}; las conexiones SSH fallarán"
    fi
fi

exec "$@"
