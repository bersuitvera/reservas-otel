import logging
import os
import socket
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def _build_resource(service_name: str) -> Resource:
    return Resource.create({
        "service.namespace": os.getenv("SERVICE_NAMESPACE", "reservas"),
        "service.name": service_name,
        "service.version": os.getenv("SERVICE_VERSION", "0.1.0"),
        "service.instance.id": os.getenv("SERVICE_INSTANCE_ID", socket.gethostname()),
        "deployment.environment.name": os.getenv("ENVIRONMENT", "dev"),
    })


def _configure_application_logger(service_name: str, logger_provider: LoggerProvider) -> None:
    app_logger = logging.getLogger(service_name)
    if getattr(app_logger, "_otel_handler_configured", False):
        return

    app_logger.addHandler(LoggingHandler(level=logging.INFO, logger_provider=logger_provider))
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False
    app_logger._otel_handler_configured = True


def setup_telemetry(service_name: str) -> None:
    resource = _build_resource(service_name)

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    set_logger_provider(logger_provider)

    _configure_application_logger(service_name, logger_provider)
