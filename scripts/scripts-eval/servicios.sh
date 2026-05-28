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
SIZE="${SIZE:-20}"

CURL_OPTS=(-sS)

if [[ "$ENGINE_INSECURE" == "true" ]]; then
  CURL_OPTS+=(-k)
fi

if [[ -n "${ENGINE_USER:-}" && -n "${ENGINE_PASS:-}" ]]; then
  CURL_OPTS+=(-u "${ENGINE_USER}:${ENGINE_PASS}")
fi

request_json() {
  local path="$1"
  curl "${CURL_OPTS[@]}" "${ENGINE_URL%/}${path}"
}

search_json() {
  local index_pattern="$1"
  curl "${CURL_OPTS[@]}" \
    "${ENGINE_URL%/}/${index_pattern}/_search" \
    -H "Content-Type: application/json" \
    -d @-
}

elastic_services_summary() {
  search_json "${TRACE_INDEX_PATTERN:-traces-*}" <<JSON | jq --arg scenario "${SCENARIO:-}" '{
  scenario: $scenario,
  trace_index_pattern: "'"${TRACE_INDEX_PATTERN:-traces-*}"'",
  services_from_service_name: .aggregations.services_query_compat.buckets,
  services_from_resource_attributes: .aggregations.services_resource.buckets,
  top_span_names: .aggregations.span_names.buckets,
  business_spans: .aggregations.business_spans.buckets
}'
{
  "size": 0,
  "aggs": {
    "services_query_compat": {
      "terms": {
        "field": "service.name",
        "size": ${SIZE}
      }
    },
    "services_resource": {
      "terms": {
        "field": "resource.attributes.service.name",
        "size": ${SIZE}
      }
    },
    "span_names": {
      "terms": {
        "field": "name",
        "size": ${SIZE}
      }
    },
    "business_spans": {
      "filter": {
        "prefix": {
          "name": "reservation."
        }
      },
      "aggs": {
        "buckets": {
          "terms": {
            "field": "name",
            "size": ${SIZE}
          }
        }
      }
    }
  }
}
JSON
}

elastic_logs_services_summary() {
  search_json "${LOG_INDEX_PATTERN:-logs-*}" <<JSON | jq '{
  log_index_pattern: "'"${LOG_INDEX_PATTERN:-logs-*}"'",
  services_from_resource_attributes: .aggregations.services_resource.buckets,
  severities: .aggregations.severities.buckets,
  sample_messages: [
    .hits.hits[] | {
      timestamp: ._source["@timestamp"],
      trace_id: ._source.trace_id,
      span_id: ._source.span_id,
      service_name: (._source.resource.attributes["service.name"] // ._source.service.name),
      severity_text: ._source.severity_text,
      body: (._source.body.text // ._source.body)
    }
  ]
}'
{
  "size": 10,
  "_source": [
    "@timestamp",
    "trace_id",
    "span_id",
    "resource.attributes.service.name",
    "service.name",
    "severity_text",
    "body"
  ],
  "query": {
    "match_all": {}
  },
  "sort": [
    { "@timestamp": { "order": "desc" } }
  ],
  "aggs": {
    "services_resource": {
      "terms": {
        "field": "resource.attributes.service.name",
        "size": ${SIZE}
      }
    },
    "severities": {
      "terms": {
        "field": "severity_text",
        "size": ${SIZE}
      }
    }
  }
}
JSON
}

opensearch_service_map() {
  local service_map_index="${SERVICE_MAP_INDEX_PATTERN:-otel-v2-apm-service-map*}"

  jq -n \
    --arg scenario "${SCENARIO:-}" \
    --arg index_pattern "$service_map_index" \
    --argjson indices "$(request_json "/_cat/indices/${service_map_index}?format=json" 2>/dev/null || printf '[]')" \
    --argjson sample "$(search_json "$service_map_index" <<'JSON' 2>/dev/null || printf '{}'
{
  "size": 100,
  "query": {
    "match_all": {}
  }
}
JSON
)" \
    '{scenario: $scenario, service_map_index_pattern: $index_pattern, indices: $indices, sample: $sample}'
}

case "${SCENARIO:-}" in
  escenario_b|escenario_c)
    jq -n \
      --argjson traces "$(elastic_services_summary)" \
      --argjson logs "$(elastic_logs_services_summary)" \
      '{traces: $traces, logs: $logs}'
    ;;
  escenario_a)
    opensearch_service_map
    ;;
  *)
    echo "[ERROR] SCENARIO=${SCENARIO:-} no reconocido" >&2
    exit 1
    ;;
esac
