"""
locustfile.py para la evaluación experimental del TFG.

Perfil de carga nominal:
- 20 % consulta de catálogo de salas: GET /rooms?capacity=6.
- 20 % consulta de disponibilidad: GET /availability.
- 40 % reservas correctas: POST /reservations con HTTP 200/201 esperado.
- 20 % conflictos de reserva controlados: POST /reservations con HTTP 409 esperado.

El bloque de lectura suma el 40 % previsto, pero queda separado en dos nombres
estadísticos para que los CSV de Locust permitan distinguir claramente catálogo
de salas y disponibilidad.

Uso recomendado:
    locust -f locustfile.py \
      --host http://localhost:8080 \
      --headless \
      -u 50 \
      -r 5 \
      --run-time 10m \
      --csv results/escenario_a

Variables de entorno útiles:
    TEST_DAY=2027-01-01        # opcional; si no se define, se elige aleatoriamente
    RANDOM_TEST_DAY_MIN_OFFSET=30
    RANDOM_TEST_DAY_MAX_OFFSET=365000
    SUCCESS_START_DAY_OFFSET=1
    ROOM_IDS=1,2,3,4
    USER_IDS=1
    START_HOUR=10
    END_HOUR=21
    SLOT_MINUTES=60
    ROOMS_PATH=/rooms?capacity=6
    USE_ROOMS_ENDPOINT=auto     # auto | true | false
    STRICT_CONFLICT_BODY=false  # true para exigir texto concreto en el 409
    MIN_WAIT=0.2
    MAX_WAIT=1.5
"""

from __future__ import annotations

import itertools
import os
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional
from urllib.parse import urlparse

import requests
from gevent.lock import Semaphore
from locust import HttpUser, between, events, task


# ---------------------------------------------------------------------------
# Configuración general del experimento
# ---------------------------------------------------------------------------

DEFAULT_HOST = os.getenv("BASE_URL_GATEWAY", "http://localhost:8080")

# Seguridad experimental: todas las peticiones deben entrar por el API Gateway.
# El script solo usa rutas relativas; estas comprobaciones evitan que una variable
# de entorno o un --host mal puesto apunte directamente a un microservicio.
ENFORCE_GATEWAY_ONLY = os.getenv("ENFORCE_GATEWAY_ONLY", "true").lower() == "true"
FORBIDDEN_DIRECT_SERVICE_HINTS = tuple(
    value.strip().lower()
    for value in os.getenv(
        "FORBIDDEN_DIRECT_SERVICE_HINTS",
        "reservation-service,room-service,user-service,notification-service,"
        "postgres,db,redis,opensearch,prometheus,elasticsearch,kibana,"
        "data-prepper,otel-collector,elastic-agent",
    ).split(",")
    if value.strip()
)
EXPECTED_GATEWAY_PORT = os.getenv("EXPECTED_GATEWAY_PORT", "")  # opcional; p. ej. 8080


def _resolve_test_day() -> str:
    explicit_test_day = os.getenv("TEST_DAY")
    if explicit_test_day:
        return explicit_test_day

    min_offset = int(os.getenv("RANDOM_TEST_DAY_MIN_OFFSET", "30"))
    max_offset = int(os.getenv("RANDOM_TEST_DAY_MAX_OFFSET", "365000"))

    if min_offset < 0:
        raise ValueError("RANDOM_TEST_DAY_MIN_OFFSET no puede ser negativo")
    if max_offset < min_offset:
        raise ValueError(
            "RANDOM_TEST_DAY_MAX_OFFSET debe ser mayor o igual que "
            "RANDOM_TEST_DAY_MIN_OFFSET"
        )

    random_offset = random.SystemRandom().randint(min_offset, max_offset)
    return (date.today() + timedelta(days=random_offset)).isoformat()


TEST_DAY = ""
BASE_TEST_DATE = date.today()


def _parse_int_list(env_name: str, default: str) -> list[int]:
    values = [value.strip() for value in os.getenv(env_name, default).split(",")]
    parsed = [int(value) for value in values if value]
    if not parsed:
        raise ValueError(f"{env_name} debe contener al menos un identificador numérico")
    return parsed


ROOM_IDS = _parse_int_list("ROOM_IDS", "1,2,3,4")
USER_IDS = _parse_int_list("USER_IDS", "1")

