"""Step 3 — the words on the why-line.

Two sources, tried in order:
  1. the LLM (OpenAI — OPENAI_API_KEY from .env ONLY, no keys in code;
     model from EXPLAIN_MODEL, default gpt-4o-mini): one short,
     user-friendly line per pick. The LLM never sees or emits the score
     numbers — they live behind the UI's "show scores" toggle.
  2. a template fallback with the same rules, used when the key is
     absent, the call fails, or the reply is unusable — the demo never
     shows a number-only line again.

Honesty constraints for both sources:
  - the full-room sentence stays whenever fill >= capacity ("...is full,
    an alternative follows");
  - the speaker's standing is qualitative, never a fabricated figure
    (the numbers themselves are real, on the wire, behind the toggle);
  - one call per /agenda request, never one per talk.
"""

import json
import logging
import os

logger = logging.getLogger("talkfinder.explain")

MAX_WHY_CHARS = 180


def _and_join(words: list[str]) -> str:
    if not words:
        return ""
    if len(words) == 1:
        return words[0]
    return f"{', '.join(words[:-1])} and {words[-1]}"


def _strength_phrase(pick: dict) -> str:
    """Qualitative only — the underlying numbers stay behind the toggle."""
    if pick["is_new_speaker"]:
        return "New speaker, ranked on track record rather than zeroed."
    adjusted = pick["adjusted_rating"]
    if adjusted >= 4.5:
        return "Well-reviewed speaker."
    if adjusted >= 4.0:
        return "Solid speaker history."
    return "Modest speaker history so far."


def fallback_why(pick: dict, matched: list[str], topics_given: bool) -> str:
    """The number-free template why-line (also the LLM-failure fallback)."""
    parts = []
    if topics_given:
        if matched:
            parts.append(f"Matches {_and_join(matched)}.")
        else:
            parts.append("Near your interests rather than an exact match.")
    else:
        parts.append("Part of the full schedule, ranked by pick quality.")
    parts.append(_strength_phrase(pick))
    if pick["fill"] >= pick["capacity"]:
        parts.append(f"{pick['room']} is full, so an alternative follows.")
    return " ".join(parts)


def _pitch(picks: list[dict], topics: list[str]) -> list[dict]:
    """The per-pick facts the LLM may use — no scores, ever."""
    topic_set = {t.lower().strip() for t in topics}
    return [
        {
            "id": pick["id"],
            "title": pick["title"],
            "speaker": pick["speaker"],
            "track": pick["track"],
            "start": pick["start"],
            "room": pick["room"],
            "matches": [t for t in pick.get("topics", []) if t in topic_set],
            "full": pick["fill"] >= pick["capacity"],
            "new_speaker": pick["is_new_speaker"],
        }
        for pick in picks
    ]


def _parse_json(content: str) -> dict | None:
    """Tolerant JSON read for model replies: json_object mode should make
    the content pure JSON, but if a model still wraps or prefixes it,
    pull out the outermost {...} block before giving up."""
    try:
        return json.loads(content)
    except ValueError:
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(content[start:end + 1])
            except ValueError:
                return None
        return None


def _clean(facts, reply_ids: set[str]) -> dict[str, str]:
    lines: dict[str, str] = {}
    for item in facts.get("lines", []) if isinstance(facts, dict) else []:
        pick_id = str(item.get("id", "")).strip()
        why = str(item.get("why", "")).strip()
        if pick_id in reply_ids and why:
            lines[pick_id] = why[:MAX_WHY_CHARS]
    return lines


def llm_why_lines(picks: list[dict], topics: list[str]) -> dict[str, str] | None:
    """One chat call for the whole batch, strict JSON out.

    Returns {talk_id: why_line}, or None on any failure (key absent,
    network, non-JSON, unusable reply) — callers keep the template then.
    The LLM's adjectives only: it never reorders, adds or drops talks.
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    model = os.getenv("EXPLAIN_MODEL", "gpt-4o-mini")
    facts = _pitch(picks, topics)
    system = (
        "Write one user-friendly why-pick line per talk for a conference "
        "attendee scanning an agenda. Plain words, energetic but precise, "
        "at most 18 words each. Never mention scores, percentages, ratings "
        "or numbers. When 'full' is true, say the room is full and an "
        "alternative follows. When 'new_speaker' is true, say it is their "
        "first talk here and they were ranked fairly. Reply with ONLY "
        'compact JSON of the shape {"lines": [{"id": "...", "why": "..."}]} '
        "and an entry for every id."
    )
    try:
        from openai import OpenAI

        resp = OpenAI(api_key=api_key).chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(facts)},
            ],
            response_format={"type": "json_object"},  # bytes in, JSON out
            temperature=0.4,
            timeout=15,
        )
        content = resp.choices[0].message.content or ""
        parsed = _clean(_parse_json(content), {pick["id"] for pick in picks})
        logger.info("LLM why-lines (%s): %d/%d returned (%s)", model, len(parsed), len(picks),
                    "; ".join(f"{pid}: {why}" for pid, why in parsed.items()) or "nothing usable")
        return parsed
    except Exception as err:  # noqa: BLE001 — fallback must never crash the demo
        logger.warning("LLM why-lines unavailable (%s); using templates.", err)
        return None


def attach_lines(picks: list[dict], topics: list[str]) -> list[dict]:
    """Fill why_line on every pick: LLM where usable, template elsewhere.

    router-level helper so the endpoint stays a straight line.
    """
    llm = llm_why_lines(picks, topics) or {}
    topics_given = bool([t for t in topics if t.strip()])
    for pick in picks:
        matched = [t for t in pick.get("topics", []) if t in {x.lower().strip() for x in topics}]
        template = fallback_why(pick, matched, topics_given)
        llm_line = llm.get(pick["id"], "")
        # a full room must always say so — template wins if the LLM dropped it
        if pick["fill"] >= pick["capacity"] and "full" not in llm_line.lower():
            pick["why_line"] = template
        else:
            pick["why_line"] = llm_line or template
    return picks
