#!/usr/bin/env bash
# Utilidades comunes para cargar la configuración de evaluación.

EVAL_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVAL_REPO_ROOT="$(cd "${EVAL_SCRIPT_DIR}/../.." && pwd)"
EVAL_ENV_FILE="${EVAL_ENV_FILE:-${EVAL_SCRIPT_DIR}/.env}"
EVAL_GIT_BRANCH="$(git -C "${EVAL_REPO_ROOT}" branch --show-current 2>/dev/null || true)"

declare -gA EVAL_ORIGINAL_ENV=()

while IFS= read -r name; do
  EVAL_ORIGINAL_ENV["$name"]=1
done < <(compgen -e)

eval_trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

eval_load_env_defaults() {
  local env_file="$1"
  local mode="${2:-defaults}"
  local line name value

  if [[ ! -f "$env_file" ]]; then
    if [[ "$mode" != "local" ]]; then
      echo "[WARN] No existe el fichero de entorno de evaluación: ${env_file}" >&2
    fi
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
    value="$(eval_expand_env_value "$value")"

    if [[ "$mode" == "local" ]]; then
      if [[ -z "${EVAL_ORIGINAL_ENV[$name]+x}" ]]; then
        export "${name}=${value}"
      fi
    elif [[ -z "${!name+x}" ]]; then
      export "${name}=${value}"
    fi
  done < "$env_file"
}

eval_expand_env_value() {
  local value="$1"
  local prefix var default suffix replacement

  while [[ "$value" =~ (.*)\$\{([A-Za-z_][A-Za-z0-9_]*)\:-([^}]*)\}(.*) ]]; do
    prefix="${BASH_REMATCH[1]}"
    var="${BASH_REMATCH[2]}"
    default="${BASH_REMATCH[3]}"
    suffix="${BASH_REMATCH[4]}"
    replacement="${!var:-$default}"
    value="${prefix}${replacement}${suffix}"
  done

  while [[ "$value" =~ (.*)\$\{([A-Za-z_][A-Za-z0-9_]*)\}(.*) ]]; do
    prefix="${BASH_REMATCH[1]}"
    var="${BASH_REMATCH[2]}"
    suffix="${BASH_REMATCH[3]}"
    replacement="${!var:-}"
    value="${prefix}${replacement}${suffix}"
  done

  printf '%s' "$value"
}

eval_detect_scenario() {
  local branch="$1"

  case "$branch" in
    otel-collector)
      printf '%s\n' "escenario_a"
      ;;
    feat-edot-elasticsearch-dual-stack)
      printf '%s\n' "escenario_b"
      ;;
    integracion-total-elastic)
      printf '%s\n' "escenario_c"
      ;;
    *)
      printf '%s\n' "${SCENARIO:-escenario}"
      ;;
  esac
}

eval_detect_backend() {
  local scenario="$1"

  case "$scenario" in
    escenario_a) printf '%s\n' "opensearch" ;;
    escenario_b|escenario_c) printf '%s\n' "elasticsearch" ;;
    *) printf '%s\n' "unknown" ;;
  esac
}

eval_detect_observability_stack() {
  local scenario="$1"

  case "$scenario" in
    escenario_a) printf '%s\n' "otel-data-prepper" ;;
    escenario_b) printf '%s\n' "edot" ;;
    escenario_c) printf '%s\n' "elastic-apm" ;;
    *) printf '%s\n' "unknown" ;;
  esac
}

eval_resolve_path() {
  local path="$1"
  local base="${2:-$EVAL_SCRIPT_DIR}"

  case "$path" in
    /*) printf '%s\n' "$path" ;;
    *) printf '%s/%s\n' "$base" "$path" ;;
  esac
}

EVAL_DETECTED_SCENARIO="$(eval_detect_scenario "$EVAL_GIT_BRANCH")"

if [[ -z "${SCENARIO:-}" ]]; then
  export SCENARIO="$EVAL_DETECTED_SCENARIO"
fi

EVAL_SCENARIO_DEFAULTS_FILE="${EVAL_SCENARIO_DEFAULTS_FILE:-${EVAL_SCRIPT_DIR}/env/${SCENARIO}.env}"

eval_load_env_defaults "$EVAL_SCENARIO_DEFAULTS_FILE" "defaults"
eval_load_env_defaults "$EVAL_ENV_FILE" "local"

EVAL_BACKEND="$(eval_detect_backend "${SCENARIO:-}")"
EVAL_OBSERVABILITY_STACK="$(eval_detect_observability_stack "${SCENARIO:-}")"

export EVAL_SCRIPT_DIR EVAL_REPO_ROOT EVAL_ENV_FILE
export EVAL_GIT_BRANCH EVAL_DETECTED_SCENARIO EVAL_SCENARIO_DEFAULTS_FILE
export EVAL_BACKEND EVAL_OBSERVABILITY_STACK
