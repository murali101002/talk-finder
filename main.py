

import logging

from fastapi import FastAPI

from telemetry import setup_otel

logger = logging.getLogger("talkfinder.main")

app = FastAPI(title="TalkFinder", description="Agenda finder for conference attendees")


@app.get("/health")
def health() -> dict:
    logger.info("health ping")
    return {"status": "ok"}


setup_otel(app)
