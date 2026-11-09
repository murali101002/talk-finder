import os

# Hermetic by construction: kill the two env gates BEFORE any app module is
# imported (conftest loads before test modules). setup_otel() calls
# load_dotenv(), but load_dotenv never overrides variables that are already
# set — so an empty string here wins over a real endpoint in .env:
# no OTLP exporter, no TracerProvider, no OpenAI tier, no network anywhere
# in `uv run pytest -q`.
os.environ["OPENAI_API_KEY"] = ""
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = ""

import pytest


@pytest.fixture(autouse=True)
def _hermetic_env():
    """Force the same two gates per test, regardless of shell env or .env."""
    saved = os.environ.copy()
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = ""
    yield
    os.environ.clear()
    os.environ.update(saved)
