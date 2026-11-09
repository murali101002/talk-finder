"""GET /talks — the full corpus, time-sorted, for the browse view.
GET /topics — distinct topic keywords, for the frontend's topic multi-select.

The embedding NEVER rides the wire — thousands of floats per talk, no
consumer — so it is stripped here at the boundary (plain dicts, no Talk
model: the pipeline speaks dicts, only AgendaRequest/AgendaResponse earn
pydantic)."""

from fastapi import APIRouter

from retriever import distinct_topics, search_talks

router = APIRouter()


@router.get("/talks")
def talks() -> list[dict]:
    return [
        {k: v for k, v in talk.items() if k != "embedding"}
        for talk in search_talks()
    ]


@router.get("/topics")
def topics() -> list[str]:
    return distinct_topics()
