"""OpenTelemetry -> Dash0 (cloud; endpoint/headers/dataset come ONLY from env).

Standard FastAPI spans only, one trace per request, no custom spans yet.
Python application logs (the ES/LLM result lines included) additionally
export as OTLP logs through the same endpoint/protocol/headers — see
_setup_log_export. Verify in Dash0: hit POST /agenda, then find the same
request as a trace in Dash0 and the why-lines under Logs.

Dash0 specifics honored here:
- dataset is selected by the "Dash0-Dataset" HEADER (not a resource attribute)
- endpoint needs a scheme; a bare host:port (e.g. from the onboarding snippet)
  is normalized to https://
- OTLP protocol comes from OTEL_EXPORTER_OTLP_PROTOCOL, defaulting to grpc
  when the endpoint targets :4317 (Dash0's gRPC ingress port) and to
  http/protobuf otherwise
- header values are accepted in either "key=value,key2=value2" (OTel standard)
  or "key: value, key2: value2" (paste-from-docs) form
"""

import logging
import os

from dotenv import load_dotenv

logger = logging.getLogger("talkfinder.telemetry")


def _parse_headers(raw: str) -> dict[str, str]:
    """Parse OTLP headers from either k=v or "k: v" comma-separated format."""
    headers: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            key, value = part.split("=", 1)
        elif ":" in part:
            key, value = part.split(":", 1)
        else:
            logger.warning("Skipping unparseable OTLP header fragment (no key/value separator).")
            continue
        headers[key.strip()] = value.strip().strip("'\"")
    return headers


def _normalize_endpoint(endpoint: str) -> str:
    if "://" not in endpoint:
        endpoint = "https://" + endpoint  # onboarding snippets often omit scheme
    return endpoint


def _pick_protocol(endpoint: str) -> str:
    explicit = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "").strip()
    if explicit:
        return explicit
    return "grpc" if endpoint.rstrip("/").endswith(":4317") else "http/protobuf"


SIGNAL_PATHS = {
    "spans": "/v1/traces",
    "logs": "/v1/logs",
    "metrics": "/v1/metrics",
}


def _signal_url(endpoint: str, signal: str) -> str | None:
    """Build the OTLP http/protobuf URL for one signal.

    The exporter posts to the URL VERBATIM — it does not append the signal
    path itself (verified: a bare endpoint lands on "/"). So the configured
    endpoint either carries no signal path (bare Dash0 ingress — append) or
    the exact path of the given signal (use as-is). Any other signal's path
    (e.g. .../v1/logs reused for spans, or .../v1/metrics) is a config error:
    refuse loudly and return None so telemetry degrades to console-only
    instead of posting twice-joined garbage paths like /v1/logs/v1/traces.
    """
    url = endpoint.rstrip("/")
    wanted = SIGNAL_PATHS[signal]
    for other_path in SIGNAL_PATHS.values():
        if url.endswith(other_path):
            if other_path == wanted:
                return url
            logger.error(
                "OTEL_EXPORTER_OTLP_ENDPOINT is routed to another signal's "
                "path: %s ends with %s so %s cannot use it — telemetry "
                "disabled (console logging still works). Point it at the "
                "bare ingress or at %s.",
                url, other_path, signal, wanted,
            )
            return None
    return f"{url}{wanted}"


def setup_otel(app) -> None:
    load_dotenv()
    # root level from LOG_LEVEL (default INFO): the ES and LLM result logs
    # are INFO, so this must run even when telemetry itself is disabled
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(levelname)s %(name)s: %(message)s",
    )
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        logger.info("OTEL_EXPORTER_OTLP_ENDPOINT not set — tracing/logs disabled.")
        return

    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    endpoint = _normalize_endpoint(endpoint)
    protocol = _pick_protocol(endpoint)

    headers = _parse_headers(os.getenv("OTEL_EXPORTER_OTLP_HEADERS", ""))
    dataset = os.getenv("DASH0_DATASET", "").strip()
    if dataset and not any(k.lower() == "dash0-dataset" for k in headers):
        headers["Dash0-Dataset"] = dataset  # Dash0 routes datasets by header
    if protocol == "grpc":
        # gRPC metadata requires lowercase keys — "Authorization" (capital A)
        # is rejected as invalid metadata by the grpc stack
        headers = {k.lower(): v for k, v in headers.items()}

    resource = Resource.create({"service.name": "talkfinder"})

    # each signal checks the URL independently: an endpoint routed to
    # another signal disables only that signal, not every one of them
    spans_url = endpoint if protocol == "grpc" else _signal_url(endpoint, "spans")
    if spans_url is not None:
        if protocol == "grpc":
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            spans_exporter = OTLPSpanExporter(endpoint=spans_url, headers=headers)
        else:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )
            spans_exporter = OTLPSpanExporter(endpoint=spans_url, headers=headers)
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(spans_exporter))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        logger.warning(
            "OTLP tracing ON: %s -> %s, dataset=%s, auth header %s",
            protocol, spans_url.split("://", 1)[-1],
            dataset or "(token default)",
            "present" if "authorization" in {k.lower() for k in headers} else "MISSING",
        )

    logs_url = endpoint if protocol == "grpc" else _signal_url(endpoint, "logs")
    if logs_url is not None:
        _setup_log_export(logs_url, protocol, headers, dataset, resource)


def _setup_log_export(endpoint: str, protocol: str, headers: dict,
                      dataset: str, resource) -> None:
    """Route Python logs to the same OTLP backend as traces.

    The root logging handler stays in the terminal; this ADDS an export
    sink (console and OLTP ship the same records). Records emitted inside
    a request carry that request's trace_id, so in the backend's Logs view
    an ES/LLM line joins the very trace that produced it.
    """
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

    if protocol == "grpc":
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
        exporter = OTLPLogExporter(endpoint=endpoint, headers=headers)
    else:
        # the URL check (exact matching signal path, refuse wrong-signal
        # routes) already ran in setup_otel — here it is always correct
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        exporter = OTLPLogExporter(endpoint=endpoint, headers=headers)

    log_provider = LoggerProvider(resource=resource)
    log_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    # INFO so the ES/LLM result lines export; root's own level stays as set
    logging.getLogger().addHandler(
        LoggingHandler(level=logging.INFO, logger_provider=log_provider))
    logger.warning(
        "OTLP log export ON: every talkfinder.* (and std-lib) log line "
        "duplicates to the backend Logs view, trace-correlated, dataset=%s",
        dataset or "(token default)",
    )
