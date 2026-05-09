import json
import os
import random
import threading
import time

import elasticapm
from fastapi import FastAPI
from redis import Redis

from common.apm import setup_apm
from common.logger import log

SERVICE = os.getenv("SERVICE_NAME", "notification-service")

redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))

FAIL_RATE = float(os.getenv("FAIL_RATE", "0.10"))
LAT_MS = int(os.getenv("ARTIFICIAL_LATENCY_MS", "50"))

app = FastAPI(title="Notification Service")
setup_apm(SERVICE, app)

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

                event_type = str(event.get("type", "unknown")).replace(".", "_")
                tx_name = f"notification.consume.{event_type}"

                client = elasticapm.get_client()
                trace_headers = event.get("trace", {})
                parent = elasticapm.trace_parent_from_headers(trace_headers) if trace_headers else None
                client.begin_transaction("messaging", trace_parent=parent)
                elasticapm.set_transaction_name(tx_name)

                tx_result = "success"
                with elasticapm.capture_span(
                    tx_name,
                    span_type="messaging",
                    span_subtype="redis",
                    span_action="process",
                    labels={
                        "app_messaging_system": "redis",
                        "app_messaging_destination": "events",
                        "app_event_type": event.get("type", "unknown"),
                        "app_reservation_id": event.get("reservation_id", 0),
                        "app_received_traceparent": str(trace_headers.get("traceparent", "")),
                    },
                ):
                    time.sleep(LAT_MS / 1000)

                    if random.random() < FAIL_RATE:
                        tx_result = "error"
                        log("error", "notification failed", event=event, error_type="simulated_503")
                    else:
                        log("info", "notification sent", event=event)

                client.end_transaction(name=tx_name, result=tx_result)


@app.on_event("startup")
def startup():
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    log("info", "notification worker started", fail_rate=FAIL_RATE, latency_ms=LAT_MS)


@app.get("/health")
def health():
    return {"ok": True}
