#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=eval_env.sh
source "${SCRIPT_DIR}/eval_env.sh"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "[ERROR] Comando requerido no disponible: $1" >&2
    exit 1
  }
}

require_cmd curl
require_cmd jq

ENGINE_URL="${ENGINE_URL:-http://localhost:9200}"
ENGINE_INSECURE="${ENGINE_INSECURE:-false}"
SIZE="${SIZE:-50}"
TRACE_ID="${1:-${TRACE_ID:-}}"

CURL_OPTS=(-sS)

if [[ "$ENGINE_INSECURE" == "true" ]]; then
  CURL_OPTS+=(-k)
fi

if [[ -n "${ENGINE_USER:-}" && -n "${ENGINE_PASS:-}" ]]; then
  CURL_OPTS+=(-u "${ENGINE_USER}:${ENGINE_PASS}")
fi

search_json() {
  local index_pattern="$1"
  curl "${CURL_OPTS[@]}" \
    "${ENGINE_URL%/}/${index_pattern}/_search" \
    -H "Content-Type: application/json" \
    -d @-
}

latest_elastic_trace_id() {
  search_json "${LOG_INDEX_PATTERN:-logs-*}" <<'JSON' | jq -r '.hits.hits[0]._source.trace_id // empty'
{
  "size": 1,
  "_source": ["trace_id"],
  "query": {
    "exists": {
      "field": "trace_id"
    }
  },
  "sort": [
    { "@timestamp": { "order": "desc" } }
  ]
}
JSON
}

latest_elastic_apm_trace_id() {
  search_json "${LOG_INDEX_PATTERN:-logs-containerlogs-*}" <<'JSON' | jq -r '.hits.hits[0]._source.trace.id // empty'
{
  "size": 1,
  "_source": ["trace.id"],
  "query": {
    "exists": {
      "field": "trace.id"
    }
  },
  "sort": [
    { "@timestamp": { "order": "desc" } }
  ]
}
JSON
}

latest_opensearch_trace_id() {
  search_json "${LOG_INDEX_PATTERN:-logs-otel-v1*}" <<'JSON' | jq -r '.hits.hits[0]._source.traceId // empty'
{
  "size": 1,
  "_source": ["traceId"],
  "query": {
    "exists": {
      "field": "traceId"
    }
  },
  "sort": [
    { "@timestamp": { "order": "desc" } }
  ]
}
JSON
}

query_elastic_logs() {
  local trace_id="$1"
  search_json "${LOG_INDEX_PATTERN:-logs-*}" <<JSON | jq '. as $root | {
  total: $root.hits.total,
  logs: [
    $root.hits.hits[] | {
      index: ._index,
      timestamp: ._source["@timestamp"],
      observed_timestamp: ._source.observed_timestamp,
      trace_id: ._source.trace_id,
      span_id: ._source.span_id,
      service_name: (._source.resource.attributes["service.name"] // ._source.service.name),
      scope_name: ._source.scope.name,
      severity_text: ._source.severity_text,
      severity_number: ._source.severity_number,
      body: (._source.body.text // ._source.body),
      event: ._source.attributes.event,
      code_file: ._source.attributes["code.file.path"],
      code_function: ._source.attributes["code.function.name"],
      code_line: ._source.attributes["code.line.number"]
    }
  ]
}'
{
  "size": ${SIZE},
  "query": {
    "term": {
      "trace_id": "${trace_id}"
    }
  },
  "sort": [
    { "@timestamp": { "order": "asc" } }
  ]
}
JSON
}

query_elastic_apm_logs() {
  local trace_id="$1"
  search_json "${LOG_INDEX_PATTERN:-logs-containerlogs-*}" <<JSON | jq '. as $root | {
  total: $root.hits.total,
  logs: [
    $root.hits.hits[] | {
      index: ._index,
      timestamp: ._source["@timestamp"],
      trace_id: ._source.trace.id,
      span_id: ._source.span.id,
      service_name: ._source.service.name,
      container_name: ._source.container.name,
      log_level: ._source["log.level"],
      message: ._source.message,
      event_dataset: ._source.event.dataset,
      event_original: ._source.event.original,
      code_file: (._source.log.origin.file.name // ._source["log.origin"].file.name),
      code_function: (._source.log.origin.function // ._source["log.origin"].function),
      code_line: (._source.log.origin.file.line // ._source["log.origin"].file.line)
    }
  ]
}'
{
  "size": ${SIZE},
  "query": {
    "term": {
      "trace.id": "${trace_id}"
    }
  },
  "sort": [
    { "@timestamp": { "order": "asc" } }
  ]
}
JSON
}

query_opensearch_logs() {
  local trace_id="$1"
  search_json "${LOG_INDEX_PATTERN:-logs-otel-v1*}" <<JSON
{
  "size": ${SIZE},
  "query": {
    "query_string": {
      "query": "${trace_id}"
    }
  },
  "sort": [
    { "@timestamp": { "order": "asc" } }
  ]
}
JSON
}

case "${SCENARIO:-}" in
  escenario_b)
    if [[ -z "$TRACE_ID" ]]; then
      TRACE_ID="$(latest_elastic_trace_id)"
    fi

    if [[ -z "$TRACE_ID" ]]; then
      echo "[ERROR] No se encontró TRACE_ID en ${LOG_INDEX_PATTERN:-logs-*}" >&2
      exit 1
    fi

    echo "[INFO] Escenario=${SCENARIO}; índice=${LOG_INDEX_PATTERN:-logs-*}; trace_id=${TRACE_ID}" >&2
    query_elastic_logs "$TRACE_ID"
    ;;
  escenario_c)
    if [[ -z "$TRACE_ID" ]]; then
      TRACE_ID="$(latest_elastic_apm_trace_id)"
    fi

    if [[ -z "$TRACE_ID" ]]; then
      echo "[ERROR] No se encontró TRACE_ID en ${LOG_INDEX_PATTERN:-logs-containerlogs-*}" >&2
      exit 1
    fi

    echo "[INFO] Escenario=${SCENARIO}; índice=${LOG_INDEX_PATTERN:-logs-containerlogs-*}; trace.id=${TRACE_ID}" >&2
    query_elastic_apm_logs "$TRACE_ID"
    ;;
  escenario_a)
    if [[ -z "$TRACE_ID" ]]; then
      TRACE_ID="$(latest_opensearch_trace_id)"
    fi

    if [[ -z "$TRACE_ID" ]]; then
      echo "[ERROR] No se encontró TRACE_ID en ${LOG_INDEX_PATTERN:-logs-otel-v1*}" >&2
      exit 1
    fi

    echo "[INFO] Escenario=${SCENARIO}; índice=${LOG_INDEX_PATTERN:-logs-otel-v1*}; traceId=${TRACE_ID}" >&2
    query_opensearch_logs "$TRACE_ID"
    ;;
  *)
    echo "[ERROR] SCENARIO=${SCENARIO:-} no reconocido" >&2
    exit 1
    ;;
esac
