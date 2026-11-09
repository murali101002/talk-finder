"""Tests for main.py — hermetic: telemetry off via conftest, ES faked here."""

from fastapi.testclient import TestClient

import main
from main import app


class _FakeES:
    def __init__(self, up: bool):
        self._up = up

    def ping(self) -> bool:
        return self._up


def test_health_reports_ok_with_es_up(monkeypatch):
    monkeypatch.setattr(main, "es_client", lambda: _FakeES(True))
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert r.json() == {"app_status": "ok", "elasticsearch": "up"}


def test_health_is_503_when_es_url_is_not_configured(monkeypatch):
    monkeypatch.setenv("ES_URL", "")  # load_dotenv never overrides existing vars
    r = TestClient(app).get("/health")
    assert r.status_code == 503
