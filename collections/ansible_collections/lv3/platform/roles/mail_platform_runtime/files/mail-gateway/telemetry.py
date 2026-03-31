import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_TELEMETRY_CONFIGURED = False
_SENTRY_CONFIGURED = False


def parse_resource_attributes(raw_attributes: str) -> dict[str, str]:
    attributes: dict[str, str] = {}
    for item in raw_attributes.split(","):
        item = item.strip()
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            attributes[key] = value
    return attributes


def configure_sentry(app) -> None:
    global _SENTRY_CONFIGURED

    dsn = os.getenv("SENTRY_DSN", "").strip()
    if _SENTRY_CONFIGURED or not dsn:
        return

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.httpx import HttpxIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", "").strip() or None,
        release=os.getenv("SENTRY_RELEASE", "").strip() or None,
        traces_sample_rate=0.0,
        profiles_sample_rate=0.0,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            HttpxIntegration(),
        ],
    )
    _SENTRY_CONFIGURED = True


def configure_telemetry(app) -> None:
    global _TELEMETRY_CONFIGURED

    configure_sentry(app)

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "").strip()
    if _TELEMETRY_CONFIGURED or not endpoint:
        return

    resource_attributes = parse_resource_attributes(os.getenv("OTEL_RESOURCE_ATTRIBUTES", ""))
    resource_attributes["service.name"] = os.getenv("OTEL_SERVICE_NAME", "mail-gateway")
    resource = Resource.create(resource_attributes)

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app, excluded_urls="/healthz")
    HTTPXClientInstrumentor().instrument()
    _TELEMETRY_CONFIGURED = True