START_HOUR = int(os.getenv("START_HOUR", "10"))
END_HOUR = int(os.getenv("END_HOUR", "21"))  # no incluido; 21 permite última franja 20-21
SLOT_MINUTES = int(os.getenv("SLOT_MINUTES", "60"))

if END_HOUR <= START_HOUR:
    raise ValueError("END_HOUR debe ser mayor que START_HOUR")

HOURS = list(range(START_HOUR, END_HOUR))

ROOMS_PATH = os.getenv("ROOMS_PATH", "/rooms?capacity=6")
USE_ROOMS_ENDPOINT = os.getenv("USE_ROOMS_ENDPOINT", "auto").lower()  # auto | true | false
STRICT_CONFLICT_BODY = os.getenv("STRICT_CONFLICT_BODY", "false").lower() == "true"

MIN_WAIT = float(os.getenv("MIN_WAIT", "0.2"))
MAX_WAIT = float(os.getenv("MAX_WAIT", "1.5"))

# Se reserva el TEST_DAY para el conflicto controlado. Las reservas correctas
# empiezan por defecto al día siguiente para no pisar la reserva semilla.
SUCCESS_START_DAY_OFFSET = int(os.getenv("SUCCESS_START_DAY_OFFSET", "1"))

# Ventana aleatoria para consultas de disponibilidad de solo lectura.
AVAILABILITY_DAYS_SPAN = int(os.getenv("AVAILABILITY_DAYS_SPAN", "30"))

# Usuario y sala usados en la reserva semilla de conflicto.
CONFLICT_USER_ID = int(os.getenv("CONFLICT_USER_ID", str(USER_IDS[0])))
CONFLICT_ROOM_ID = int(os.getenv("CONFLICT_ROOM_ID", str(ROOM_IDS[0])))
CONFLICT_START = ""
CONFLICT_END = ""


# ---------------------------------------------------------------------------
# Estado compartido entre usuarios Locust
# ---------------------------------------------------------------------------

_slot_counter = itertools.count()
_conflict_lock = Semaphore()
_conflict_seeded = False
_rooms_endpoint_available: Optional[bool] = None


def configure_test_window() -> None:
    global TEST_DAY, BASE_TEST_DATE, CONFLICT_START, CONFLICT_END
    global _slot_counter, _conflict_seeded

    TEST_DAY = _resolve_test_day()
    BASE_TEST_DATE = date.fromisoformat(TEST_DAY)
    CONFLICT_START = os.getenv("CONFLICT_START", f"{TEST_DAY}T10:00:00")
    CONFLICT_END = os.getenv("CONFLICT_END", f"{TEST_DAY}T11:00:00")
    _slot_counter = itertools.count()
    _conflict_seeded = False


configure_test_window()


@dataclass(frozen=True)
class ReservationPayload:
    room_id: int
    user_id: int
    start: str
    end: str

    def as_json(self) -> dict:
        return {
            "room_id": self.room_id,
            "user_id": self.user_id,
            "start": self.start,
            "end": self.end,
        }


def _slot_to_datetimes(day_offset: int, hour: int) -> tuple[str, str]:
    start_dt = datetime.combine(
        BASE_TEST_DATE + timedelta(days=day_offset),
        datetime.min.time(),
    )
    start_dt = start_dt + timedelta(hours=hour)
    end_dt = start_dt + timedelta(minutes=SLOT_MINUTES)
    return start_dt.isoformat(timespec="seconds"), end_dt.isoformat(timespec="seconds")


