import json
import logging
import os
import sys
from typing import Any, Dict
import ecs_logging


def configure_ecs_logging() -> None:
    root_logger = logging.getLogger()
    if getattr(root_logger, "_ecs_handler_configured", False):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ecs_logging.StdlibFormatter())
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)
    root_logger._ecs_handler_configured = True

def log(level: str, msg: str, **fields: Any) -> None:
    configure_ecs_logging()
    service = os.getenv("SERVICE_NAME", "unknown")
    app_logger = logging.getLogger(service)
    log_record_fields = {
        "service.name": service,
        "service.environment": os.getenv("ENVIRONMENT", "dev"),
        **fields,
    }
    app_logger.log(_to_level(level), msg, extra=_sanitize_fields(log_record_fields))


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
