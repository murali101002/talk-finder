

import logging
import os

from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from fastapi import HTTPException

logger = logging.getLogger("talkfinder.retriever")

load_dotenv()

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
INDEX = "talks"
# MUST be the same model load_seed.py used for the corpus, or the knn
# halves live in different spaces. Set EMBEDDING_MODEL in .env for both.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

client = Elasticsearch(ES_URL)


def embed_query(text: str) -> list[float] | None:
    
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.info("api_key not found!!!")
        return None
    from openai import OpenAI

    logger.debug("api_key present.")
    resp = OpenAI(api_key=api_key).embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return [float(x) for x in resp.data[0].embedding]


def ensure_index() -> None:
    if not client.indices.exists(index=INDEX):
        raise HTTPException(
            status_code=503,
            detail="Index 'talks' not found — run load_seed.py first.",
        )


# accessibility tag -> does this talk's room actually satisfy it?
# Missing/zero values fail the need conservatively (never silently pass).
_ACCESS_CHECKS = {
    "step_free": lambda talk: bool(talk.get("step_free")),
    "wheelchair": lambda talk: int(talk.get("wheelchair_spaces") or 0) > 0,
    "hearing_loop": lambda talk: bool(talk.get("hearing_loop")),
    "captions": lambda talk: bool(talk.get("captions")),
    "sign_language": lambda talk: bool(talk.get("sign_language")),
}


def _meets_access(talk: dict, needs: set[str]) -> bool:
    """True when every requested accommodation holds for this talk.

    The filter is Python-side (ES is not asked to rank accommodation fields);
    unknown tags are ignored here — the composition root warns about them.
    """
    return all(
        check(talk)
        for tag, check in _ACCESS_CHECKS.items()
        if tag in needs
    )


ACCESS_TAGS = frozenset(_ACCESS_CHECKS)


def count_meeting_needs(needs: set[str]) -> int:
    """How many of today's talks satisfy every requested accommodation.

    The corpus-level count the empty-result note needs: it separates "the
    constraint can never be met today" from "these interests have no hits"
    instead of letting the note blame topics for a filtering outcome.
    """
    ensure_index()
    resp = client.search(index=INDEX, query={"match_all": {}}, size=1000)
    return sum(
        1
        for hit in resp["hits"]["hits"]
        if _meets_access(hit["_source"], needs)
    )


def search_talks() -> list[dict]:
    """All talks, sorted by start time then room (used by GET /talks)."""
    ensure_index()
    resp = client.search(index=INDEX, query={"match_all": {}}, size=100)
    found = [hit["_source"] for hit in resp["hits"]["hits"]]
    logger.info("ES match_all: %d talks returned (%s)", len(found),
                ", ".join(t["id"] for t in found) or "none")
    return sorted(found, key=lambda talk: (talk["start"], talk.get("room", "")))


def distinct_topics() -> list[str]:
    """Distinct topic keywords across the corpus, alphabetical.
    """
    ensure_index()
    resp = client.search(
        index=INDEX,
        size=0,
        aggs={"topics": {"terms": {"field": "topics", "size": 50}}},
    )
    buckets = resp["aggregations"]["topics"]["buckets"]
    return sorted(bucket["key"] for bucket in buckets)


def search_candidates(text: str, size: int = 20,
                      needs: set[str] | None = None) -> list[dict]:
    """Step 1 of /agenda: ranked hybrid-search candidates for an interest string.

    Returns [{"talk": <source doc>, "score": <float>}, ...], strongest first.
    ~size candidates on purpose — the builder needs to SEE overlaps to resolve
    them, not just the top 5.

    Hybrid: multi_match (BM25, exact keyword recall) + knn (semantic recall
    via the query embedding). ES fuses both hit lists into one _score.
    Without OPENAI_API_KEY the knn half is skipped and ranking is BM25 only.
    `needs` (validated at the request boundary) filters hits in Python via
    _meets_access — never silently: the count that fell out is logged.
    """
    ensure_index()
    vector = embed_query(text)
    # over-fetch when an access filter will run after ES cut to size: talks
    # ranked just below the window may be exactly the accessible ones
    fetch_size = max(size * 4, 50) if needs else size
    ranked = _search_hybrid_with_embedding(text, fetch_size, vector) \
        if vector is not None else _search_bm25_only(text, fetch_size)
    if needs:
        kept = [hit for hit in ranked if _meets_access(hit["talk"], needs)]
        logger.info(
            "access filter: %d of %d hits pass needs=%s",
            len(kept), len(ranked), sorted(needs),
        )
        ranked = kept
    return ranked


def _search_hybrid_with_embedding(text: str, size: int,
                                  vector: list[float]) -> list[dict]:
    resp = client.search(
        index=INDEX,
        size=size,
        query={
            "multi_match": {
                "query": text,
                "fields": ["title^2", "abstract", "speaker", "topics"],
            }
        },
        knn={
            "field": "embedding",
            "query_vector": vector,
            "k": min(10, size),
            "num_candidates": 50,
        },
    )
    hits = [
        {"talk": hit["_source"], "score": hit.get("_score", 0.0)}
        for hit in resp["hits"]["hits"]
    ]
    logger.info("ES hybrid: %d hits for %r (%s)", len(hits), text,
                ", ".join(f"{h['talk']['id']}:{h['score']:.2f}" for h in hits) or "none")
    return hits


def _search_bm25_only(text: str, size: int) -> list[dict]:
    """Fallback when no OPENAI_API_KEY is set: multi_match only."""
    resp = client.search(
        index=INDEX,
        size=size,
        query={
            "multi_match": {
                "query": text,
                "fields": ["title^2", "abstract", "speaker", "topics"],
            }
        },
    )
    hits = [
        {"talk": hit["_source"], "score": hit.get("_score", 0.0)}
        for hit in resp["hits"]["hits"]
    ]
    logger.info("ES bm25-only (no key): %d hits for %r (%s)", len(hits), text,
                ", ".join(f"{h['talk']['id']}:{h['score']:.2f}" for h in hits) or "none")
    return hits
