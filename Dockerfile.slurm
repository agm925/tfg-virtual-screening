# Clúster SLURM de un solo nodo, para simular Picasso en local.
#
# Ejercita el camino EXECUTION_MODE=slurm de punta a punta: SSH, SFTP, sbatch,
# sondeo con sacct y descarga de resultados. Sin esto, app/slurm_executor.py
# (229 líneas) no se ejecuta jamás en el entorno de desarrollo, porque
# docker-compose fija EXECUTION_MODE=local y el import de SlurmExecutor está
# diferido dentro de la función que lo usa.
#
# Parte de la MISMA imagen base que el backend, porque los algoritmos se
# ejecutan AQUÍ, en el nodo de cómputo, no en el worker de Celery: el nodo
# necesita RDKit y Open Babel o cada job moriría con ImportError.
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    # --- Pila SLURM ---
    #   slurm-wlm  → slurmctld (controlador) + slurmd (nodo de cómputo) + cliente
    #   slurmdbd   → demonio de accounting; SIN ÉL, `sacct` DEVUELVE VACÍO y
    #                _esperar_finalizacion() giraría hasta agotar el timeout.
    #   munge      → autenticación entre demonios SLURM
    slurm-wlm \
    slurmdbd \
    munge \
    # --- Acceso SSH: es como entra SlurmExecutor ---
    openssh-server \
    # --- Dependencias de los algoritmos ---
    openbabel \
    libxrender1 \
    libxext6 \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Mismas dependencias Python que el backend: si un algoritmo funciona en local,
# tiene que funcionar en el nodo. Instalarlas aquí evita que la simulación
# falle por un motivo que en Picasso no ocurriría.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# El script sbatch invoca "python3". En un job de SLURM el PATH es el mínimo
# que propaga sbatch, y en esta imagen python3 vive en /usr/local/bin. El
# enlace garantiza que se encuentre sin tener que tocar el generador de
# scripts sbatch de app/slurm_executor.py.
RUN ln -sf /usr/local/bin/python3 /usr/bin/python3

# Clave munge: cualquier clave sirve porque los tres demonios viven en el mismo
# contenedor, pero tiene que existir y tener permisos estrictos o munged no arranca.
RUN dd if=/dev/urandom of=/etc/munge/munge.key bs=1024 count=1 2>/dev/null \
    && chown munge:munge /etc/munge/munge.key \
    && chmod 400 /etc/munge/munge.key

# Directorios de estado que SLURM espera encontrar creados y con dueño correcto.
RUN mkdir -p /var/spool/slurmctld /var/spool/slurmd /var/log/slurm /run/munge \
    && chown -R slurm:slurm /var/spool/slurmctld /var/log/slurm \
    && chown -R munge:munge /run/munge

# Usuario que usará SlurmExecutor para entrar por SSH (SLURM_USER / SLURM_PASSWORD).
ARG SLURM_SIM_USER=tfg
ARG SLURM_SIM_PASSWORD=tfg
RUN useradd -m -s /bin/bash ${SLURM_SIM_USER} \
    && echo "${SLURM_SIM_USER}:${SLURM_SIM_PASSWORD}" | chpasswd \
    && mkdir -p /var/run/sshd

# Autenticación por contraseña: es la rama "else" de SlurmExecutor._conectar
# cuando no hay SLURM_SSH_KEY_PATH. Aceptable SOLO porque este contenedor es
# local y efímero; contra Picasso se usa clave SSH.
RUN sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config \
    && sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/'             /etc/ssh/sshd_config \
    && ssh-keygen -A

COPY docker/slurm/slurm.conf    /etc/slurm/slurm.conf
COPY docker/slurm/slurmdbd.conf /etc/slurm/slurmdbd.conf
RUN chown slurm:slurm /etc/slurm/slurmdbd.conf && chmod 600 /etc/slurm/slurmdbd.conf

COPY docker/slurm/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 22
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
