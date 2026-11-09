"""Basic tests for builder.py — pure dict pins, fully hermetic: fit-first
walk, half-open interval clash rule, honest alternatives from the agenda.

The builder's unscheduled items carry the score breakdown at item level
(the same evidence explain.py reads for agenda picks), so verdict asserts
use subsets rather than whole-dict equality.
"""

from builder import build_plan, offer_alternatives

PICK_KEYS = {"talk", "reason", "clashes_with"}


def _talk(tid: str, start: str, end: str, *, capacity=100, fill=50,
          final=10.0, topics=None) -> dict:
    return {"talk": {"id": tid, "start": start, "end": end, "title": tid,
                     "topics": topics or [], "capacity": capacity, "fill": fill},
            "relevance_score": final, "final_score": final}


def test_full_room_skips_with_open_slot_and_empty_clashes():
    """A full pick must not occupy its slot: a lower-ranked non-full talk in
    the SAME window still lands in the agenda, and the loser says so honestly
    (reason 'full', clashes_with empty — a full room is not a time clash)."""
    full = _talk("T99", "11:00", "11:40", capacity=50, fill=50, final=20.0)
    open_slot = _talk("T10", "11:00", "11:40", final=5.0)
    plan = offer_alternatives(build_plan([full, open_slot]))
    assert [p["talk"]["id"] for p in plan["agenda"]] == ["T10"]
    [loser] = plan["unscheduled"]
    assert loser["talk"] is full["talk"]
    assert loser["reason"] == "full" and loser["clashes_with"] == []
    assert loser["alternative"] == open_slot["talk"]


def test_back_to_back_talks_do_not_clash_but_overlaps_do():
    """[start,end) is half-open: end == next start is fine; intersecting
    windows lose to the higher-ranked pick in the walk order."""
    ok = [_talk("E1", "11:00", "11:40", final=8.0),
          _talk("E2", "11:40", "12:20", final=7.0)]
    assert build_plan(ok)["unscheduled"] == []
    assert [p["talk"]["id"] for p in build_plan(ok)["agenda"]] == ["E1", "E2"]
    clashy = [_talk("C1", "11:00", "11:40", final=8.0),
              _talk("C2", "11:20", "12:00", final=7.0)]
    plan = build_plan(clashy)
    assert [p["talk"]["id"] for p in plan["agenda"]] == ["C1"]
    [loser] = plan["unscheduled"]
    assert {k: loser[k] for k in PICK_KEYS} == {
        "talk": clashy[1]["talk"], "reason": "clash", "clashes_with": ["C1"]}
    assert loser["final_score"] == 7.0  # breakdown rides at item level


def test_alternatives_form_from_agenda_or_honest_none():
    """A loser gets the agenda pick playing in its own window; a full pick
    at a time the agenda doesn't cover gets a truthful None, never a
    fabricated swap."""
    plan = offer_alternatives(build_plan([
        _talk("W1", "11:00", "11:40", final=15.0),                # agenda 11:00
        _talk("L1", "11:10", "11:30", final=10.0),                # clash: alt W1
        _talk("L2", "14:00", "14:40", capacity=10, fill=10,
              final=5.0),                                          # full, empty slot: None
    ]))
    by_id = {u["talk"]["id"]: u for u in plan["unscheduled"]}
    assert by_id["L1"]["alternative"]["id"] == "W1"
    assert by_id["L2"]["alternative"] is None
