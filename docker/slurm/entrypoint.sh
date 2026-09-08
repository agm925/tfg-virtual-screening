#!/bin/bash
# Arranque del clúster SLURM de un nodo.
#
# El orden importa y no es negociable:
#   munged  →  slurmdbd  →  (registrar el clúster)  →  slurmctld  →  slurmd  →  sshd
#
# munged va primero porque los demás se autentican entre sí con munge.
# slurmdbd va antes que slurmctld porque slurm.conf declara
# AccountingStorageType=accounting_storage/slurmdbd: si el controlador arranca
# sin su base de accounting, los jobs no se registran y `sacct` -- que es lo
# que sondea app/slurm_executor.py -- devuelve vacío para siempre.
set -euo pipefail

log() { echo "[slurm-sim] $*"; }

esperar_puerto() {
    local host=$1 puerto=$2 etiqueta=$3 intentos=${4:-60}
    log "esperando a ${etiqueta} (${host}:${puerto})..."
    for _ in $(seq 1 "${intentos}"); do
        if (echo > "/dev/tcp/${host}/${puerto}") 2>/dev/null; then
            log "${etiqueta} disponible"
            return 0
        fi
        sleep 2
    done
    log "ERROR: ${etiqueta} no respondió a tiempo"
    return 1
}

# /run suele ser tmpfs y se vacía en cada arranque del contenedor, así que los
# directorios y dueños se rehacen aquí y no solo en el Dockerfile.
mkdir -p /run/munge /var/spool/slurmctld /var/spool/slurmd /var/log/slurm /var/run/sshd
chown -R munge:munge /run/munge
chown -R slurm:slurm /var/spool/slurmctld /var/log/slurm

log "arrancando munged"
runuser -u munge -- /usr/sbin/munged --force
sleep 1

esperar_puerto slurmdb 3306 "MariaDB de accounting"

log "arrancando slurmdbd"
/usr/sbin/slurmdbd
esperar_puerto localhost 6819 "slurmdbd"

# El clúster tiene que existir en la base de accounting o slurmctld no puede
# registrar jobs. Si ya está creado, sacctmgr devuelve error: no es un fallo.
log "registrando el clúster en accounting"
sacctmgr -i add cluster tfgcluster 2>/dev/null || log "  (el clúster ya existía)"

log "arrancando slurmctld"
/usr/sbin/slurmctld
sleep 2

log "arrancando slurmd"
/usr/sbin/slurmd
sleep 2

# El nodo puede quedar DOWN si el contenedor se reinició de forma abrupta.
# ReturnToService=2 lo recupera solo, pero forzarlo aquí evita una primera
# ejecución en la que todos los jobs se quedan en cola sin explicación.
scontrol update NodeName=slurm State=RESUME 2>/dev/null || true

log "arrancando sshd"
/usr/sbin/sshd

log "estado del clúster:"
sinfo || true

log "listo — el clúster acepta trabajos"

# Mantener el contenedor vivo mostrando los logs, que es lo que querrás mirar
# cuando un job falle (docker compose logs -f slurm).
exec tail -F /var/log/slurm/slurmctld.log /var/log/slurm/slurmd.log 2>/dev/null