def build_unique_success_payload() -> ReservationPayload:
    """
    Genera una franja previsiblemente única para reservas correctas.

    Así se evita que el 40 % de reservas exitosas termine generando 409 por
    agotamiento de slots durante una prueba de carga prolongada.
    """
    seq = next(_slot_counter)

    room_index = seq % len(ROOM_IDS)
    hour_index = (seq // len(ROOM_IDS)) % len(HOURS)
    day_index = seq // (len(ROOM_IDS) * len(HOURS))

    room_id = ROOM_IDS[room_index]
    hour = HOURS[hour_index]
    day_offset = SUCCESS_START_DAY_OFFSET + day_index

    start, end = _slot_to_datetimes(day_offset, hour)
    user_id = random.choice(USER_IDS)

    return ReservationPayload(room_id=room_id, user_id=user_id, start=start, end=end)


def build_random_availability_query() -> tuple[int, str, str]:
    room_id = random.choice(ROOM_IDS)
    hour = random.choice(HOURS)
    day_offset = random.randint(0, AVAILABILITY_DAYS_SPAN)
    start, end = _slot_to_datetimes(day_offset, hour)
    return room_id, start, end


def build_conflict_payload() -> ReservationPayload:
    return ReservationPayload(
        room_id=CONFLICT_ROOM_ID,
        user_id=CONFLICT_USER_ID,
        start=CONFLICT_START,
        end=CONFLICT_END,
    )


def _base_url(environment) -> str:
    return (environment.host or DEFAULT_HOST).rstrip("/")


def _request_ok(response: requests.Response) -> bool:
    return 200 <= response.status_code < 300


def _assert_relative_api_path(path: str, env_name: str) -> None:
    """Impide URLs absolutas que puedan saltarse el API Gateway."""
    parsed = urlparse(path)
    if parsed.scheme or parsed.netloc or not path.startswith("/"):
        raise ValueError(
            f"{env_name} debe ser una ruta relativa del API Gateway, "
            f"por ejemplo '/rooms?capacity=6'. Valor recibido: {path!r}"
        )


def _assert_gateway_target(base_url: str) -> None:
    """Comprueba que el host de Locust no apunta a un servicio interno."""
    if not ENFORCE_GATEWAY_ONLY:
        return

    parsed = urlparse(base_url)
    hostname = (parsed.hostname or "").lower()
    netloc = (parsed.netloc or "").lower()

    if not parsed.scheme or not hostname:
        raise ValueError(
            "El host de Locust debe ser una URL completa del API Gateway, "
            "por ejemplo http://localhost:8080 o http://api-gateway:8080"
        )

    if "gateway" not in hostname and hostname not in {"localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal"}:
        raise ValueError(
            "El host configurado no parece ser el API Gateway. "
            f"Host recibido: {base_url!r}. Usa --host http://localhost:8080 "
            "o --host http://api-gateway:8080 según dónde ejecutes Locust."
        )

    for hint in FORBIDDEN_DIRECT_SERVICE_HINTS:
        if hint and hint in hostname and "gateway" not in hostname:
            raise ValueError(
                "El host configurado parece apuntar directamente a un servicio interno "
                f"({hint}) en lugar del API Gateway: {base_url!r}"
            )

    if EXPECTED_GATEWAY_PORT:
        expected = int(EXPECTED_GATEWAY_PORT)
        actual = parsed.port
        if actual != expected:
            raise ValueError(
                f"El API Gateway esperado está en el puerto {expected}, "
                f"pero el host configurado usa {actual}: {base_url!r}"
            )


def validate_gateway_only_configuration(base_url: str) -> None:
    """Valida que todos los puntos configurables siguen entrando por el gateway."""
    _assert_gateway_target(base_url)
    _assert_relative_api_path(ROOMS_PATH, "ROOMS_PATH")


def preflight_and_seed(host: str) -> None:
    """
    Ejecuta una comprobación mínima equivalente al smoke test y crea o confirma
    la reserva semilla que permitirá medir conflictos HTTP 409 como errores
    funcionales esperados, no como fallos técnicos.
    """
    global _conflict_seeded, _rooms_endpoint_available

    validate_gateway_only_configuration(host)

    session = requests.Session()

    health = session.get(f"{host}/health", timeout=10)
    health.raise_for_status()

    if USE_ROOMS_ENDPOINT not in {"auto", "true", "false"}:
        raise ValueError("USE_ROOMS_ENDPOINT debe ser auto, true o false")

    if USE_ROOMS_ENDPOINT == "true":
        _rooms_endpoint_available = True
    elif USE_ROOMS_ENDPOINT == "false":
        _rooms_endpoint_available = False
    else:
        try:
            rooms = session.get(f"{host}{ROOMS_PATH}", timeout=10)
            _rooms_endpoint_available = _request_ok(rooms)
        except requests.RequestException:
            _rooms_endpoint_available = False

    with _conflict_lock:
        if _conflict_seeded:
            return

        payload = build_conflict_payload().as_json()
        response = session.post(f"{host}/reservations", json=payload, timeout=10)

        # 200/201: la semilla acaba de crearse.
        # 409: la semilla ya existía; también sirve para provocar el conflicto.
        if response.status_code not in (200, 201, 409):
            raise RuntimeError(
                "No se pudo crear o confirmar la reserva semilla de conflicto. "
                f"HTTP {response.status_code}: {response.text[:500]}"
            )

        _conflict_seeded = True


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    configure_test_window()
    host = _base_url(environment)
    preflight_and_seed(host)


validate_gateway_only_configuration(DEFAULT_HOST)


class ReservasGatewayUser(HttpUser):
    """
    Usuario sintético para el sistema de reservas a través del API Gateway.

    Distribución nominal de la carga:
        - 20 % catálogo de salas.
        - 20 % disponibilidad.
        - 40 % reservas correctas.
        - 20 % conflictos HTTP 409 esperados.
    """

    host = DEFAULT_HOST
    wait_time = between(MIN_WAIT, MAX_WAIT)

    @task(20)
    def catalogo_salas(self):
        """Consulta de catálogo de salas a través del gateway."""
        if not _rooms_endpoint_available:
            # Fallback conservador: mantiene el bloque de lectura aunque el gateway
            # no exponga /rooms en una rama concreta del experimento.
            self._consulta_disponibilidad(name="GET /availability [fallback catálogo]")
            return

        with self.client.get(
            ROOMS_PATH,
            name="GET /rooms?capacity=6",
            catch_response=True,
            timeout=10,
        ) as response:
            if response.status_code != 200:
                response.failure(f"HTTP inesperado en /rooms: {response.status_code}")
                return

            try:
                response.json()
            except ValueError:
                response.failure("Respuesta /rooms no es JSON válido")
                return

            response.success()

    @task(20)
    def consulta_disponibilidad(self):
        """Consulta de disponibilidad de una sala y franja horaria concreta."""
        self._consulta_disponibilidad(name="GET /availability")

    def _consulta_disponibilidad(self, name: str) -> None:
        room_id, start, end = build_random_availability_query()
        path = f"/availability?room_id={room_id}&start={start}&end={end}"

        with self.client.get(
            path,
            name=name,
            catch_response=True,
            timeout=10,
        ) as response:
            if response.status_code != 200:
                response.failure(f"HTTP inesperado en /availability: {response.status_code}")
                return

            try:
                body = response.json()
            except ValueError:
                response.failure("Respuesta /availability no es JSON válido")
                return

            if "available" not in body:
                response.failure("Respuesta /availability sin campo 'available'")
            else:
                response.success()

    @task(40)
    def reserva_exitosa(self):
        """
        Flujo largo de negocio.

        Genera un slot único para favorecer HTTP 200/201 y producir trazas largas:
        API Gateway -> User Service -> Reservation Service -> Room Service
        -> PostgreSQL -> Redis -> Notification Service.
        """
        payload = build_unique_success_payload().as_json()

        with self.client.post(
            "/reservations",
            json=payload,
            name="POST /reservations [200 esperado]",
            catch_response=True,
            timeout=15,
        ) as response:
            if response.status_code not in (200, 201):
                response.failure(
                    f"Reserva correcta devolvió HTTP {response.status_code}. "
                    f"Cuerpo: {response.text[:300]}"
                )
                return

            try:
                body = response.json()
            except ValueError:
                response.failure("Respuesta de reserva correcta no es JSON válido")
                return

            if body.get("status") != "CONFIRMED":
                response.failure(f"Reserva no confirmada. Cuerpo: {body}")
            else:
                response.success()

    @task(20)
    def conflicto_reserva(self):
        """
        Error funcional controlado.

        Repite siempre la reserva semilla. El resultado esperado es HTTP 409.
        Se marca como éxito en Locust para no contaminar la métrica de errores
        técnicos; el volumen de conflictos se analiza por el nombre de la petición.
        """
        payload = build_conflict_payload().as_json()

        with self.client.post(
            "/reservations",
            json=payload,
            name="POST /reservations [409 esperado]",
            catch_response=True,
            timeout=15,
        ) as response:
            if response.status_code != 409:
                response.failure(
                    f"Conflicto esperado devolvió HTTP {response.status_code}. "
                    f"Cuerpo: {response.text[:300]}"
                )
                return

            # Por defecto, el 409 es suficiente para considerar correcto el
            # conflicto funcional. Si se necesita validar el texto exacto del
            # smoke test, activar STRICT_CONFLICT_BODY=true.
            if STRICT_CONFLICT_BODY and "time slot not available" not in response.text:
                response.failure(
                    "HTTP 409 recibido, pero el cuerpo no contiene "
                    "'time slot not available'"
                )
                return

            response.success()
