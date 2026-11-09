"""Basic hermetic tests for retriever.py — the ES client is faked, so no
Elasticsearch and no network; no OpenAI (the key path is only evidence-gated).

Pins, one per designed behavior:
- search_talks sorts by start time, then room (the browse contract)
- embed_query returns None with no OPENAI_API_KEY (callers skip the knn half)
- ensure_index 503s when the index is missing (run load_seed.py first)
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import retriever


def _fake_client(hits: list, index_exists: bool = True):
    """Shape the ES search/indices surface exactly where retriever reads it."""
    return SimpleNamespace(
        indices=SimpleNamespace(exists=lambda index: index_exists),
        search=lambda *a, **kw: {"hits": {"hits": hits}},
    )


def test_search_talks_sorts_by_start_then_room(monkeypatch):
    shuffled_hits = [
        {"_source": {"id": "T03", "start": "12:00", "room": "Hall A"}},
        {"_source": {"id": "T02", "start": "11:00", "room": "Hall B"}},
        {"_source": {"id": "T04", "start": "11:00"}},
        {"_source": {"id": "T01", "start": "11:00", "room": "Hall A"}},
    ]
    monkeypatch.setattr(retriever, "client", _fake_client(shuffled_hits))
    assert [talk["id"] for talk in retriever.search_talks()] == ["T04", "T01", "T02", "T03"]


def test_embed_query_is_none_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)  # beats any .env key
    assert retriever.embed_query("kubernetes") is None


def test_ensure_index_is_503_when_index_missing(monkeypatch):
    monkeypatch.setattr(retriever, "client", _fake_client(hits=[], index_exists=False))
    with pytest.raises(HTTPException) as err:
        retriever.ensure_index()
    assert err.value.status_code == 503
    assert "load_seed.py" in err.value.detail
