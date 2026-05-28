#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -gt 0 && -n "${1:-}" ]]; then
  export SCENARIO="$1"
fi

# Carga defaults versionados por escenario y, después, overrides locales de .env.
# Las variables ya exportadas por el usuario tienen prioridad sobre ambos.
# shellcheck source=eval_env.sh
source "${SCRIPT_DIR}/eval_env.sh"

SCENARIO="${SCENARIO:-${EVAL_DETECTED_SCENARIO:-escenario}}"

HOST="${HOST:-http://localhost:8080}"
USERS="${USERS:-50}"
SPAWN_RATE="${SPAWN_RATE:-5}"
RUN_TIME="${RUN_TIME:-10m}"
SAMPLE_INTERVAL="${SAMPLE_INTERVAL:-5}"
POST_RUN_SLEEP="${POST_RUN_SLEEP:-30}"
OUT_ROOT="${OUT_ROOT:-results}"
LOCUSTFILE="${LOCUSTFILE:-locustfile.py}"
BASE_URL_GATEWAY="${BASE_URL_GATEWAY:-$HOST}"
export BASE_URL_GATEWAY

OUT_ROOT="$(eval_resolve_path "$OUT_ROOT" "$SCRIPT_DIR")"
LOCUSTFILE="$(eval_resolve_path "$LOCUSTFILE" "$SCRIPT_DIR")"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="${OUT_ROOT}/${SCENARIO}_${RUN_ID}"
LOCAL_ENV_FILE=""

if [[ -f "$EVAL_ENV_FILE" ]]; then
  LOCAL_ENV_FILE="$EVAL_ENV_FILE"
fi

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "[ERROR] Comando requerido no disponible: $1" >&2
    exit 1
  }
}

require_cmd curl
require_cmd docker
require_cmd locust
require_cmd python3

if [[ ! -f "$LOCUSTFILE" ]]; then
  echo "[ERROR] No existe LOCUSTFILE=${LOCUSTFILE}" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

cat > "${OUT_DIR}/metadata.env" <<EOF
GIT_BRANCH=${EVAL_GIT_BRANCH}
DETECTED_SCENARIO=${EVAL_DETECTED_SCENARIO}
SCENARIO=${SCENARIO}
BACKEND=${EVAL_BACKEND}
OBSERVABILITY_STACK=${EVAL_OBSERVABILITY_STACK}
RUN_ID=${RUN_ID}
HOST=${HOST}
USERS=${USERS}
SPAWN_RATE=${SPAWN_RATE}
RUN_TIME=${RUN_TIME}
SAMPLE_INTERVAL=${SAMPLE_INTERVAL}
POST_RUN_SLEEP=${POST_RUN_SLEEP}
OUT_ROOT=${OUT_ROOT}
OUT_DIR=${OUT_DIR}
LOCUSTFILE=${LOCUSTFILE}
CONTAINER_REGEX=${CONTAINER_REGEX:-}
ENGINE_URL=${ENGINE_URL:-http://localhost:9200}
PROMETHEUS_URL=${PROMETHEUS_URL:-}
EVAL_SCENARIO_DEFAULTS_FILE=${EVAL_SCENARIO_DEFAULTS_FILE}
EVAL_ENV_FILE=${EVAL_ENV_FILE}
EVAL_LOCAL_ENV_FILE=${LOCAL_ENV_FILE}
SCRIPT_DIR=${SCRIPT_DIR}
REPO_ROOT=${EVAL_REPO_ROOT}
STARTED_AT=$(date -Iseconds)
EOF

echo "[INFO] Directorio de salida: ${OUT_DIR}"
echo "[INFO] Rama detectada: ${EVAL_GIT_BRANCH:-unknown}"
echo "[INFO] Escenario detectado: ${EVAL_DETECTED_SCENARIO}; escenario activo: ${SCENARIO}"
echo "[INFO] Backend: ${EVAL_BACKEND}; stack: ${EVAL_OBSERVABILITY_STACK}"
echo "[INFO] Defaults cargados desde: ${EVAL_SCENARIO_DEFAULTS_FILE}"
if [[ -n "$LOCAL_ENV_FILE" ]]; then
  echo "[INFO] Overrides locales cargados desde: ${LOCAL_ENV_FILE}"
fi
echo "[INFO] Comprobando API Gateway: ${HOST%/}/health"

curl -fsS "${HOST%/}/health" > "${OUT_DIR}/gateway_health.json" || {
  echo "[ERROR] El API Gateway no responde en ${HOST%/}/health"
  exit 1
}

echo "[INFO] Iniciando muestreo docker stats cada ${SAMPLE_INTERVAL}s"
"${SCRIPT_DIR}/monitor_docker_stats.sh" "${OUT_DIR}/docker_stats_raw.jsonl" "${SAMPLE_INTERVAL}" &
MONITOR_PID=$!

cleanup() {
  if kill -0 "${MONITOR_PID}" 2>/dev/null; then
    kill "${MONITOR_PID}" 2>/dev/null || true
    wait "${MONITOR_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "[INFO] Lanzando Locust: usuarios=${USERS}, spawn_rate=${SPAWN_RATE}, duración=${RUN_TIME}"

locust \
  -f "${LOCUSTFILE}" \
  --host "${HOST}" \
  --headless \
  -u "${USERS}" \
  -r "${SPAWN_RATE}" \
  --run-time "${RUN_TIME}" \
  --csv "${OUT_DIR}/locust" \
  --html "${OUT_DIR}/locust_report.html"

echo "[INFO] Locust finalizado. Esperando ${POST_RUN_SLEEP}s para vaciado de colas e indexación final"
sleep "${POST_RUN_SLEEP}"

cleanup
trap - EXIT

echo "[INFO] Generando resúmenes de docker stats"
python3 "${SCRIPT_DIR}/summarize_docker_stats.py" \
  "${OUT_DIR}/docker_stats_raw.jsonl" \
  "${OUT_DIR}"

echo "[INFO] Recogiendo datos de índices/data streams"
"${SCRIPT_DIR}/collect_indices.sh" "${OUT_DIR}" || {
  echo "[WARN] No se pudieron recoger todos los datos de índices. Revisa ENGINE_URL/credenciales."
}

if [[ -n "${PROMETHEUS_URL:-}" ]]; then
  echo "[INFO] Recogiendo snapshot de Prometheus"
  "${SCRIPT_DIR}/collect_prometheus_snapshot.sh" "${OUT_DIR}/prometheus" || {
    echo "[WARN] No se pudieron recoger todas las métricas de Prometheus."
  }
else
  echo "[INFO] PROMETHEUS_URL no definido. Se omite snapshot de Prometheus."
fi

echo "FINISHED_AT=$(date -Iseconds)" >> "${OUT_DIR}/metadata.env"

echo "[OK] Prueba completada."
echo "[OK] Resultados en: ${OUT_DIR}"
