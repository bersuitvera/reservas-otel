#!/usr/bin/env bash

set -euo pipefail

BASE_URL_ROOM="${BASE_URL_ROOM:-http://localhost:8081}"
BASE_URL_USER="${BASE_URL_USER:-http://localhost:8082}"
BASE_URL_RES="${BASE_URL_RES:-http://localhost:8083}"
BASE_URL_NOTIFICATION="${BASE_URL_NOTIFICATION:-http://localhost:8084}"
TEST_DAY="${TEST_DAY:-2026-03-24}"

START_TS="${TEST_DAY}T10:00:00"
END_TS="${TEST_DAY}T11:00:00"

pass() {
  printf '[PASS] %s\n' "$1"
}

fail() {
  printf '[FAIL] %s\n' "$1" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Comando requerido no disponible: $1"
}

http_status() {
  local method="$1"
  local url="$2"
  local data="${3:-}"

  if [[ -n "$data" ]]; then
    curl -sS -o /tmp/reservas_test_body.$$ -w '%{http_code}' \
      -X "$method" \
      -H 'Content-Type: application/json' \
      -d "$data" \
      "$url"
  else
    curl -sS -o /tmp/reservas_test_body.$$ -w '%{http_code}' \
      -X "$method" \
      "$url"
  fi
}

assert_status() {
  local name="$1"
  local expected="$2"
  local actual="$3"
  [[ "$actual" == "$expected" ]] || {
    printf 'Respuesta recibida:\n' >&2
    cat /tmp/reservas_test_body.$$ >&2
    fail "$name devolvió HTTP $actual, esperado $expected"
  }
  pass "$name devolvió HTTP $expected"
}

assert_body_contains() {
  local name="$1"
  local pattern="$2"
  if ! grep -q "$pattern" /tmp/reservas_test_body.$$; then
    printf 'Respuesta recibida:\n' >&2
    cat /tmp/reservas_test_body.$$ >&2
    fail "$name no contiene el patrón esperado: $pattern"
  fi
  pass "$name contiene $pattern"
}

cleanup() {
  rm -f /tmp/reservas_test_body.$$
}

trap cleanup EXIT

require_cmd curl
require_cmd grep

status="$(http_status GET "$BASE_URL_ROOM/health")"
assert_status "room-service /health" "200" "$status"
assert_body_contains "room-service /health" '"ok":true'

status="$(http_status GET "$BASE_URL_USER/health")"
assert_status "user-service /health" "200" "$status"
assert_body_contains "user-service /health" '"ok":true'

status="$(http_status GET "$BASE_URL_RES/health")"
assert_status "reservation-service /health" "200" "$status"
assert_body_contains "reservation-service /health" '"ok":true'

status="$(http_status GET "$BASE_URL_NOTIFICATION/health")"
assert_status "notification-service /health" "200" "$status"
assert_body_contains "notification-service /health" '"ok":true'

status="$(http_status GET "$BASE_URL_ROOM/rooms?capacity=6")"
assert_status "room-service /rooms" "200" "$status"
assert_body_contains "room-service /rooms" '"rooms"'

status="$(http_status GET "$BASE_URL_USER/users/1")"
assert_status "user-service /users/1" "200" "$status"
assert_body_contains "user-service /users/1" '"id":1'

status="$(http_status GET "$BASE_URL_RES/availability?room_id=1&start=$START_TS&end=$END_TS")"
assert_status "reservation-service /availability" "200" "$status"
assert_body_contains "reservation-service /availability" '"available":true'

payload="$(printf '{"room_id":1,"user_id":1,"start":"%s","end":"%s"}' "$START_TS" "$END_TS")"
status="$(http_status POST "$BASE_URL_RES/reservations" "$payload")"
assert_status "reservation-service POST /reservations" "200" "$status"
assert_body_contains "reservation-service POST /reservations" '"status":"CONFIRMED"'

status="$(http_status GET "$BASE_URL_RES/availability?room_id=1&start=$START_TS&end=$END_TS")"
assert_status "reservation-service /availability tras reservar" "200" "$status"
assert_body_contains "reservation-service /availability tras reservar" '"available":false'

status="$(http_status POST "$BASE_URL_RES/reservations" "$payload")"
assert_status "reservation-service conflicto duplicado" "409" "$status"
assert_body_contains "reservation-service conflicto duplicado" 'time slot not available'

printf '\nSmoke tests completados correctamente.\n'
