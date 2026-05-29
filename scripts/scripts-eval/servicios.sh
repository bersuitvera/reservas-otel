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
TRACE_ID="${1:-${TRACE_ID:-}}"

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

empty_trace_services_summary() {
  local reason="$1"
  jq -n \
    --arg trace_id "${TRACE_ID:-}" \
    --arg reason "$reason" \
    '{trace_id: $trace_id, skipped: true, reason: $reason}'
}

elastic_services_summary() {
  local trace_index_pattern="${TRACE_INDEX_PATTERN:-traces-*}"

  search_json "$trace_index_pattern" <<JSON | jq \
    --arg scenario "${SCENARIO:-}" \
    --arg trace_index_pattern "$trace_index_pattern" \
    '{
  scenario: $scenario,
  trace_index_pattern: $trace_index_pattern,
  error: .error,
  services_from_service_name: (.aggregations.services_query_compat.buckets // []),
  services_from_resource_attributes: (.aggregations.services_resource.buckets // []),
  top_span_names: (.aggregations.span_names.buckets // []),
  business_spans: (.aggregations.business_spans.span_names.buckets // [])
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

elastic_apm_services_summary() {
  local trace_index_pattern="${TRACE_INDEX_PATTERN:-traces-apm*}"

  search_json "$trace_index_pattern" <<JSON | jq \
    --arg scenario "${SCENARIO:-}" \
    --arg trace_index_pattern "$trace_index_pattern" \
    '{
  scenario: $scenario,
  trace_index_pattern: $trace_index_pattern,
  error: .error,
  services: (.aggregations.services.buckets // []),
  processors: (.aggregations.processors.buckets // []),
  top_transaction_names: (.aggregations.transaction_names.buckets // []),
  top_span_names: (.aggregations.span_names.buckets // [])
}'
{
  "size": 0,
  "aggs": {
    "services": {
      "terms": {
        "field": "service.name",
        "size": ${SIZE}
      }
    },
    "processors": {
      "terms": {
        "field": "processor.event",
        "size": ${SIZE}
      }
    },
    "transaction_names": {
      "terms": {
        "field": "transaction.name",
        "size": ${SIZE}
      }
    },
    "span_names": {
      "terms": {
        "field": "span.name",
        "size": ${SIZE}
      }
    }
  }
}
JSON
}

elastic_logs_services_summary() {
  local log_index_pattern="${LOG_INDEX_PATTERN:-logs-*}"

  search_json "$log_index_pattern" <<JSON | jq \
    --arg log_index_pattern "$log_index_pattern" \
    '{
  log_index_pattern: $log_index_pattern,
  error: .error,
  services_from_resource_attributes: (.aggregations.services_resource.buckets // []),
  severities: (.aggregations.severities.buckets // []),
  sample_messages: [
    (.hits.hits // [])[] | {
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

elastic_apm_logs_services_summary() {
  local log_index_pattern="${LOG_INDEX_PATTERN:-logs-containerlogs-*}"

  search_json "$log_index_pattern" <<JSON | jq \
    --arg log_index_pattern "$log_index_pattern" \
    '{
  log_index_pattern: $log_index_pattern,
  error: .error,
  services: (.aggregations.services.buckets // []),
  containers: (.aggregations.containers.buckets // []),
  log_levels: (.aggregations.log_levels.buckets // []),
  sample_messages: [
    (.hits.hits // [])[] | {
      timestamp: ._source["@timestamp"],
      trace_id: ._source.trace.id,
      span_id: ._source.span.id,
      service_name: ._source.service.name,
      container_name: ._source.container.name,
      log_level: ._source["log.level"],
      message: ._source.message
    }
  ]
}'
{
  "size": 10,
  "_source": [
    "@timestamp",
    "trace.id",
    "span.id",
    "service.name",
    "container.name",
    "log.level",
    "message"
  ],
  "query": {
    "match_all": {}
  },
  "sort": [
    { "@timestamp": { "order": "desc" } }
  ],
  "aggs": {
    "services": {
      "terms": {
        "field": "service.name",
        "size": ${SIZE}
      }
    },
    "containers": {
      "terms": {
        "field": "container.name",
        "size": ${SIZE}
      }
    },
    "log_levels": {
      "terms": {
        "field": "log.level",
        "size": ${SIZE}
      }
    }
  }
}
JSON
}

opensearch_services_summary() {
  local trace_index_pattern="${TRACE_INDEX_PATTERN:-otel-v1-apm-span-*}"

  search_json "$trace_index_pattern" <<JSON | jq \
    --arg scenario "${SCENARIO:-}" \
    --arg trace_index_pattern "$trace_index_pattern" \
    '{
  scenario: $scenario,
  trace_index_pattern: $trace_index_pattern,
  error: .error,
  services_from_service_name: (.aggregations.services_service_name.buckets // []),
  services_from_resource_attributes: (.aggregations.services_resource.buckets // []),
  top_span_names: (.aggregations.span_names.buckets // []),
  business_spans: (.aggregations.business_spans.span_names.buckets // [])
}'
{
  "size": 0,
  "aggs": {
    "services_service_name": {
      "terms": {
        "field": "serviceName",
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
        "bool": {
          "should": [
            { "prefix": { "name": "reservation." } },
            { "prefix": { "name": "notification." } }
          ],
          "minimum_should_match": 1
        }
      },
      "aggs": {
        "span_names": {
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

opensearch_logs_services_summary() {
  local log_index_pattern="${LOG_INDEX_PATTERN:-logs-otel-v1*}"

  search_json "$log_index_pattern" <<JSON | jq \
    --arg log_index_pattern "$log_index_pattern" \
    '{
  log_index_pattern: $log_index_pattern,
  error: .error,
  services_from_resource_attributes: (.aggregations.services_resource.buckets // []),
  severities: (.aggregations.severities.buckets // []),
  sample_messages: [
    (.hits.hits // [])[] | {
      timestamp: (._source["@timestamp"] // ._source.time),
      trace_id: ._source.traceId,
      span_id: ._source.spanId,
      service_name: ._source.resource.attributes["service.name"],
      severity_text: ._source.severityText,
      body: ._source.body
    }
  ]
}'
{
  "size": 10,
  "_source": [
    "@timestamp",
    "time",
    "traceId",
    "spanId",
    "resource.attributes.service.name",
    "severityText",
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
        "field": "severityText.keyword",
        "size": ${SIZE}
      }
    }
  }
}
JSON
}

elastic_trace_services_summary() {
  local trace_id="$1"
  local trace_index_pattern="${TRACE_INDEX_PATTERN:-traces-*}"

  [[ -n "$trace_id" ]] || {
    empty_trace_services_summary "No se encontró TRACE_ID para agregar servicios de la traza."
    return 0
  }

  search_json "$trace_index_pattern" <<JSON | jq \
    --arg trace_id "$trace_id" \
    --arg trace_index_pattern "$trace_index_pattern" \
    '{
  trace_id: $trace_id,
  trace_index_pattern: $trace_index_pattern,
  error: .error,
  total_spans: .hits.total,
  services_from_service_name: (.aggregations.services_query_compat.buckets // []),
  services_from_resource_attributes: (.aggregations.services_resource.buckets // []),
  span_names: (.aggregations.span_names.buckets // []),
  business_spans: (.aggregations.business_spans.span_names.buckets // [])
}'
{
  "size": 0,
  "query": {
    "term": {
      "trace_id": "${trace_id}"
    }
  },
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
        "bool": {
          "should": [
            { "prefix": { "name": "reservation." } },
            { "prefix": { "name": "notification." } }
          ],
          "minimum_should_match": 1
        }
      },
      "aggs": {
        "span_names": {
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

elastic_apm_trace_services_summary() {
  local trace_id="$1"
  local trace_index_pattern="${TRACE_INDEX_PATTERN:-traces-apm*}"

  [[ -n "$trace_id" ]] || {
    empty_trace_services_summary "No se encontró TRACE_ID para agregar servicios de la traza."
    return 0
  }

  search_json "$trace_index_pattern" <<JSON | jq \
    --arg trace_id "$trace_id" \
    --arg trace_index_pattern "$trace_index_pattern" \
    '{
  trace_id: $trace_id,
  trace_index_pattern: $trace_index_pattern,
  error: .error,
  total_spans: .hits.total,
  services: (.aggregations.services.buckets // []),
  transaction_names: (.aggregations.transaction_names.buckets // []),
  span_names: (.aggregations.span_names.buckets // [])
}'
{
  "size": 0,
  "query": {
    "term": {
      "trace.id": "${trace_id}"
    }
  },
  "aggs": {
    "services": {
      "terms": {
        "field": "service.name",
        "size": ${SIZE}
      }
    },
    "transaction_names": {
      "terms": {
        "field": "transaction.name",
        "size": ${SIZE}
      }
    },
    "span_names": {
      "terms": {
        "field": "span.name",
        "size": ${SIZE}
      }
    }
  }
}
JSON
}

opensearch_trace_services_summary() {
  local trace_id="$1"
  local trace_index_pattern="${TRACE_INDEX_PATTERN:-otel-v1-apm-span-*}"

  [[ -n "$trace_id" ]] || {
    empty_trace_services_summary "No se encontró TRACE_ID para agregar servicios de la traza."
    return 0
  }

  search_json "$trace_index_pattern" <<JSON | jq \
    --arg trace_id "$trace_id" \
    --arg trace_index_pattern "$trace_index_pattern" \
    '{
  trace_id: $trace_id,
  trace_index_pattern: $trace_index_pattern,
  error: .error,
  total_spans: .hits.total,
  services_from_service_name: (.aggregations.services_service_name.buckets // []),
  services_from_resource_attributes: (.aggregations.services_resource.buckets // []),
  span_names: (.aggregations.span_names.buckets // []),
  business_spans: (.aggregations.business_spans.span_names.buckets // [])
}'
{
  "size": 0,
  "query": {
    "term": {
      "traceId": "${trace_id}"
    }
  },
  "aggs": {
    "services_service_name": {
      "terms": {
        "field": "serviceName",
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
        "bool": {
          "should": [
            { "prefix": { "name": "reservation." } },
            { "prefix": { "name": "notification." } }
          ],
          "minimum_should_match": 1
        }
      },
      "aggs": {
        "span_names": {
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

opensearch_service_map() {
  local service_map_index="${SERVICE_MAP_INDEX_PATTERN:-otel-v2-apm-service-map*}"
  local sample_size="${SERVICE_MAP_SAMPLE_SIZE:-10}"

  jq -n \
    --arg scenario "${SCENARIO:-}" \
    --arg index_pattern "$service_map_index" \
    --argjson indices "$(request_json "/_cat/indices/${service_map_index}?format=json" 2>/dev/null || printf '[]')" \
    --argjson sample "$(search_json "$service_map_index" <<JSON 2>/dev/null || printf '{}'
{
  "size": ${sample_size},
  "query": {
    "match_all": {}
  }
}
JSON
)" \
    '{scenario: $scenario, service_map_index_pattern: $index_pattern, indices: $indices, sample: $sample}'
}

case "${SCENARIO:-}" in
  escenario_b)
    if [[ -z "$TRACE_ID" ]]; then
      TRACE_ID="$(latest_elastic_trace_id)"
    fi

    jq -n \
      --arg scenario "${SCENARIO:-}" \
      --arg selected_trace_id "${TRACE_ID:-}" \
      --argjson traces "$(elastic_services_summary)" \
      --argjson logs "$(elastic_logs_services_summary)" \
      --argjson trace_services "$(elastic_trace_services_summary "$TRACE_ID")" \
      '{scenario: $scenario, selected_trace_id: $selected_trace_id, traces: $traces, logs: $logs, trace_services: $trace_services}'
    ;;
  escenario_c)
    if [[ -z "$TRACE_ID" ]]; then
      TRACE_ID="$(latest_elastic_apm_trace_id)"
    fi

    jq -n \
      --arg scenario "${SCENARIO:-}" \
      --arg selected_trace_id "${TRACE_ID:-}" \
      --argjson traces "$(elastic_apm_services_summary)" \
      --argjson logs "$(elastic_apm_logs_services_summary)" \
      --argjson trace_services "$(elastic_apm_trace_services_summary "$TRACE_ID")" \
      '{scenario: $scenario, selected_trace_id: $selected_trace_id, traces: $traces, logs: $logs, trace_services: $trace_services}'
    ;;
  escenario_a)
    if [[ -z "$TRACE_ID" ]]; then
      TRACE_ID="$(latest_opensearch_trace_id)"
    fi

    jq -n \
      --arg scenario "${SCENARIO:-}" \
      --arg selected_trace_id "${TRACE_ID:-}" \
      --argjson service_map "$(opensearch_service_map)" \
      --argjson traces "$(opensearch_services_summary)" \
      --argjson logs "$(opensearch_logs_services_summary)" \
      --argjson trace_services "$(opensearch_trace_services_summary "$TRACE_ID")" \
      '{scenario: $scenario, selected_trace_id: $selected_trace_id, service_map: $service_map, traces: $traces, logs: $logs, trace_services: $trace_services}'
    ;;
  *)
    echo "[ERROR] SCENARIO=${SCENARIO:-} no reconocido" >&2
    exit 1
    ;;
esac
