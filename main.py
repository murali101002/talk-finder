

import logging
import os
from functools import lru_cache

from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from fastapi import FastAPI, HTTPException

from routers import talks
from telemetry import setup_otel

logger = logging.getLogger("talkfinder.main")

app = FastAPI(title="TalkFinder", description="Agenda finder for conference attendees")

load_dotenv()

app.include_router(talks.router)

@lru_cache(maxsize=1)
def _build_es(es_url: str) -> Elasticsearch:
    return Elasticsearch(es_url)

def es_client() -> Elasticsearch:
    es_url = os.getenv('ES_URL', '')
    if not es_url:
        logger.error("ES_URL is not configured")
        raise HTTPException(503, "ES_URL is not configured")
    return _build_es(es_url)



@app.get("/health")
def health() -> dict:
    logger.info("health ping")
    es = es_client()
    if es.ping():
        return {"app_status": "ok", "elasticsearch": "up"}
    return {"app_status": "ok", "elasticsearch": "down"}


setup_otel(app)
