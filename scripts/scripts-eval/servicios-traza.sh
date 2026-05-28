TRACE_ID="627f7efc5cacc909694cf2fa7928bb4e"
ENGINE_USER="admin"
ENGINE_PASS="ChangeMe_123!"
ENGINE_URL="https://localhost:9200"


curl -k -u "$ENGINE_USER:$ENGINE_PASS" \
  "$ENGINE_URL/otel-v1-apm-span-*/_search?pretty" \
  -H "Content-Type: application/json" \
  -d "{
    \"size\": 0,
    \"query\": {
      \"term\": {
        \"traceId\": \"$TRACE_ID\"
      }
    },
    \"aggs\": {
      \"servicios_implicados\": {
        \"terms\": {
          \"field\": \"serviceName.keyword\",
          \"size\": 20
        }
      }
    }
  }"
