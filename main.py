

import logging
import os
from fastapi import FastAPI, HTTPException

from telemetry import setup_otel
from elasticsearch import Elasticsearch
from dotenv import load_dotenv

logger = logging.getLogger("talkfinder.main")

app = FastAPI(title="TalkFinder", description="Agenda finder for conference attendees")

load_dotenv()

def es_client():
    es_url = os.getenv('ES_URL','')
    if not es_url:
        logger.error("App Un-healthy!!!ES_URL is not configured!!!")
        raise HTTPException(503, "App Un-healthy!!!ES_URL is not configured!!!")
    return Elasticsearch(es_url)



@app.get("/health")
def health() -> dict:
    logger.info("health ping")
    es = es_client()
    if es.ping():
        return {"app_status": "ok", "elasticsearch": "up"}
    return {"app_status": "ok", "elasticsearch": "down"}


setup_otel(app)
