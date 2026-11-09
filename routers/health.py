"""GET /health — liveness with an honest ES check baked in (up/down stated,
never faked; unconfigured ES_URL is a 503, not a pretending 200)."""

import logging
import os
from functools import lru_cache

from elasticsearch import Elasticsearch
from fastapi import APIRouter, HTTPException

logger = logging.getLogger("talkfinder.health")

router = APIRouter()


@lru_cache(maxsize=1)
def _build_es(es_url: str) -> Elasticsearch:
    return Elasticsearch(es_url)


def es_client() -> Elasticsearch:
    es_url = os.getenv("ES_URL", "")
    if not es_url:
        logger.error("ES_URL is not configured")
        raise HTTPException(503, "ES_URL is not configured")
    return _build_es(es_url)


@router.get("/health")
def health() -> dict:
    logger.info("health ping")
    es = es_client()
    if es.ping():
        return {"app_status": "ok", "elasticsearch": "up"}
    return {"app_status": "ok", "elasticsearch": "down"}
