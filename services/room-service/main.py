import os
from fastapi import FastAPI, Depends
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from common.otel import setup_telemetry
from common.logger import log
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

SERVICE = os.getenv("SERVICE_NAME", "room-service")
setup_telemetry(SERVICE)

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
    
    Args:
        date (str, optional): Fecha para filtrar disponibilidad (Formato YYYY-MM-DD). *Actualmente no implementado*.
        capacity (int, optional): Capacidad mínima requerida.
    """
    # TODO: Implementar lógica de filtrado por fecha cuando exista tabla de reservas
    q = "SELECT id, name, capacity, equipment FROM rooms"
    params = {}
    if capacity is not None:
        q += " WHERE capacity >= :cap"
        params["cap"] = capacity
    q += " ORDER BY capacity DESC"
    with engine.begin() as conn:
        rows = conn.execute(text(q), params).mappings().all()
    return {"rooms": list(rows)}

@app.get("/health")
def health():
    return {"ok": True}
