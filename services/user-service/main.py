import os

from fastapi import FastAPI, HTTPException
from common.otel import setup_telemetry
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry import metrics, trace
from opentelemetry.trace import SpanKind

SERVICE = os.getenv("SERVICE_NAME", "user-service")
setup_telemetry(SERVICE)
tracer = trace.get_tracer(SERVICE)
meter = metrics.get_meter(SERVICE)

user_lookup_counter = meter.create_counter("users.lookup", description="Número de consultas de usuario")
user_notfound_counter = meter.create_counter("users.notfound", description="Consultas de usuario no encontrado")

app = FastAPI(title="User Service")
FastAPIInstrumentor.instrument_app(app)

USERS = {
    1: {"id": 1, "name": "Ana", "email": "ana@example.com"},
    2: {"id": 2, "name": "Luis", "email": "luis@example.com"},
    3: {"id": 3, "name": "Marta", "email": "marta@example.com"},
}

@app.get("/users/{user_id}")
def get_user(user_id: int):
    """
    Obtiene la información pública de un usuario por su ID.
    """
    with tracer.start_as_current_span("user.lookup", kind=SpanKind.INTERNAL) as span:
        span.set_attribute("app_user_id", user_id)
        u = USERS.get(user_id)
        if not u:
            user_notfound_counter.add(1, {"user_id": user_id})
            span.set_attribute("app_user_found", False)
            span.set_status(trace.Status(trace.StatusCode.ERROR, "not found"))
            raise HTTPException(404, "not found")
        user_lookup_counter.add(1, {"user_id": user_id})
        span.set_attribute("app_user_found", True)
        # No meter PII en atributos de trazas/logs en un lab realista
        return {"id": u["id"], "name": u["name"]}

@app.get("/health")
def health():
    return {"ok": True}
