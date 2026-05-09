import os
import elasticapm
from elasticapm.contrib.starlette import ElasticAPM, make_apm_client
from fastapi import FastAPI
from common.logger import configure_ecs_logging

_INSTRUMENTED = False


def setup_apm(service_name: str, app: FastAPI) -> None:
    global _INSTRUMENTED

    configure_ecs_logging()

    if not _INSTRUMENTED:
        elasticapm.instrument()
        _INSTRUMENTED = True

    # Prefer explicit ELASTIC_APM_* env vars as recommended by Elastic docs.
    os.environ.setdefault("ELASTIC_APM_SERVICE_NAME", service_name)
    os.environ.setdefault("ELASTIC_APM_SERVICE_VERSION", os.getenv("SERVICE_VERSION", "0.1.0"))
    os.environ.setdefault("ELASTIC_APM_ENVIRONMENT", os.getenv("ENVIRONMENT", "dev"))
    os.environ.setdefault("ELASTIC_APM_SERVER_URL", os.getenv("ELASTIC_APM_SERVER_URL", "http://apm-server:8200"))

    client = make_apm_client()

    app.add_middleware(ElasticAPM, client=client)
