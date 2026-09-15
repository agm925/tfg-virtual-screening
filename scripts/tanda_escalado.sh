#!/usr/bin/env bash
#
# Tanda completa de escalado: N repeticiones de 1, 2 y 4 workers sobre los
# mismos tres lotes.
#
# Se separa del propio benchmark.py a proposito: ese script mide UNA
# configuracion y no debe cambiar la que esta midiendo. Este orquesta las
# tandas, que es lo que hasta ahora se hacia a mano y por tanto no quedaba
# registrado en ninguna parte.
#
# Las repeticiones van POR FUERA y las escalas por dentro. Al reves --las tres
# repeticiones de 1 worker seguidas, luego las de 2-- cualquier deriva de la
# maquina durante la tanda (termica, otro proceso, el directorio creciendo) se
# concentraria en una escala concreta y se leeria como si fuera efecto del
# numero de workers. Alternando, esa deriva se reparte entre todas.
#
# Uso:  bash scripts/tanda_escalado.sh
#       REPETICIONES=1 ESCALAS="1 4" bash scripts/tanda_escalado.sh
set -u

cd "$(dirname "$0")/.."

LOTES="${LOTES:-100,500,1000}"
ESCALAS="${ESCALAS:-1 2 4}"
REPETICIONES="${REPETICIONES:-3}"

# Reconstruir ANTES de medir, y sin argumentos. Es imprescindible: app/ no
# esta montado como volumen --solo lo estan uploads/ y algoritmos/--, asi que
# el codigo del backend y del worker va horneado en sus imagenes y
# "docker compose up" no lo actualiza. Sin esto se mide una version vieja del
# sistema creyendo que se mide HEAD. Y sin argumentos porque backend y worker
# son dos entradas de build distintas: reconstruir solo "backend" deja el
# worker atrasado, que es justo lo que paso en la primera tanda del 15-sep.
echo "Reconstruyendo las imagenes para medir el codigo actual..."
docker compose build || exit 1

echo "Esperando al motor de Docker..."
until docker info >/dev/null 2>&1; do sleep 5; done
echo "Motor listo."

for rep in $(seq 1 "$REPETICIONES"); do
  for n in $ESCALAS; do
    echo
    echo "=============================================================="
    echo " Repeticion $rep/$REPETICIONES  --  $n worker(s)"
    echo "=============================================================="
    docker compose up -d --scale worker="$n" || exit 1

    # La API tarda un poco en responder tras recrear los contenedores; sondear
    # es mas fiable que dormir una cantidad fija.
    echo "Esperando a que la API responda..."
    until curl -sf http://localhost:8000/ >/dev/null 2>&1; do sleep 3; done

    activos=$(docker compose ps --format '{{.Service}}' | grep -c '^worker$')
    if [ "$activos" -ne "$n" ]; then
      echo "ABORTADO: se pidieron $n workers y hay $activos activos." >&2
      exit 1
    fi
    echo "Workers activos confirmados: $activos"

    python scripts/benchmark.py --workers "$n" --batches "$LOTES" --repeticion "$rep" || exit 1
  done
done

echo
echo "=============================================================="
echo " Tanda completa. Resultados en scripts/benchmark_results.csv"
echo "=============================================================="
cat scripts/benchmark_results.csv
