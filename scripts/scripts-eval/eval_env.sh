#!/usr/bin/env bash
# Utilidades comunes para cargar la configuración de evaluación.

EVAL_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVAL_REPO_ROOT="$(cd "${EVAL_SCRIPT_DIR}/../.." && pwd)"
EVAL_ENV_FILE="${EVAL_ENV_FILE:-${EVAL_SCRIPT_DIR}/.env}"

eval_trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

eval_load_env_defaults() {
  local env_file="$1"
  local line name value

  if [[ ! -f "$env_file" ]]; then
    echo "[WARN] No existe el fichero de entorno de evaluación: ${env_file}" >&2
    return 0
  fi

  while IFS= read -r line || [[ -n "$line" ]]; do
    line="$(eval_trim "$line")"
    [[ -z "$line" || "$line" == \#* ]] && continue
    [[ "$line" == export\ * ]] && line="$(eval_trim "${line#export }")"
    [[ "$line" != *=* ]] && continue

    name="$(eval_trim "${line%%=*}")"
    value="$(eval_trim "${line#*=}")"

    if ! [[ "$name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      echo "[WARN] Variable ignorada en ${env_file}: ${name}" >&2
      continue
    fi

    if [[ "$value" =~ ^\".*\"$ || "$value" =~ ^\'.*\'$ ]]; then
      value="${value:1:${#value}-2}"
    fi

    if [[ -z "${!name+x}" ]]; then
      export "${name}=${value}"
    fi
  done < "$env_file"
}

eval_resolve_path() {
  local path="$1"
  local base="${2:-$EVAL_SCRIPT_DIR}"

  case "$path" in
    /*) printf '%s\n' "$path" ;;
    *) printf '%s/%s\n' "$base" "$path" ;;
  esac
}

eval_load_env_defaults "$EVAL_ENV_FILE"
export EVAL_SCRIPT_DIR EVAL_REPO_ROOT EVAL_ENV_FILE
