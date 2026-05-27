#TRACE_ID="8ed25f83078c26b944a21bd030e6e738"
TRACE_ID="627f7efc5cacc909694cf2fa7928bb4e"
ENGINE_USER="admin"
ENGINE_PASS="ChangeMe_123!"
ENGINE_URL="https://localhost:9200"
curl -k -u "$ENGINE_USER:$ENGINE_PASS" \
  "$ENGINE_URL/otel-v1-apm-span-*/_search?pretty" \
  -H "Content-Type: application/json" \
  -d "{
    \"size\": 100,
    \"_source\": [
      \"traceId\",
      \"spanId\",
      \"parentSpanId\",
      \"serviceName\",
      \"name\",
      \"kind\",
      \"startTime\",
      \"durationInNanos\",
      \"status.code\",
      \"attributes.http.method\",
      \"attributes.http.route\",
      \"attributes.http.status_code\"
    ],
    \"query\": {
      \"term\": {
        \"traceId\": \"$TRACE_ID\"
      }
    },
    \"sort\": [
      { \"startTime\": { \"order\": \"asc\" } }
    ]
  }"
