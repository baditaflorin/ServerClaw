import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_TELEMETRY_CONFIGURED = False


def configure_telemetry(app) -> None:
    global _TELEMETRY_CONFIGURED

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "").strip()
    if _TELEMETRY_CONFIGURED or not endpoint:
        return

    resource = Resource.create(
        {
            "service.name": os.getenv("OTEL_SERVICE_NAME", "mail-gateway"),
        }
    )

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app, excluded_urls="/healthz")
    HTTPXClientInstrumentor().instrument()
    _TELEMETRY_CONFIGURED = True
