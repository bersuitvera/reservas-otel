#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=eval_env.sh
source "${SCRIPT_DIR}/eval_env.sh"

OUT_ROOT="$(eval_resolve_path "${OUT_ROOT:-results}" "$SCRIPT_DIR")"
OUT_FILE="${1:-${OUT_ROOT}/docker_stats_raw.jsonl}"
OUT_FILE="$(eval_resolve_path "$OUT_FILE" "$SCRIPT_DIR")"
INTERVAL="${2:-5}"

mkdir -p "$(dirname "$OUT_FILE")"
: > "$OUT_FILE"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "[ERROR] Comando requerido no disponible: $1" >&2
    exit 1
  }
}

require_cmd docker

echo "[INFO] monitor_docker_stats: salida=${OUT_FILE}, intervalo=${INTERVAL}s" >&2

while true; do
  TS="$(date -Iseconds)"
  FILTERED_CONTAINERS=()

  if [[ -n "${CONTAINERS:-}" ]]; then
    read -r -a CONTAINER_LIST <<< "${CONTAINERS}"
  else
    mapfile -t CONTAINER_LIST < <(docker ps --format '{{.Names}}')
  fi

  for NAME in "${CONTAINER_LIST[@]}"; do
    [[ -z "$NAME" ]] && continue

    if [[ -n "${CONTAINER_REGEX:-}" ]]; then
      if ! [[ "$NAME" =~ ${CONTAINER_REGEX} ]]; then
        continue
      fi
    fi

    FILTERED_CONTAINERS+=("$NAME")
  done

  if [[ ${#FILTERED_CONTAINERS[@]} -gt 0 ]]; then
    # One docker stats call per cycle keeps SAMPLE_INTERVAL meaningful even with
    # many containers in the scenario.
    docker stats --no-stream --format '{{json .}}' "${FILTERED_CONTAINERS[@]}" 2>/dev/null \
      | while IFS= read -r LINE; do
          [[ -z "$LINE" ]] && continue
          printf '{"ts":"%s","stats":%s}\n' "$TS" "$LINE" >> "$OUT_FILE"
        done || true
  fi

  sleep "$INTERVAL"
done
