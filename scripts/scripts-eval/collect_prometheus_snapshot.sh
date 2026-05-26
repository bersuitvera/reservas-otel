#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=eval_env.sh
source "${SCRIPT_DIR}/eval_env.sh"

OUT_ROOT="$(eval_resolve_path "${OUT_ROOT:-results}" "$SCRIPT_DIR")"
OUT_DIR="${1:-${OUT_ROOT}/manual_prometheus_$(date +%Y%m%d_%H%M%S)}"
OUT_DIR="$(eval_resolve_path "$OUT_DIR" "$SCRIPT_DIR")"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"

mkdir -p "$OUT_DIR"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "[ERROR] Comando requerido no disponible: $1" >&2
    exit 1
  }
}

require_cmd curl
require_cmd python3

queries=(
  "up"
  "up{job=\"otel-collector\"}"
  "up{job=\"data-prepper\"}"
  "up{job=\"opensearch\"}"
  "otelcol_receiver_accepted_spans_total"
  "otelcol_receiver_accepted_metric_points_total"
  "otelcol_receiver_accepted_log_records_total"
  "otelcol_exporter_sent_spans_total"
  "otelcol_exporter_sent_metric_points_total"
  "otelcol_exporter_sent_log_records_total"
  "otelcol_exporter_send_failed_spans_total"
  "otelcol_exporter_send_failed_metric_points_total"
  "otelcol_exporter_send_failed_log_records_total"
  "otelcol_exporter_queue_size"
  "otelcol_processor_batch_batch_send_size_count"
  "elasticsearch_cluster_health_status"
  "elasticsearch_cluster_health_number_of_nodes"
  "elasticsearch_cluster_health_active_shards"
  "elasticsearch_cluster_health_unassigned_shards"
  "elasticsearch_indices_docs"
  "elasticsearch_indices_store_size_bytes"
  "elasticsearch_thread_pool_rejected_count"
  "elasticsearch_jvm_memory_used_bytes"
  "entry_pipeline_BlockingBuffer_recordsInBuffer"
  "entry_pipeline_BlockingBuffer_recordsInFlight"
  "entry_pipeline_BlockingBuffer_recordsWriteFailed_total"
  "traces_raw_pipeline_opensearch_recordsIn_total"
  "logs_pipeline_opensearch_recordsIn_total"
  "service_map_pipeline_opensearch_recordsIn_total"
  "service_map_pipeline_prometheus_recordsIn_total"
  "traces_raw_pipeline_BlockingBuffer_recordsWriteFailed_total"
  "logs_pipeline_BlockingBuffer_recordsWriteFailed_total"
  "service_map_pipeline_BlockingBuffer_recordsWriteFailed_total"
  "process_cpu_seconds_total"
  "process_resident_memory_bytes"
)

for query in "${queries[@]}"; do
  encoded="$(python3 - <<PY
import urllib.parse
print(urllib.parse.quote("""${query}"""))
PY
)"
  safe_name="$(echo "$query" | tr -c 'A-Za-z0-9_' '_')"
  outfile="${OUT_DIR}/${safe_name}.json"

  status="$(curl -sS -w "%{http_code}" -o "$outfile" "${PROMETHEUS_URL%/}/api/v1/query?query=${encoded}" || true)"
  echo "$status" > "${outfile}.status"

  if [[ "$status" =~ ^2 ]]; then
    echo "[OK] Prometheus query '${query}' -> ${outfile}"
  else
    echo "[WARN] Prometheus query '${query}' devolvió HTTP ${status}" >&2
  fi
done

python3 "${SCRIPT_DIR}/summarize_prometheus_snapshot.py" "$OUT_DIR"
