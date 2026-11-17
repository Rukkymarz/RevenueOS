"""OpenTelemetry setup and the standard span attributes every tool call carries."""
import os

from opentelemetry import propagate, trace

# Standard attributes (spec 1.8). Every tool-call span sets all four.
TASK_ID, AGENT_ID, TOOL, RISK_CLASS = "task_id", "agent_id", "tool", "risk_class"

_configured = False


def setup_tracing(service_name: str) -> trace.Tracer:
    """Configure the global tracer provider once; exports OTLP/HTTP to OTEL_EXPORTER_OTLP_ENDPOINT."""
    global _configured
    if not _configured:
        # The SDK loads here, not at import: receipt writers that never trace don't need it.
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if endpoint:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=endpoint.rstrip("/") + "/v1/traces")
            sync = os.environ.get("REVENUEOS_OTEL_SYNC") == "1"
            provider.add_span_processor(SimpleSpanProcessor(exporter) if sync else BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _configured = True
    return trace.get_tracer(service_name)


def standard_attributes(task_id: str, agent_id: str, tool: str, risk_class: str) -> dict:
    return {TASK_ID: task_id, AGENT_ID: agent_id, TOOL: tool, RISK_CLASS: risk_class}


def inject_traceparent() -> str | None:
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    return carrier.get("traceparent")


def extract_context(traceparent: str | None):
    return propagate.extract({"traceparent": traceparent}) if traceparent else None
