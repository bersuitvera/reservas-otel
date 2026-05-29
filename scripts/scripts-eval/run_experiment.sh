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

extract_correlation_trace_id() {
  local json_file="$1"

  python3 - "$json_file" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    sys.exit(0)

if isinstance(payload, dict):
    spans = payload.get("spans")
    if isinstance(spans, list):
        for span in spans:
            if isinstance(span, dict) and span.get("trace_id"):
                print(span["trace_id"])
                sys.exit(0)
            if isinstance(span, dict) and span.get("trace", {}).get("id"):
                print(span["trace"]["id"])
                sys.exit(0)

    hits = payload.get("hits", {}).get("hits", [])
    if isinstance(hits, list):
        for hit in hits:
            source = hit.get("_source", {}) if isinstance(hit, dict) else {}
            trace_id = source.get("traceId") or source.get("trace_id") or source.get("trace", {}).get("id")
            if trace_id:
                print(trace_id)
                sys.exit(0)
PY
}

collect_trace_correlation_evidence() {
  local trace_span_out="${OUT_DIR}/relacion_trace_span.json"
  local trace_span_err="${OUT_DIR}/relacion_trace_span.stderr"
  local logs_out="${OUT_DIR}/logs_correlacionados.json"
  local logs_err="${OUT_DIR}/logs_correlacionados.stderr"
  local trace_env="${OUT_DIR}/trace_correlation.env"
  local correlation_trace_id="${TRACE_ID:-}"

  echo "[INFO] Recogiendo relación trace/span y logs correlacionados"
  echo "TRACE_ID=${correlation_trace_id}" > "$trace_env"

  if [[ -n "$correlation_trace_id" ]]; then
    if ! "${SCRIPT_DIR}/relacion-trace-span.sh" "$correlation_trace_id" > "$trace_span_out" 2> "$trace_span_err"; then
      echo "[WARN] No se pudo recoger la relación trace/span. Ver ${trace_span_err}" >&2
    fi
  elif "${SCRIPT_DIR}/relacion-trace-span.sh" > "$trace_span_out" 2> "$trace_span_err"; then
    correlation_trace_id="$(extract_correlation_trace_id "$trace_span_out")"
    if [[ -n "$correlation_trace_id" ]]; then
      echo "TRACE_ID=${correlation_trace_id}" > "$trace_env"
    fi
  else
    echo "[WARN] No se pudo recoger la relación trace/span. Ver ${trace_span_err}" >&2
  fi

  if [[ -n "$correlation_trace_id" ]]; then
    if ! "${SCRIPT_DIR}/logs.sh" "$correlation_trace_id" > "$logs_out" 2> "$logs_err"; then
      echo "[WARN] No se pudieron recoger logs correlacionados para TRACE_ID=${correlation_trace_id}. Ver ${logs_err}" >&2
    fi
  else
    if ! "${SCRIPT_DIR}/logs.sh" > "$logs_out" 2> "$logs_err"; then
      echo "[WARN] No se pudieron recoger logs correlacionados. Ver ${logs_err}" >&2
    fi
  fi
}

collect_services_evidence() {
  local services_out="${OUT_DIR}/servicios.json"
  local services_err="${OUT_DIR}/servicios.stderr"
  local trace_env="${OUT_DIR}/trace_correlation.env"
  local correlation_trace_id="${TRACE_ID:-}"

  if [[ -z "$correlation_trace_id" && -f "$trace_env" ]]; then
    correlation_trace_id="$(sed -n 's/^TRACE_ID=//p' "$trace_env" | tail -n 1)"
  fi

  echo "[INFO] Recogiendo resumen de servicios observados"
  if [[ -n "$correlation_trace_id" ]]; then
    if ! "${SCRIPT_DIR}/servicios.sh" "$correlation_trace_id" > "$services_out" 2> "$services_err"; then
      echo "[WARN] No se pudo recoger resumen de servicios para TRACE_ID=${correlation_trace_id}. Ver ${services_err}" >&2
    fi
  elif ! "${SCRIPT_DIR}/servicios.sh" > "$services_out" 2> "$services_err"; then
    echo "[WARN] No se pudo recoger resumen de servicios. Ver ${services_err}" >&2
  fi
}

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

collect_trace_correlation_evidence
collect_services_evidence

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
