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
SIZE="${SIZE:-100}"
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
  search_json "${TRACE_INDEX_PATTERN:-traces-*}" <<'JSON' | jq -r '.hits.hits[0]._source.trace_id // empty'
{
  "size": 1,
  "_source": ["trace_id"],
  "query": {
    "bool": {
      "must": [
        { "exists": { "field": "trace_id" } },
        { "exists": { "field": "parent_span_id" } }
      ]
    }
  },
  "sort": [
    { "@timestamp": { "order": "desc" } }
  ]
}
JSON
}

latest_elastic_apm_trace_id() {
  search_json "${TRACE_INDEX_PATTERN:-traces-apm*}" <<'JSON' | jq -r '.hits.hits[0]._source.trace.id // empty'
{
  "size": 1,
  "_source": ["trace.id"],
  "query": {
    "bool": {
      "must": [
        { "exists": { "field": "trace.id" } },
        { "exists": { "field": "parent.id" } }
      ]
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

query_elastic_trace() {
  local trace_id="$1"
  search_json "${TRACE_INDEX_PATTERN:-traces-*}" <<JSON | jq '. as $root | {
  total: $root.hits.total,
  spans: [
    $root.hits.hits[] | {
      index: ._index,
      timestamp: ._source["@timestamp"],
      trace_id: ._source.trace_id,
      span_id: ._source.span_id,
      parent_span_id: ._source.parent_span_id,
      service_name: ._source.resource.attributes["service.name"],
      name: ._source.name,
      kind: ._source.kind,
      duration_ns: ._source.duration,
      status_code: ._source.status.code,
      processor_event: ._source.attributes["processor.event"],
      http_method: (._source.attributes["http.request.method"] // ._source.attributes["http.method"]),
      http_route: (._source.attributes["http.route"] // ._source.attributes["url.path"]),
      http_status_code: (._source.attributes["http.response.status_code"] // ._source.attributes["http.status_code"]),
      app_user_id: ._source.attributes["app.user_id"],
      app_room_id: ._source.attributes["app.room_id"],
      app_reservation_id: ._source.attributes["app.reservation_id"],
      app_reservation_status: ._source.attributes["app.reservation.status"],
      app_event_type: ._source.attributes["app.event.type"]
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
    { "attributes.timestamp.us": { "order": "asc", "unmapped_type": "long" } },
    { "@timestamp": { "order": "asc" } }
  ]
}
JSON
}

query_elastic_apm_trace() {
  local trace_id="$1"
  search_json "${TRACE_INDEX_PATTERN:-traces-apm*}" <<JSON | jq '. as $root | {
  total: $root.hits.total,
  spans: [
    $root.hits.hits[] | {
      index: ._index,
      timestamp: ._source["@timestamp"],
      trace_id: ._source.trace.id,
      span_id: (._source.span.id // ._source.transaction.id),
      parent_span_id: ._source.parent.id,
      service_name: ._source.service.name,
      name: (._source.span.name // ._source.transaction.name),
      kind: (._source.span.type // ._source.transaction.type),
      subtype: ._source.span.subtype,
      action: ._source.span.action,
      duration_us: (._source.span.duration.us // ._source.transaction.duration.us),
      outcome: ._source.event.outcome,
      processor_event: ._source.processor.event,
      http_method: ._source.http.request.method,
      http_route: (._source.transaction.name // ._source.url.path),
      http_status_code: ._source.http.response.status_code,
      app_user_id: (._source.labels.app_user_id // ._source.numeric_labels.app_user_id),
      app_room_id: (._source.labels.app_room_id // ._source.numeric_labels.app_room_id),
      app_reservation_id: (._source.labels.app_reservation_id // ._source.numeric_labels.app_reservation_id),
      app_reservation_status: ._source.labels.app_reservation_status,
      app_event_type: ._source.labels.app_event_type,
      app_received_traceparent: ._source.labels.app_received_traceparent
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
    { "@timestamp": { "order": "asc" } },
    { "timestamp.us": { "order": "asc", "unmapped_type": "long" } }
  ]
}
JSON
}

query_opensearch_trace() {
  local trace_id="$1"
  search_json "${TRACE_INDEX_PATTERN:-otel-v1-apm-span-*}" <<JSON | jq '. as $root | {
  total: $root.hits.total,
  spans: [
    $root.hits.hits[] | {
      index: ._index,
      timestamp: ._source.startTime,
      trace_id: ._source.traceId,
      span_id: ._source.spanId,
      parent_span_id: ._source.parentSpanId,
      service_name: (._source.serviceName // ._source.resource.attributes["service.name"]),
      name: ._source.name,
      kind: ._source.kind,
      duration_ns: ._source.durationInNanos,
      status_code: ._source.status.code,
      http_method: ._source.attributes["http.method"],
      http_route: ._source.attributes["http.route"],
      http_status_code: ._source.attributes["http.status_code"],
      app_user_id: ._source.attributes.app_user_id,
      app_room_id: ._source.attributes.app_room_id,
      app_reservation_id: ._source.attributes.app_reservation_id,
      app_reservation_status: ._source.attributes["app.reservation.status"],
      app_event_type: ._source.attributes.app_event_type,
      app_received_traceparent: ._source.attributes.app_received_traceparent,
      app_propagated_traceparent: ._source.attributes.app_propagated_traceparent
    }
  ]
}'
{
  "size": ${SIZE},
  "_source": [
    "traceId",
    "spanId",
    "parentSpanId",
    "serviceName",
    "resource.attributes.service.name",
    "name",
    "kind",
    "startTime",
    "durationInNanos",
    "status.code",
    "attributes.http.method",
    "attributes.http.route",
    "attributes.http.status_code",
    "attributes.app_user_id",
    "attributes.app_room_id",
    "attributes.app_reservation_id",
    "attributes.app.reservation.status",
    "attributes.app_event_type",
    "attributes.app_received_traceparent",
    "attributes.app_propagated_traceparent"
  ],
  "query": {
    "term": {
      "traceId": "${trace_id}"
    }
  },
  "sort": [
    { "startTime": { "order": "asc" } }
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
      echo "[ERROR] No se encontró TRACE_ID en ${TRACE_INDEX_PATTERN:-traces-*}" >&2
      exit 1
    fi

    echo "[INFO] Escenario=${SCENARIO}; índice=${TRACE_INDEX_PATTERN:-traces-*}; trace_id=${TRACE_ID}" >&2
    query_elastic_trace "$TRACE_ID"
    ;;
  escenario_c)
    if [[ -z "$TRACE_ID" ]]; then
      TRACE_ID="$(latest_elastic_apm_trace_id)"
    fi

    if [[ -z "$TRACE_ID" ]]; then
      echo "[ERROR] No se encontró TRACE_ID en ${TRACE_INDEX_PATTERN:-traces-apm*}" >&2
      exit 1
    fi

    echo "[INFO] Escenario=${SCENARIO}; índice=${TRACE_INDEX_PATTERN:-traces-apm*}; trace.id=${TRACE_ID}" >&2
    query_elastic_apm_trace "$TRACE_ID"
    ;;
  escenario_a)
    if [[ -z "$TRACE_ID" ]]; then
      TRACE_ID="$(latest_opensearch_trace_id)"
    fi

    if [[ -z "$TRACE_ID" ]]; then
      echo "[ERROR] No se encontró TRACE_ID en ${TRACE_INDEX_PATTERN:-otel-v1-apm-span-*}" >&2
      exit 1
    fi

    echo "[INFO] Escenario=${SCENARIO}; índice=${TRACE_INDEX_PATTERN:-otel-v1-apm-span-*}; traceId=${TRACE_ID}" >&2
    query_opensearch_trace "$TRACE_ID"
    ;;
  *)
    echo "[ERROR] SCENARIO=${SCENARIO:-} no reconocido" >&2
    exit 1
    ;;
esac
