ENGINE_USER="admin"
ENGINE_PASS="ChangeMe_123!"
ENGINE_URL="https://localhost:9200"

TRACE_ID="627f7efc5cacc909694cf2fa7928bb4e"

#TRACE_ID="8ed25f83078c26b944a21bd030e6e738"

curl -k -u "$ENGINE_USER:$ENGINE_PASS" \
  "$ENGINE_URL/logs-otel-v1*/_search?pretty" \
  -H "Content-Type: application/json" \
  -d "{
    \"size\": 20,
    \"query\": {
      \"query_string\": {
        \"query\": \"$TRACE_ID\"
      }
    },
    \"sort\": [
      { \"@timestamp\": { \"order\": \"asc\" } }
    ]
  }"
