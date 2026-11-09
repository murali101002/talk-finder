"""Boundary models ONLY — where HTTP meets the app.

pydantic earns its keep here: request validation (422s), payload bounding
and OpenAPI docs. Inside these lines the pipeline speaks plain dicts —
no Talk model, no item models (boundary-models policy). The response model
still bounds shapes: every agenda item dict, and every nested talk dict,
must have its embedding stripped at the composition root before assembly.
"""

from typing import Literal

from pydantic import BaseModel


class AgendaRequest(BaseModel):
    topics: list[str]
    accessibility: list[str] = []


class UnscheduledItem(BaseModel):
    """One verdict the builder owed the user: a talk they cannot fully have.

    alternative is the highest-ranked agenda pick in the loser's own time
    window (builder.offer_alternatives) — dict or None, never a swap the
    agenda itself would clash with.
    """

    talk: dict
    reason: Literal["full", "clash"]
    clashes_with: list[str] = []
    alternative: dict | None = None
    why_line: str = ""


class AgendaResponse(BaseModel):
    topics: list[str] = []
    agenda: list[dict] = []               # clash-free, time-sorted item dicts
    unscheduled: list[UnscheduledItem] = []  # full/clash losers, never hidden
    note: str | None = None
