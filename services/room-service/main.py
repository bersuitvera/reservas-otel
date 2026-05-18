import os

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from common.otel import setup_telemetry
from common.logger import log
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry import metrics, trace
from opentelemetry.trace import SpanKind


SERVICE = os.getenv("SERVICE_NAME", "room-service")
setup_telemetry(SERVICE)
tracer = trace.get_tracer(SERVICE)
meter = metrics.get_meter(SERVICE)

room_list_counter = meter.create_counter("rooms.list", description="Consultas de listado de habitaciones")
room_detail_counter = meter.create_counter("rooms.detail", description="Consultas de detalle de habitación")
room_notfound_counter = meter.create_counter("rooms.notfound", description="Consultas de habitación no encontrada")

DATABASE_URL = os.getenv("DATABASE_URL")
_engine: Engine | None = None

def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        SQLAlchemyInstrumentor().instrument(engine=_engine)
    return _engine

app = FastAPI(title="Room Service")
FastAPIInstrumentor.instrument_app(app)

@app.on_event("startup")
def startup():
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS rooms (
              id SERIAL PRIMARY KEY,
              name TEXT NOT NULL,
              capacity INT NOT NULL,
              equipment TEXT NOT NULL DEFAULT ''
            )
        """))
    if os.getenv("STARTUP_SEED", "false").lower() == "true":
        with engine.begin() as conn:
            cnt = conn.execute(text("SELECT COUNT(*) FROM rooms")).scalar_one()
            if cnt == 0:
                conn.execute(text("""
                  INSERT INTO rooms(name, capacity, equipment) VALUES
                  ('Sala A', 6, 'TV,Whiteboard'),
                  ('Sala B', 10, 'Projector'),
                  ('Sala C', 4, 'Whiteboard'),
                  ('Sala D', 12, 'TV,Projector')
                """))
        log("info", "seeded rooms")


@app.get("/rooms")
def list_rooms(date: str | None = None, capacity: int | None = None, engine: Engine = Depends(get_engine)):
    """
    Lista las habitaciones disponibles.
    """
    with tracer.start_as_current_span("room.list", kind=SpanKind.INTERNAL) as span:
        span.set_attribute("app_capacity_filter", capacity if capacity is not None else "any")
        room_list_counter.add(1, {"capacity": capacity if capacity is not None else 0})
        q = "SELECT id, name, capacity, equipment FROM rooms"
        params = {}
        if capacity is not None:
            q += " WHERE capacity >= :cap"
            params["cap"] = capacity
        q += " ORDER BY capacity DESC"
        with engine.begin() as conn:
            rows = conn.execute(text(q), params).mappings().all()
        span.set_attribute("app_room_count", len(rows))
        return {"rooms": list(rows)}


@app.get("/rooms/{room_id}")
def get_room(room_id: int, engine: Engine = Depends(get_engine)):
    with tracer.start_as_current_span("room.detail", kind=SpanKind.INTERNAL) as span:
        span.set_attribute("app_room_id", room_id)
        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT id, name, capacity, equipment FROM rooms WHERE id = :id"),
                {"id": room_id},
            ).mappings().first()
        if not row:
            room_notfound_counter.add(1, {"room_id": room_id})
            span.set_attribute("app_room_found", False)
            span.set_status(trace.Status(trace.StatusCode.ERROR, "not found"))
            raise HTTPException(404, "room not found")
        room_detail_counter.add(1, {"room_id": room_id})
        span.set_attribute("app_room_found", True)
        return dict(row)

@app.get("/health")
def health():
    return {"ok": True}
