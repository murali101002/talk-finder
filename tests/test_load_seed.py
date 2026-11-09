"""Sanity checks for load_seed.py — hermetic (validate_talk is pure: no ES,
no OpenAI; importing the module only load_dotenv()+imports, no connections).

Pin: the loader is the seed's validation point — the real seed must pass and
each broken talk must produce a loud one-line reason before we ever index.
"""

import json
from pathlib import Path

from load_seed import validate_talk

TALKS = json.loads(Path("seed.json").read_text())["talks"]


def test_whole_seed_validates_clean():
    assert len(TALKS) == 12
    assert all(validate_talk(talk) is None for talk in TALKS)


def test_overfull_talk_gets_a_loud_reason():
    talk = {**TALKS[0], "fill": TALKS[0]["capacity"] + 1}
    reason = validate_talk(talk)
    assert reason is not None and "more attendees than seats" in reason


def test_broken_talk_is_flagged_not_silently_indexed():
    reason = validate_talk({"id": "T99"})  # missing every required field
    assert reason is not None and "missing fields" in reason
