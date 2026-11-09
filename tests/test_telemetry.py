"""Tests for telemetry.py — the basic pins only, all hermetic:
- env-only config, both header forms accepted
- :4317 => grpc, else http/protobuf
- no endpoint => tracing disabled and the global provider untouched
"""

import logging

import telemetry
import opentelemetry.trace as otel_trace


def test_headers_parse_both_documented_forms():
    assert telemetry._parse_headers("Authorization=Bearer x") == {"Authorization": "Bearer x"}
    assert telemetry._parse_headers("Authorization: token123") == {"Authorization": "token123"}


def test_protocol_from_port_4317_grpc_else_http(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_PROTOCOL", raising=False)
    assert telemetry._pick_protocol("https://ingress.example.com:4317") == "grpc"
    assert telemetry._pick_protocol("https://ingress.example.com:4318") == "http/protobuf"


def test_no_endpoint_disables_tracing_and_never_touches_the_provider(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    calls = []
    monkeypatch.setattr(otel_trace, "set_tracer_provider",
                        lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "   ")  # whitespace only
    telemetry.setup_otel(None)
    assert calls == []
    assert "tracing/logs disabled" in caplog.text
