import json
import os
import time
from datetime import datetime

import elasticapm
import httpx
from fastapi import FastAPI, HTTPException
from redis import Redis
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from common.apm import setup_apm
from common.logger import log

SERVICE = os.getenv("SERVICE_NAME", "reservation-service")

DATABASE_URL = os.getenv("DATABASE_URL")
ROOM_SERVICE_URL = os.getenv("ROOM_SERVICE_URL", "http://room-service:8000")
engine: Engine = create_engine(DATABASE_URL, pool_pre_ping=True)
http_client = httpx.Client(timeout=3.0)

redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))

DB_LAT_MS = int(os.getenv("ARTIFICIAL_DB_LATENCY_MS", "0"))

app = FastAPI(title="Reservation Service")
setup_apm(SERVICE, app)


def parse_ts(s: str) -> datetime:
    # ISO 8601 expected: "2026-03-05T10:00:00"
    return datetime.fromisoformat(s)


def ensure_room_exists(room_id: int) -> None:
    with elasticapm.capture_span(
        "reservation.validate.room",
        span_type="app.validation",
        labels={"app_room_id": room_id},
    ):
        url = f"{ROOM_SERVICE_URL}/rooms/{room_id}"
        try:
            resp = http_client.get(url)
        except httpx.HTTPError:
            raise HTTPException(503, "room service unavailable")

        if resp.status_code == 404:
            raise HTTPException(400, "room not found")

        if resp.status_code >= 400:
            raise HTTPException(503, "room validation failed")


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

    with elasticapm.capture_span(
        "reservation.flow.create",
        span_type="app.reservation",
        labels={
            "app_room_id": room_id,
            "app_user_id": user_id,
            "app_duration_seconds": duration_seconds,
        },
    ):
        elasticapm.label(app_room_id=room_id, app_user_id=user_id)
        ensure_room_exists(room_id)

        if DB_LAT_MS:
            time.sleep(DB_LAT_MS / 1000)

        with elasticapm.capture_span("reservation.check.availability", span_type="app.reservation"):
            with engine.begin() as conn:
                overlap = conn.execute(text("""
                  SELECT COUNT(*) FROM reservations
                  WHERE room_id = :room_id
                    AND status = 'CONFIRMED'
                    AND (start_ts < :end_ts) AND (end_ts > :start_ts)
                """), {"room_id": room_id, "start_ts": s, "end_ts": e}).scalar_one()

                if overlap > 0:
                    elasticapm.label(app_reservation_conflict=True)
                    log("warn", "reservation conflict", room_id=room_id, user_id=user_id)
                    raise HTTPException(409, "time slot not available")

                with elasticapm.capture_span("reservation.persist.confirmed", span_type="app.reservation"):
                    rid = conn.execute(text("""
                      INSERT INTO reservations(room_id, user_id, start_ts, end_ts)
                      VALUES (:room_id, :user_id, :start_ts, :end_ts)
                      RETURNING id
                    """), {"room_id": room_id, "user_id": user_id, "start_ts": s, "end_ts": e}).scalar_one()

        with elasticapm.capture_span(
            "reservation.event.publish",
            span_type="messaging",
            span_subtype="redis",
            span_action="publish",
            labels={
                "app_messaging_system": "redis",
                "app_messaging_destination": "events",
                "app_reservation_id": rid,
            },
        ):
            traceparent = elasticapm.get_trace_parent_header() or ""
            trace_headers = {"traceparent": traceparent} if traceparent else {}
            event = {
                "type": "reservation.created",
                "reservation_id": rid,
                "room_id": room_id,
                "user_id": user_id,
                "trace": trace_headers,
            }
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
