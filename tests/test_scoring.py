"""Basic tests for scoring.py — pure dict-in/dict-out pins, fully hermetic:
batch-max normalization, new-speaker-neutrality, deterministic tie-breaks.
"""

import pytest

from scoring import compute_speaker_score, rank_candidates


def test_batch_max_normalization_makes_relevance_dominant():
    """Relevance is normalized by the batch max, and that channel carries
    3x the weight of the speaker channel — so a 2x relevance gap wins."""
    cands = [
        {"talk": {"id": "A", "start": "11:00"}, "relevance": 20.0},
        {"talk": {"id": "B", "start": "11:00"}, "relevance": 10.0},
    ]
    ranked = rank_candidates(cands)
    top, other = ranked[0], ranked[1]
    assert top["relevance_score"] / other["relevance_score"] == 2.0
    # both talks have zero-evidence speakers => identical speaker halves,
    # so the final-score gap is pure relevance: 0.75 * (1.0 - 0.5)
    assert top["final_score"] - other["final_score"] == pytest.approx(0.375)


def test_none_relevance_is_treated_as_zero():
    ranked = rank_candidates(
        [{"talk": {"id": "A", "start": "11:00"}, "relevance": None}]
    )
    assert ranked[0]["relevance_score"] == 0.0


def test_score_key_is_accepted_as_relevance_alias():
    cands = [
        {"talk": {"id": "A", "start": "11:00"}, "score": 20.0},
        {"talk": {"id": "B", "start": "12:00"}, "score": 10.0},
    ]

    ranked = rank_candidates(cands)

    assert [candidate["relevance_score"] for candidate in ranked] == [20.0, 10.0]


def test_new_speaker_scores_as_average_not_zero():
    """rating_count == 0 => adjusted rating is the prior (4.0) and the
    DEFAULT_FILL_RATE applies — new reads as average, never last."""
    speaker_score, adjusted = compute_speaker_score({"speaker_rating_count": 0})
    assert adjusted == 4.0
    assert speaker_score > 0.0  # exactly 0.6*4/5 + 0.4*0.5 = 0.68


def test_ties_rank_deterministically_by_start():
    """Same relevance, same speaker evidence => same final_score; the
    documented tie-break orders by start asc. Repeat = identical result."""
    talk = lambda tid, start: {"talk": {"id": tid, "start": start},
                               "relevance": 5.0}
    batch = [talk("late", "12:00"), talk("early", "10:00"), talk("mid", "11:00")]
    ranked = rank_candidates(batch)
    assert [c["talk"]["id"] for c in ranked] == ["early", "mid", "late"]
    assert ranked == rank_candidates(batch)
