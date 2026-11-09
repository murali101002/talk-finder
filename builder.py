


def _minutes(time: str) -> int:
    """'HH:mm' -> minutes since midnight."""
    hours, mins = time.split(":")
    return int(hours) * 60 + int(mins)


def _overlaps(a: dict, b: dict) -> bool:
    """Half-open interval intersect on [start, end) — end==start
    back-to-back talks do NOT clash (11:00→11:40 then 11:40 is fine)."""
    return (_minutes(a["start"]) < _minutes(b["end"])
            and _minutes(b["start"]) < _minutes(a["end"]))


def is_full(talk: dict) -> bool:
    """A room is full when its fill has reached capacity."""
    return talk["fill"] >= talk["capacity"]


def match_reasons(talk: dict, interest_words: set[str]) -> list[str]:
    """Matched topic keywords for this talk, lexically matched in topic order."""
    topics = [t.lower() for t in talk["topics"]]
    return [t for t in topics if any(t in w or w in t for w in interest_words)]


def _breakdown(item: dict) -> dict:
    """The score fields explain.py's template reads, at item level."""
    return {key: item[key] for key in (
        "relevance_score", "speaker_score", "adjusted_rating",
        "is_new_speaker", "final_score") if key in item}


def build_plan(candidates: list[dict]) -> dict:
    """Split ranked candidates into agenda / unscheduled.

    Input items: scoring.rank_candidates output ({"talk": <talk dict>,
    "relevance_score": , "final_score": , ...}). Re-sorted defensively
    (final desc, relevance desc, start asc, id asc) so equal-scoring
    batches stay deterministic.

    Output: {"agenda": [<candidate items>],
             "unscheduled": [{"talk": <talk dict>, "reason": "full"|"clash",
                              "clashes_with": [<ids>], <breakdown>}, ...]}
    The `alternative` field is filled by offer_alternatives(plan) — the
    builder never invents remedies, only verdicts.
    """
    ranked = sorted(
        candidates,
        key=lambda c: (
            -float(c.get("final_score") or 0.0),
            -float(c.get("relevance_score") or 0.0),
            c["talk"]["start"],
            c["talk"]["id"],
        ),
    )

    agenda: list[dict] = []
    unscheduled: list[dict] = []
    for item in ranked:
        talk = item["talk"]
        if is_full(talk):
            # a full room is not a time clash: no clashes_with, and the
            # slot stays open for later candidates (fit-first)
            verdict = {"reason": "full", "clashes_with": []}
        elif winners := [p["talk"]["id"] for p in agenda
                         if _overlaps(p["talk"], talk)]:
            verdict = {"reason": "clash", "clashes_with": winners}
        else:
            agenda.append(item)
            continue
        unscheduled.append({"talk": talk, **verdict, **_breakdown(item)})

    agenda.sort(key=lambda pick: (_minutes(pick["talk"]["start"]),
                                  pick["talk"]["id"]))
    return {"agenda": agenda, "unscheduled": unscheduled}


def offer_alternatives(plan: dict) -> dict:
    
    for item in plan["unscheduled"]:
        in_window = [pick for pick in plan["agenda"]
                     if _overlaps(pick["talk"], item["talk"])]
        item["alternative"] = (
            max(in_window, key=lambda p: (float(p.get("final_score") or 0.0),
                                          p["talk"]["id"]))["talk"]
            if in_window else None
        )
    return plan
