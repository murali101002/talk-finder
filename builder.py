

def _minutes(time: str) -> int:
    """'HH:mm' -> minutes since midnight (no date library, see module head)."""
    hours, mins = time.split(":")
    return int(hours) * 60 + int(mins)


def _overlaps(talk1: dict, talk2: dict) -> bool:
    """Half-open interval intersect on [start, end) — end==start back-to-back
    talks do NOT clash (11:00→11:40 then 11:40 is fine)."""
    t1_start = _minutes(talk1["start"])
    t2_start = _minutes(talk2["start"])
    return t1_start < _minutes(talk2["end"]) and t2_start < _minutes(talk1["end"])


def is_full(talk: dict) -> bool:
    """A room is full when its fill has reached capacity."""
    return talk["fill"] >= talk["capacity"]


def match_reasons(talk: dict, interest_words: set[str]) -> list[str]:
    """Matched topic keywords for this talk, lexically matched in topic order."""
    words = {w.lower().strip() for w in interest_words if w and w.strip()}
    topics = [t.lower() for t in talk["topics"]]
    return [t for t in topics if t in words or set(t.split()) & words]


def build_plan(candidates: list[dict]) -> dict:
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
            # a full room is not a time clash: skips with no clashes_with,
            # and the slot stays open for later candidates (fit-first)
            unscheduled.append({
                "talk": talk,
                "reason": "full",
                "clashes_with": [],
            })
            continue
        winners = [pick["talk"]["id"] for pick in agenda if _overlaps(pick["talk"], talk)]
        if winners:
            unscheduled.append({
                "talk": talk,
                "reason": "clash",
                "clashes_with": winners,
            })
        else:
            agenda.append(item)

    agenda.sort(key=lambda pick: (_minutes(pick["talk"]["start"]),
                                  pick["talk"]["id"]))
    return {"agenda": agenda, "unscheduled": unscheduled}


def offer_alternatives(plan: dict) -> dict:
    for item in plan["unscheduled"]:
        in_window = [
            pick
            for pick in plan["agenda"]
            if _overlaps(pick["talk"], item["talk"])
        ]
        item["alternative"] = (
            max(in_window, key=lambda p: (float(p.get("final_score") or 0.0),
                                          p["talk"]["id"]))["talk"]
            if in_window
            else None
        )
    return plan
