#!/usr/bin/env bash
set -euo pipefail

ENGINE_USER="${ENGINE_USER:-admin}"
ENGINE_PASS="${ENGINE_PASS:-ChangeMe_123!}"
ENGINE_URL="${ENGINE_URL:-https://localhost:9200}"

echo "[INFO] Índices de service map:"
curl -k -u "$ENGINE_USER:$ENGINE_PASS" \
  "$ENGINE_URL/_cat/indices/otel-v2-apm-service-map*?v"

echo
echo "[INFO] Muestra de documentos de service map:"
curl -k -u "$ENGINE_USER:$ENGINE_PASS" \
  "$ENGINE_URL/otel-v2-apm-service-map*/_search?pretty" \
  -H "Content-Type: application/json" \
  -d '{
    "size": 100,
    "query": {
      "match_all": {}
    }
  }'
