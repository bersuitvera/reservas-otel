import os, time, json
from datetime import datetime
from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from redis import Redis
from common.otel import setup_telemetry
from common.logger import log
from opentelemetry import metrics, trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.propagate import inject
from opentelemetry.trace import SpanKind

SERVICE = os.getenv("SERVICE_NAME", "reservation-service")
setup_telemetry(SERVICE)
tracer = trace.get_tracer(SERVICE)
meter = metrics.get_meter(SERVICE)

DATABASE_URL = os.getenv("DATABASE_URL")
engine: Engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SQLAlchemyInstrumentor().instrument(engine=engine)

redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
RedisInstrumentor().instrument()

NOTIF_FAIL_RATE = float(os.getenv("NOTIFICATION_FAIL_RATE", "0.10"))
DB_LAT_MS = int(os.getenv("ARTIFICIAL_DB_LATENCY_MS", "0"))
reservation_created_counter = meter.create_counter("reservations.created")
reservation_conflict_counter = meter.create_counter("reservations.conflict")
availability_check_counter = meter.create_counter("reservations.availability.check")
reservation_duration_histogram = meter.create_histogram("reservations.duration.seconds")

app = FastAPI(title="Reservation Service")
FastAPIInstrumentor.instrument_app(app)

def parse_ts(s: str) -> datetime:
    # ISO 8601 expected: "2026-03-05T10:00:00"
    return datetime.fromisoformat(s)

@app.on_event("startup")
def startup():
    with engine.begin() as conn:
        conn.execute(text("""
          CREATE TABLE IF NOT EXISTS reservations (
            id SERIAL PRIMARY KEY,
            room_id INT NOT NULL,
            user_id INT NOT NULL,
            start_ts TIMESTAMP NOT NULL,
            end_ts TIMESTAMP NOT NULL,
            status TEXT NOT NULL DEFAULT 'CONFIRMED'
          )
        """))

@app.get("/availability")
def availability(room_id: int, start: str, end: str):
    s, e = parse_ts(start), parse_ts(end)
    availability_check_counter.add(1, {"room_id": room_id})
    if DB_LAT_MS:
        time.sleep(DB_LAT_MS / 1000)
    with engine.begin() as conn:
        overlap = conn.execute(text("""
          SELECT COUNT(*) FROM reservations
          WHERE room_id = :room_id
            AND status = 'CONFIRMED'
            AND (start_ts < :end_ts) AND (end_ts > :start_ts)
        """), {"room_id": room_id, "start_ts": s, "end_ts": e}).scalar_one()

    return {"room_id": room_id, "available": overlap == 0, "overlaps": overlap}

@app.post("/reservations")
def create(payload: dict):
    room_id = int(payload["room_id"])
    user_id = int(payload["user_id"])
    s, e = parse_ts(payload["start"]), parse_ts(payload["end"])
    if e <= s:
        raise HTTPException(400, "end must be after start")

    duration_seconds = (e - s).total_seconds()
    with tracer.start_as_current_span("reservation.create", kind=SpanKind.INTERNAL) as span:
        span.set_attribute("app_room_id", room_id)
        span.set_attribute("app_user_id", user_id)
        span.set_attribute("app_duration_seconds", duration_seconds)

        if DB_LAT_MS:
            time.sleep(DB_LAT_MS / 1000)

        with engine.begin() as conn:
            overlap = conn.execute(text("""
              SELECT COUNT(*) FROM reservations
              WHERE room_id = :room_id
                AND status = 'CONFIRMED'
                AND (start_ts < :end_ts) AND (end_ts > :start_ts)
            """), {"room_id": room_id, "start_ts": s, "end_ts": e}).scalar_one()

            if overlap > 0:
                reservation_conflict_counter.add(1, {"room_id": room_id})
                span.add_event("reservation.conflict", {"app_room_id": room_id})
                log("warn", "reservation conflict", room_id=room_id, user_id=user_id)
                raise HTTPException(409, "time slot not available")

            rid = conn.execute(text("""
              INSERT INTO reservations(room_id, user_id, start_ts, end_ts)
              VALUES (:room_id, :user_id, :start_ts, :end_ts)
              RETURNING id
            """), {"room_id": room_id, "user_id": user_id, "start_ts": s, "end_ts": e}).scalar_one()

        reservation_created_counter.add(1, {"room_id": room_id})
        reservation_duration_histogram.record(duration_seconds, {"room_id": room_id})

        propagation_headers: dict[str, str] = {}
        inject(propagation_headers)
        event = {
            "type": "reservation.created",
            "reservation_id": rid,
            "room_id": room_id,
            "user_id": user_id,
            "trace": propagation_headers,
        }

        with tracer.start_as_current_span("reservation.publish_notification", kind=SpanKind.PRODUCER) as publish_span:
            publish_span.set_attribute("app_messaging_system", "redis")
            publish_span.set_attribute("app_messaging_destination", "events")
            publish_span.set_attribute("app_messaging_operation", "publish")
            publish_span.set_attribute("app_reservation_id", rid)
            redis.xadd("events", {"event": json.dumps(event)})

    return {"id": rid, "status": "CONFIRMED"}

@app.get("/reservations/{reservation_id}")
def get_res(reservation_id: int):
    with engine.begin() as conn:
        row = conn.execute(text("""
          SELECT id, room_id, user_id, start_ts, end_ts, status
          FROM reservations WHERE id = :id
        """), {"id": reservation_id}).mappings().first()
    if not row:
        raise HTTPException(404, "not found")
    return dict(row)

@app.get("/health")
def health():
    return {"ok": True}
