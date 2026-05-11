

**PromQL (métricas, datasource `prometheus_local`)**
1. `sum by (service_name) (rate(http_server_duration_milliseconds_count[5m]))`
2. `sum by (service_name) (rate(http_server_duration_milliseconds_sum[5m])) / sum by (service_name) (rate(http_server_duration_milliseconds_count[5m]))`
3. `histogram_quantile(0.95, sum by (le, service_name) (rate(http_server_duration_milliseconds_bucket[5m])))`
4. `sum by (service_name) (rate(http_server_active_requests[1m]))`
5. `sum by (service_name) (rate(http_server_response_size_bytes_sum[5m])) / sum by (service_name) (rate(http_server_response_size_bytes_count[5m]))`
6. `sum by (service_name) (rate(reservations_created_total[5m]))`
7. `sum by (service_name) (rate(reservations_conflict_total[5m]))`
8. `sum by (service_name) (rate(notifications_sent_total[5m]))`
9. `sum by (service_name) (rate(notifications_failed_total[5m]))`
10. `up`

**PPL (logs, index `logs-otel-v1*`)**
1. `source=logs-otel-v1* | where resource.attributes.service.namespace="reservas" | sort -time | head 200`
2. `source=logs-otel-v1* | where severityNumber >= 13 | sort -time | head 200`
3. `source=logs-otel-v1* | where resource.attributes.service.name="api-gateway" | sort -time | head 200`
4. `source=logs-otel-v1* | where traceId="<TRACE_ID>" | fields time, resource.attributes.service.name, spanId, severityText, body | sort -time | head 200`
5. `source=logs-otel-v1* | stats count() as total by resource.attributes.service.name, severityText | sort -total`
6. `source=logs-otel-v1* | stats count() as total by span(time,1m), resource.attributes.service.name | sort span(time,1m)`

**PPL (trazas, index `otel-v1-apm-span*`)**
1. `source=otel-v1-apm-span* | sort -endTime | head 200`
2. `source=otel-v1-apm-span* | where resource.attributes.service.name="reservation-service" | sort -endTime | head 200`
3. `source=otel-v1-apm-span* | where traceId="<TRACE_ID>" | sort -endTime | head 200`
4. `source=otel-v1-apm-span* | where status.code > 0 | sort -endTime | head 200`
5. `source=otel-v1-apm-span* | stats avg(durationInNanos) as avg_ns, max(durationInNanos) as max_ns by resource.attributes.service.name | sort -avg_ns`
6. `source=otel-v1-apm-span* | stats p95(durationInNanos) as p95_ns by resource.attributes.service.name | sort -p95_ns`

