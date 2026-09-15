#!/usr/bin/env bash
#
# Tanda completa de escalado: 1, 2 y 4 workers sobre los mismos tres lotes.
#
# Se separa del propio benchmark.py a proposito: ese script mide UNA
# configuracion y no debe cambiar la que esta midiendo. Este orquesta las tres
# tandas, que es lo que hasta ahora se hacia a mano y por tanto no quedaba
# registrado en ninguna parte.
#
# Uso:  bash scripts/tanda_escalado.sh
set -u

cd "$(dirname "$0")/.."

LOTES="${LOTES:-100,500,1000}"
ESCALAS="${ESCALAS:-1 2 4}"

echo "Esperando al motor de Docker..."
until docker info >/dev/null 2>&1; do sleep 5; done
echo "Motor listo."

for n in $ESCALAS; do
  echo
  echo "=============================================================="
  echo " Levantando la plataforma con $n worker(s)"
  echo "=============================================================="
  docker compose up -d --scale worker="$n" || exit 1

  # La API tarda un poco en responder tras recrear los contenedores; sondear
  # es mas fiable que dormir una cantidad fija.
  echo "Esperando a que la API responda..."
  until curl -sf http://localhost:8000/ >/dev/null 2>&1; do sleep 3; done

  activos=$(docker compose ps --format '{{.Service}}' | grep -c '^worker$')
  echo "Workers activos segun docker compose: $activos"

  python scripts/benchmark.py --workers "$n" --batches "$LOTES" || exit 1
done

echo
echo "=============================================================="
echo " Tanda completa. Resultados en scripts/benchmark_results.csv"
echo "=============================================================="
cat scripts/benchmark_results.csv
