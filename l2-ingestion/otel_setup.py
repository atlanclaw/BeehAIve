"""
OTEL-Setup für pkb-ingestion (L2).
Einmalig im FastAPI-lifespan initialisiert.
service.name=pkb-ingestion als Resource-Attribut —
alle L2-Spans (L2-05, L2-06, L2-07) erben es automatisch.

Pflicht-Env:
  OTEL_EXPORTER_OTLP_ENDPOINT  (default: http://otel-collector:4317)
  OTEL_SAMPLE_RATE              (default: 1.0)
  SERVICE_VERSION               (default: 0.1.0)
"""
import logging
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

log = logging.getLogger("pkb.l2.otel")

OTLP_ENDPOINT   = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
SAMPLE_RATE     = float(os.getenv("OTEL_SAMPLE_RATE", "1.0"))
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "0.1.0")

_initialized = False


def setup_tracing() -> None:
    global _initialized
    if _initialized:
        return

    resource = Resource.create({
        "service.name":    "pkb-ingestion",
        "service.version": SERVICE_VERSION,
        "pkb.layer":       "L2",
    })

    exporter = OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True)
    provider = TracerProvider(
        resource=resource,
        sampler=TraceIdRatioBased(SAMPLE_RATE),
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    _initialized = True
    log.info(
        "OTEL TracerProvider initialisiert: service=pkb-ingestion, "
        "endpoint=%s, sample_rate=%.2f",
        OTLP_ENDPOINT, SAMPLE_RATE,
    )


def get_tracer(name: str):
    return trace.get_tracer(name)
