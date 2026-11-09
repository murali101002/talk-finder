

import json
import os
import sys

from dotenv import load_dotenv
from elasticsearch import Elasticsearch, helpers

load_dotenv()

INDEX = "talks"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"

REQUIRED_FIELDS = ["id", "title", "topics", "start", "end", "capacity", "fill"]


def validate_talk(talk: dict) -> str | None:
    """Return a one-line reason string if this talk is not loadable, else None."""
    missing = [f for f in REQUIRED_FIELDS if f not in talk]
    if missing:
        return f"missing fields {missing}"
    if not isinstance(talk["id"], str) or not talk["id"].strip():
        return "id must be a non-empty string"
    if not isinstance(talk["title"], str) or not talk["title"].strip():
        return "title must be a non-empty string"
    topics = talk["topics"]
    if not isinstance(topics, list) or not topics or \
            not all(isinstance(t, str) and t.strip() for t in topics):
        return "topics must be a non-empty list of strings"
    for field in ("start", "end"):
        value = talk[field]
        parts = value.split(":") if isinstance(value, str) else []
        if len(parts) != 2 or not all(p.isdigit() and len(p) == 2 for p in parts) \
                or int(parts[0]) > 23 or int(parts[1]) > 59:
            return f"{field} must be a HH:mm string, got {value!r}"
    capacity, fill = talk["capacity"], talk["fill"]
    if not isinstance(capacity, int) or capacity < 1:
        return f"capacity must be an int >= 1, got {capacity!r}"
    if not isinstance(fill, int) or fill < 0:
        return f"fill must be an int >= 0, got {fill!r}"
    if fill > capacity:
        return f"fill {fill} > capacity {capacity} — more attendees than seats"
    return None


def embed_talk_texts(texts: list[str], api_key: str, model: str) -> list[list[float]]:
    """One OpenAI embeddings call; returns the vectors, all same length."""
    from openai import OpenAI

    resp = OpenAI(api_key=api_key).embeddings.create(model=model, input=texts)
    vectors = [[float(x) for x in item.embedding] for item in resp.data]
    lengths = {len(v) for v in vectors}
    if len(lengths) != 1:
        sys.exit(
            f"Embedding validation failed: vector lengths differ ({lengths}). "
            "Refusing to index a mixed-dimension corpus."
        )
    return vectors


def main():
    es = Elasticsearch(os.getenv("ES_URL", "http://localhost:9200"))

    with open("seed.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    talks = data["talks"] if isinstance(data, dict) else data  # _note ignored
    print(f"Loaded {len(talks)} talks from seed.json")

    for talk in talks:  # validate with explicit checks; fail loudly, per talk
        if (reason := validate_talk(talk)) is not None:
            sys.exit(f"Seed validation failed for {talk.get('id', '?')}: {reason}")

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("OPENAI_API_KEY is not set — put it in .env and retry.")
    model = os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)

    texts = [f"{t['title']} {t['abstract']} {' '.join(t['topics'])}" for t in talks]
    vectors = embed_talk_texts(texts, api_key, model)
    embedding_dims = len(vectors[0])
    print(
        f"Embedded {len(talks)} talks with {model}; "
        f"EMBEDDING_DIMS measured as {embedding_dims}"
    )

    expected_dims = os.getenv("EMBEDDING_DIMS", "").strip()
    if expected_dims and int(expected_dims) != embedding_dims:
        sys.exit(
            f"EMBEDDING_DIMS check failed: env says {expected_dims}, "
            f"model measured {embedding_dims}."
        )

    for talk, vec in zip(talks, vectors):
        talk["embedding"] = vec

    mapping = {
        "properties": {
            "id": {"type": "keyword"},
            "title": {"type": "text"},
            "abstract": {"type": "text"},
            "speaker": {"type": "text"},
            "speaker_past_rating": {"type": "float"},
            "speaker_rating_count": {"type": "integer"},
            "speaker_past_fill_rate": {"type": "float"},
            "topics": {"type": "keyword"},
            "track": {"type": "keyword"},
            "day": {"type": "integer"},
            "start": {"type": "date", "format": "HH:mm"},
            "end": {"type": "date", "format": "HH:mm"},
            "room": {"type": "keyword"},
            "capacity": {"type": "integer"},
            "fill": {"type": "integer"},
            "status": {"type": "keyword"},
            "step_free": {"type": "boolean"},
            "wheelchair_spaces": {"type": "integer"},
            "accessible_seats": {"type": "integer"},
            "hearing_loop": {"type": "boolean"},
            "captions": {"type": "boolean"},
            "sign_language": {"type": "boolean"},
            "access_note": {"type": "text"},
            "embedding": {
                "type": "dense_vector",
                "dims": embedding_dims,  # measured from the model output
                "index": True,
                "similarity": "cosine",
            },
        }
    }

    if es.indices.exists(index=INDEX):
        print(f"Index '{INDEX}' exists — deleting (old schema, old vectors).")
        es.indices.delete(index=INDEX)
    es.indices.create(index=INDEX, mappings=mapping)

    actions = (
        {"_index": INDEX, "_id": talk["id"], "_source": talk} for talk in talks
    )
    success, _ = helpers.bulk(es, actions)
    es.indices.refresh(index=INDEX)
    print(f"Indexed {success} talks into '{INDEX}' ({model}, dims {embedding_dims}).")


if __name__ == "__main__":
    main()
