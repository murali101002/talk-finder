

import logging

from fastapi import APIRouter, HTTPException

from builder import build_plan, offer_alternatives
from explain import attach_lines
from models import AgendaRequest, AgendaResponse, UnscheduledItem
from retriever import (ACCESS_TAGS, count_meeting_needs, distinct_topics,
                       ensure_index, search_candidates)
from scoring import rank_candidates

logger = logging.getLogger("talkfinder.agenda")

router = APIRouter()


def _flatten(candidate: dict) -> dict:
    """Ranked candidate -> one flat item dict for the wire: talk fields +
    score breakdown, embedding stripped (it must NEVER ride the response)."""
    talk = candidate["talk"]
    return {
        **{k: v for k, v in talk.items() if k != "embedding"},
        **{k: candidate[k] for k in (
            "relevance_score", "speaker_score", "adjusted_rating",
            "is_new_speaker", "final_score") if k in candidate},
    }


@router.post(
    "/agenda",
    response_model=AgendaResponse,
    response_model_exclude_none=True,
)
def agenda(payload: AgendaRequest) -> dict:
    topics = [t.strip().lower() for t in payload.topics if t.strip()]
    if not topics:
        raise HTTPException(
            status_code=400,
            detail="No topics requested — pick at least one interest that "
                   "describes what you want to see today.",
        )

    ensure_index()

    needs = {a.strip().lower().replace("-", "_").replace(" ", "_")
             for a in (payload.accessibility or [])}
    # a room-speak normalization: "step free"/"step-free" both map to the
    # seed's step_free field; anything we cannot verify is warned, never
    # silently assumed
    scored = search_candidates(", ".join(topics), needs=needs)
    if not scored:
        # an empty result must name its cause: when an accessibility need
        # emptied the answer, the note says so — never blame topics
        if needs:
            accessible = count_meeting_needs(needs)
            if accessible == 0:
                return AgendaResponse(
                    topics=topics,
                    note=f"No talk today satisfies {', '.join(sorted(needs))} "
                         "— nothing was scheduled rather than pretending the "
                         "constraint was applied.",
                ).model_dump()
            return AgendaResponse(
                topics=topics,
                note=f"{accessible} talk(s) satisfy your accessibility "
                     "request, but none of them match these interests. "
                     "Try broader topic words.",
            ).model_dump()
        return AgendaResponse(topics=topics, note="No matching talks for these "
                           "interests. Try broader topic words.").model_dump()

    ranked = rank_candidates([
        {"talk": c["talk"], "relevance": c["score"]} for c in scored
    ])
    plan = offer_alternatives(build_plan(ranked))

    agenda_items = [_flatten(pick) for pick in plan["agenda"]]
    agenda_items = attach_lines(agenda_items, topics)

    unscheduled = []
    loser_talks = (
        attach_lines(
            [_flatten(item) for item in plan["unscheduled"]], topics
        )
        if plan["unscheduled"] else []
    )
    for item, talk in zip(plan["unscheduled"], loser_talks):
        why_line = talk["why_line"]
        alternative = (
            {k: v for k, v in item["alternative"].items() if k != "embedding"}
            if item.get("alternative") else None
        )
        unscheduled.append(UnscheduledItem(
            talk=talk,
            reason=item["reason"],
            clashes_with=item["clashes_with"],
            alternative=alternative,
            why_line=why_line,
        ))

    # warn unknown asks in the note (never silently dropped): topics we don't
    # cover, accommodations we cannot verify in today's room data
    notes = []
    known = set(distinct_topics())
    unknown_topics = [t for t in topics if t not in known]
    if unknown_topics:
        notes.append(f"no talks today match {', '.join(unknown_topics)} "
                     f"— showing matches for the other interests")
    unknown_needs = sorted(needs - ACCESS_TAGS)
    if unknown_needs:
        notes.append(f"accessibility request {', '.join(unknown_needs)} "
                     f"isn't one we can verify in room data; the other "
                     f"requests were applied")
    note = f"Note: {'; '.join(notes)}." if notes else None

    response = AgendaResponse(
        topics=topics,
        agenda=agenda_items,
        unscheduled=unscheduled,
        note=note,
    )
    return response.model_dump()
