"""Scoring for /agenda — pure functions, no I/O, no speaker names in code.

All decisions are made from generic talk fields:
  relevance    — comes from Elasticsearch (BM25 + knn _score), passed in
  speaker      — derived from seed fields: past_rating, rating_count,
                 past_fill_rate (Bayesian shrinkage toward the prior below)
Everything is deterministic so the pytest suite can prove it without
network, models, or API keys.
"""

PRIOR_RATING = 4.0          # prior belief for unknown speakers
PRIOR_COUNT = 20            # strength of that prior (pseudo-ratings)

SPEAKER_RATING_WEIGHT = 0.6  # rating share of the speaker score
SPEAKER_FILL_WEIGHT = 0.4    # historical fill-rate share of the speaker score

RELEVANCE_WEIGHT = 0.75      # relevance dominates the final score
SPEAKER_WEIGHT = 0.25        # speaker is a tie-breaker between near-equals

DEFAULT_FILL_RATE = 0.5      # a brand-new speaker is treated as average


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def compute_speaker_score(talk: dict) -> tuple[float, float]:
    
    rating_count = int(talk.get("speaker_rating_count") or 0)
    if rating_count == 0:
        adjusted_rating = PRIOR_RATING
        fill_rate = DEFAULT_FILL_RATE
    else:
        past_rating = float(talk.get("speaker_past_rating") or 0.0)
        adjusted_rating = (
            past_rating * rating_count + PRIOR_COUNT * PRIOR_RATING
        ) / (rating_count + PRIOR_COUNT)
        fill_rate = float(talk.get("speaker_past_fill_rate") or 0.0)

    speaker_score = (
        SPEAKER_RATING_WEIGHT * (adjusted_rating / 5.0)
        + SPEAKER_FILL_WEIGHT * fill_rate
    )
    return _clamp(speaker_score), adjusted_rating


def is_new_speaker(talk: dict) -> bool:
    return int(talk.get("speaker_rating_count") or 0) == 0


def compute_final_score(
    relevance_score: float, speaker_score: float, max_relevance: float
) -> float:
    """final = RELEVANCE_WEIGHT * normalized_relevance + SPEAKER_WEIGHT * speaker.

    max_relevance normalizes the raw ES score across this batch. A great
    speaker on the wrong topic stays below a good speaker on the user's
    topic, because relevance carries 3x the weight.
    """
    relevance_normalized = (
        _clamp(relevance_score / max_relevance) if max_relevance > 0 else 0.0
    )
    return _clamp(
        RELEVANCE_WEIGHT * relevance_normalized + SPEAKER_WEIGHT * speaker_score
    )


def rank_candidates(candidates: list[dict]) -> list[dict]:
    """Sort candidates by final_score desc, relevance_normalized desc, start asc.

    Input items: {"talk": <source dict>, "relevance": <raw ES score>}.
    Output items carry every breakdown field the API needs to show:
    relevance_score, speaker_score, final_score, adjusted_rating,
    is_new_speaker — so the why-line is never a single bare total.
    """
    max_relevance = max((float(c.get("relevance") or 0.0) for c in candidates), default=0.0)
    ranked = []
    for candidate in candidates:
        talk = candidate["talk"]
        relevance = float(candidate.get("relevance") or 0.0)
        speaker_score, adjusted_rating = compute_speaker_score(talk)
        relevance_normalized = (
            _clamp(relevance / max_relevance) if max_relevance > 0 else 0.0
        )
        final_score = compute_final_score(relevance, speaker_score, max_relevance)
        ranked.append(
            {
                **candidate,
                "relevance_score": relevance,
                "speaker_score": speaker_score,
                "adjusted_rating": adjusted_rating,
                "is_new_speaker": is_new_speaker(talk),
                "final_score": final_score,
                "_relevance_normalized": relevance_normalized,
            }
        )
    ranked.sort(
        key=lambda c: (
            -c["final_score"],
            -c["_relevance_normalized"],
            c["talk"]["start"],
        )
    )
    for c in ranked:
        del c["_relevance_normalized"]
    return ranked
