import os, json, random, time, threading
from fastapi import FastAPI
from redis import Redis
from common.otel import setup_telemetry
from common.logger import log
from opentelemetry import metrics, trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.propagate import extract
from opentelemetry.trace import SpanKind

SERVICE = os.getenv("SERVICE_NAME", "notification-service")
setup_telemetry(SERVICE)
tracer = trace.get_tracer(SERVICE)
meter = metrics.get_meter(SERVICE)

redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
RedisInstrumentor().instrument()

FAIL_RATE = float(os.getenv("FAIL_RATE", "0.10"))
LAT_MS = int(os.getenv("ARTIFICIAL_LATENCY_MS", "50"))
notification_sent_counter = meter.create_counter("notifications.sent")
notification_failed_counter = meter.create_counter("notifications.failed")
notification_latency_histogram = meter.create_histogram("notifications.processing.latency.ms")

app = FastAPI(title="Notification Service")
FastAPIInstrumentor.instrument_app(app)

stop_flag = False

def worker():
    last_id = "0-0"
    while not stop_flag:
        resp = redis.xread({"events": last_id}, block=1000, count=10)
        if not resp:
            continue
        for stream, msgs in resp:
            for msg_id, fields in msgs:
                last_id = msg_id.decode() if isinstance(msg_id, (bytes, bytearray)) else msg_id
                event_json = fields.get(b"event") or fields.get("event")
                if isinstance(event_json, (bytes, bytearray)):
                    event_json = event_json.decode()
                event = json.loads(event_json)
                context = extract(event.get("trace", {}))
                event_type = str(event.get("type", "unknown")).replace(".", "_")

                with tracer.start_as_current_span(
                    f"notification.consume.{event_type}",
                    context=context,
                    kind=SpanKind.CONSUMER,
                ) as span:
                    span.set_attribute("app_messaging_system", "redis")
                    span.set_attribute("app_messaging_destination", "events")
                    span.set_attribute("app_messaging_operation", "process")
                    span.set_attribute("app_event_type", event.get("type", "unknown"))
                    span.set_attribute("app_reservation_id", event.get("reservation_id", 0))
                    span.set_attribute("app_received_traceparent", str(event.get("trace", {}).get("traceparent", "")))

                    start_time = time.perf_counter()
                    time.sleep(LAT_MS / 1000)
                    latency_ms = (time.perf_counter() - start_time) * 1000
                    notification_latency_histogram.record(latency_ms)

                    if random.random() < FAIL_RATE:
                        notification_failed_counter.add(1)
                        span.add_event("notification.failed", {"app_error_type": "simulated_503"})
                        log("error", "notification failed", event=event, error_type="simulated_503")
                    else:
                        notification_sent_counter.add(1)
                        log("info", "notification sent", event=event)

@app.on_event("startup")
def startup():
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    log("info", "notification worker started", fail_rate=FAIL_RATE, latency_ms=LAT_MS)

@app.get("/health")
def health():
    return {"ok": True}
