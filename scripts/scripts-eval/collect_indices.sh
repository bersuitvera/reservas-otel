#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=eval_env.sh
source "${SCRIPT_DIR}/eval_env.sh"

OUT_ROOT="$(eval_resolve_path "${OUT_ROOT:-results}" "$SCRIPT_DIR")"
OUT_DIR="${1:-${OUT_ROOT}/manual_indices_$(date +%Y%m%d_%H%M%S)}"
OUT_DIR="$(eval_resolve_path "$OUT_DIR" "$SCRIPT_DIR")"
mkdir -p "$OUT_DIR"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "[ERROR] Comando requerido no disponible: $1" >&2
    exit 1
  }
}

require_cmd curl
require_cmd python3

ENGINE_URL="${ENGINE_URL:-http://localhost:9200}"
ENGINE_INSECURE="${ENGINE_INSECURE:-true}"

CURL_OPTS=(-sS)

if [[ "${ENGINE_INSECURE}" == "true" ]]; then
  CURL_OPTS+=(-k)
fi

if [[ -n "${ENGINE_USER:-}" && -n "${ENGINE_PASS:-}" ]]; then
  CURL_OPTS+=(-u "${ENGINE_USER}:${ENGINE_PASS}")
fi

request() {
  local path="$1"
  local outfile="$2"
  local statusfile="${outfile}.status"

  local status
  status="$(curl "${CURL_OPTS[@]}" -w "%{http_code}" -o "$outfile" "${ENGINE_URL%/}${path}" || true)"
  echo "$status" > "$statusfile"

  if [[ "$status" =~ ^2 ]]; then
    echo "[OK] ${path} -> ${outfile}"
  else
    echo "[WARN] ${path} devolvió HTTP ${status}. Ver ${outfile}" >&2
  fi
}

request "/" "${OUT_DIR}/engine_root.json"
request "/_cluster/health?pretty" "${OUT_DIR}/cluster_health.json"
request "/_cluster/stats?human&pretty" "${OUT_DIR}/cluster_stats.json"
request "/_nodes/stats/jvm,process,fs,indices?human&pretty" "${OUT_DIR}/nodes_stats.json"
request "/_stats/docs,store,indexing,search,segments?human&pretty" "${OUT_DIR}/indices_stats.json"
request "/_cat/indices?format=json&bytes=mb" "${OUT_DIR}/indices.json"
request "/_cat/count?format=json" "${OUT_DIR}/count.json"
request "/_cat/templates?format=json" "${OUT_DIR}/templates.json"
request "/_cat/shards?format=json&bytes=mb" "${OUT_DIR}/shards.json"
request "/_cat/nodes?format=json" "${OUT_DIR}/nodes.json"
request "/_cat/allocation?format=json&bytes=mb" "${OUT_DIR}/allocation.json"
request "/_cat/thread_pool/search,index,write,management?format=json" "${OUT_DIR}/thread_pool.json"

case "${SCENARIO:-}" in
  escenario_a)
    printf 'skipped\n' > "${OUT_DIR}/data_streams.json.status"
    printf '{"skipped":true,"reason":"OpenSearch scenario A stores telemetry in indices; /_cat/data_streams is not available in this backend/version."}\n' > "${OUT_DIR}/data_streams.json"
    request "/_cat/indices/otel-v1-apm-*?format=json&bytes=mb" "${OUT_DIR}/indices_opensearch_otel_v1_apm.json"
    request "/_cat/indices/logs-otel-v1-*?format=json&bytes=mb" "${OUT_DIR}/indices_opensearch_logs_otel_v1.json"
    request "/_cat/indices/otel-v2-apm-service-map*?format=json&bytes=mb" "${OUT_DIR}/indices_opensearch_otel_v2_service_map.json"
    request "/_cat/indices/*service-map*?format=json&bytes=mb" "${OUT_DIR}/indices_opensearch_service_map_all.json"
    ;;
  escenario_b)
    request "/_data_stream/*" "${OUT_DIR}/data_streams.json"
    request "/_cat/indices/.ds-traces-*?format=json&bytes=mb" "${OUT_DIR}/indices_elastic_ds_traces.json"
    request "/_cat/indices/.ds-logs-*?format=json&bytes=mb" "${OUT_DIR}/indices_elastic_ds_logs.json"
    request "/_cat/indices/.ds-metrics-*?format=json&bytes=mb" "${OUT_DIR}/indices_elastic_ds_metrics.json"
    request "/_data_stream/traces-*" "${OUT_DIR}/data_streams_elastic_traces.json"
    request "/_data_stream/logs-*" "${OUT_DIR}/data_streams_elastic_logs.json"
    request "/_data_stream/metrics-*" "${OUT_DIR}/data_streams_elastic_metrics.json"
    ;;
  escenario_c)
    request "/_data_stream/*" "${OUT_DIR}/data_streams.json"
    request "/_cat/indices/.ds-traces-apm*?format=json&bytes=mb" "${OUT_DIR}/indices_elastic_traces_apm.json"
    request "/_cat/indices/.ds-metrics-apm*?format=json&bytes=mb" "${OUT_DIR}/indices_elastic_metrics_apm.json"
    request "/_cat/indices/.ds-logs-containerlogs-*?format=json&bytes=mb" "${OUT_DIR}/indices_elastic_logs_containerlogs.json"
    request "/_cat/indices/.ds-metrics-system.*?format=json&bytes=mb" "${OUT_DIR}/indices_elastic_metrics_system.json"
    request "/_cat/indices/.ds-metrics-docker.*?format=json&bytes=mb" "${OUT_DIR}/indices_elastic_metrics_docker.json"
    request "/_data_stream/traces-apm*" "${OUT_DIR}/data_streams_elastic_traces_apm.json"
    request "/_data_stream/metrics-apm*" "${OUT_DIR}/data_streams_elastic_metrics_apm.json"
    request "/_data_stream/logs-containerlogs-*" "${OUT_DIR}/data_streams_elastic_logs_containerlogs.json"
    request "/_data_stream/metrics-system.*" "${OUT_DIR}/data_streams_elastic_metrics_system.json"
    request "/_data_stream/metrics-docker.*" "${OUT_DIR}/data_streams_elastic_metrics_docker.json"
    ;;
  *)
    echo "[WARN] SCENARIO=${SCENARIO:-} no reconocido; solo se recogieron evidencias comunes." >&2
    ;;
esac

python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/summarize_indices.py" "$OUT_DIR"
python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/summarize_backend_health.py" "$OUT_DIR" "${SCENARIO:-unknown}"
