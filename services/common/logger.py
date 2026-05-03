import json
import logging
import os
import sys
import time
from typing import Any, Dict
from opentelemetry.trace import get_current_span

def log(level: str, msg: str, **fields: Any) -> None:
    service = os.getenv("SERVICE_NAME", "unknown")
    app_logger = logging.getLogger(service)
    span = get_current_span()
    ctx = span.get_span_context() if span else None
    trace_id = f"{ctx.trace_id:032x}" if ctx and ctx.trace_id else None
    span_id = f"{ctx.span_id:016x}" if ctx and ctx.span_id else None

    payload: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "level": level,
        "service": service,
        "message": msg,
        "trace_id": trace_id,
        "span_id": span_id,
        **fields,
    }

    line = json.dumps(payload, ensure_ascii=False)
    print(line, file=sys.stdout, flush=True)

    app_logger.log(_to_level(level), msg, extra=_sanitize_fields(fields))


def _to_level(level: str) -> int:
    return {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warn": logging.WARNING,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }.get(level.lower(), logging.INFO)


def _sanitize_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for key, value in fields.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            clean[key] = value
        else:
            clean[key] = json.dumps(value, ensure_ascii=False)
    return clean
