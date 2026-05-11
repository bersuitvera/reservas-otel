#!/usr/bin/env bash

set -euo pipefail

BASE_URL_ROOM="${BASE_URL_ROOM:-http://localhost:8081}"
BASE_URL_USER="${BASE_URL_USER:-http://localhost:8082}"
BASE_URL_RES="${BASE_URL_RES:-http://localhost:8083}"
BASE_URL_NOTIFICATION="${BASE_URL_NOTIFICATION:-http://localhost:8084}"
BASE_URL_GATEWAY="${BASE_URL_GATEWAY:-http://localhost:8080}"
TEST_DAY="${TEST_DAY:-2026-02-01}"
ROOM_ID="${ROOM_ID:-1}"

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

find_available_slot() {
  # Busca una franja libre para que el test sea idempotente aunque ya existan
  # reservas previas en la base de datos.
  local room
  local hour
  local candidate_start
  local candidate_end
  local status

  for room in 1 2 3 4; do
    for hour in 10 11 12 13 14 15 16 17 18 19 20; do
      candidate_start="${TEST_DAY}T$(printf '%02d' "$hour"):00:00"
      candidate_end="${TEST_DAY}T$(printf '%02d' "$((hour + 1))"):00:00"
      status="$(http_status GET "$BASE_URL_GATEWAY/availability?room_id=$room&start=$candidate_start&end=$candidate_end")"
      [[ "$status" == "200" ]] || continue

      if grep -q '"available":true' /tmp/reservas_test_body.$$; then
        ROOM_ID="$room"
        START_TS="$candidate_start"
        END_TS="$candidate_end"
        pass "franja libre encontrada room_id=$ROOM_ID $START_TS -> $END_TS"
        return 0
      fi
    done
  done

  fail "no se encontró ninguna franja libre para TEST_DAY=$TEST_DAY (rooms 1-4)"
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

status="$(http_status GET "$BASE_URL_GATEWAY/health")"
assert_status "api-gateway /health" "200" "$status"
assert_body_contains "api-gateway /health" '"ok":true'

status="$(http_status GET "$BASE_URL_ROOM/rooms?capacity=6")"
assert_status "room-service /rooms" "200" "$status"
assert_body_contains "room-service /rooms" '"rooms"'

status="$(http_status GET "$BASE_URL_USER/users/1")"
assert_status "user-service /users/1" "200" "$status"
assert_body_contains "user-service /users/1" '"id":1'

find_available_slot

status="$(http_status GET "$BASE_URL_GATEWAY/availability?room_id=$ROOM_ID&start=$START_TS&end=$END_TS")"
assert_status "api-gateway /availability inicial" "200" "$status"
assert_body_contains "api-gateway /availability inicial" '"available":true'

payload="$(printf '{"room_id":%s,"user_id":1,"start":"%s","end":"%s"}' "$ROOM_ID" "$START_TS" "$END_TS")"
# Escenario feliz: reserva confirmada (200).
status="$(http_status POST "$BASE_URL_GATEWAY/reservations" "$payload")"
assert_status "api-gateway POST /reservations" "200" "$status"
assert_body_contains "api-gateway POST /reservations" '"status":"CONFIRMED"'

status="$(http_status GET "$BASE_URL_GATEWAY/availability?room_id=$ROOM_ID&start=$START_TS&end=$END_TS")"
assert_status "api-gateway /availability tras reservar" "200" "$status"
assert_body_contains "api-gateway /availability tras reservar" '"available":false'

# Escenario de error funcional: duplicado sobre la misma franja (409).
status="$(http_status POST "$BASE_URL_GATEWAY/reservations" "$payload")"
assert_status "api-gateway conflicto duplicado" "409" "$status"
assert_body_contains "api-gateway conflicto duplicado" 'time slot not available'

printf '\nSmoke tests completados correctamente.\n'
