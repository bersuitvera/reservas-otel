#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=eval_env.sh
source "${SCRIPT_DIR}/eval_env.sh"

OUT_ROOT="$(eval_resolve_path "${OUT_ROOT:-results}" "$SCRIPT_DIR")"
OUT_DIR="${1:-${OUT_ROOT}/manual_indices_$(date +%Y%m%d_%H%M%S)}"
OUT_DIR="$(eval_resolve_path "$OUT_DIR" "$SCRIPT_DIR")"
mkdir -p "$OUT_DIR"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "[ERROR] Comando requerido no disponible: $1" >&2
    exit 1
  }
}

require_cmd curl
require_cmd python3

ENGINE_URL="${ENGINE_URL:-http://localhost:9200}"
ENGINE_INSECURE="${ENGINE_INSECURE:-true}"

CURL_OPTS=(-sS)

if [[ "${ENGINE_INSECURE}" == "true" ]]; then
  CURL_OPTS+=(-k)
fi

if [[ -n "${ENGINE_USER:-}" && -n "${ENGINE_PASS:-}" ]]; then
  CURL_OPTS+=(-u "${ENGINE_USER}:${ENGINE_PASS}")
fi

request() {
  local path="$1"
  local outfile="$2"
  local statusfile="${outfile}.status"

  local status
  status="$(curl "${CURL_OPTS[@]}" -w "%{http_code}" -o "$outfile" "${ENGINE_URL%/}${path}" || true)"
  echo "$status" > "$statusfile"

  if [[ "$status" =~ ^2 ]]; then
    echo "[OK] ${path} -> ${outfile}"
  else
    echo "[WARN] ${path} devolvió HTTP ${status}. Ver ${outfile}" >&2
  fi
}

request "/" "${OUT_DIR}/engine_root.json"
request "/_cluster/health?pretty" "${OUT_DIR}/cluster_health.json"
request "/_cat/indices?format=json&bytes=mb" "${OUT_DIR}/indices.json"
request "/_cat/count?format=json" "${OUT_DIR}/count.json"
request "/_cat/data_streams?format=json" "${OUT_DIR}/data_streams.json"
request "/_cat/templates?format=json" "${OUT_DIR}/templates.json"

python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/summarize_indices.py" "$OUT_DIR"
