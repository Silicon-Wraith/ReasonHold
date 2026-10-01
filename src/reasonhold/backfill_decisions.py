"""Backfill the decision store into Weaviate.

`store_decision` indexes one record at write time. This script indexes an
existing `decisions.jsonl` — needed after a migration, or to rebuild the
decision half of the collection without touching the document half.

Uses the same content format, UUID5 key, and property set as
`server.store_decision`, so a backfilled record is indistinguishable from a
natively stored one.

Re-runnable: existing `chunk_type == "decision"` objects are deleted before
insert. Weaviate's `insert` raises on a duplicate UUID rather than upserting,
so a delete-then-insert rebuild is what actually makes this idempotent —
and it lets a record whose status changed (active -> superseded) be picked up.
Document chunks are untouched.

    python backfill_decisions.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys

import ollama as ollama_client
import weaviate
import weaviate.classes.query as wvq
from schema import ensure_collection, get_client
from server import _format_decision_content

from config import (
    COLLECTION_NAME,
    DECISIONS_FILE,
    EMBEDDING_CHAR_BUDGET,
    EMBEDDING_MODEL,
    OLLAMA_HOST,
    OLLAMA_PORT,
)

BATCH = 16


def load_records() -> list[dict]:
    if not DECISIONS_FILE.exists():
        sys.exit(f"no decision store at {DECISIONS_FILE}")
    out = []
    with open(DECISIONS_FILE) as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as exc:
                sys.exit(f"{DECISIONS_FILE}:{n}: {exc}")
    return out


def to_object(record: dict, vector: list[float]) -> weaviate.classes.data.DataObject:
    return weaviate.classes.data.DataObject(
        properties={
            "content": _format_decision_content(record)[:EMBEDDING_CHAR_BUDGET],
            "file_path": "docs-rag/decisions.jsonl",
            "chunk_type": "decision",
            "file_type": "decisions",
            "authority_level": "decision",
            "document_kind": "decision_log",
            "section_heading": record["topic"],
            "section_path": record["topic"],
            "semantic_label": "decision_record",
            "decision_topic": record["topic"],
            "decision_status": record.get("status", "active"),
            "chunk_index": 0,
            "last_modified": record["datetime"],
        },
        vector=vector,
        uuid=weaviate.util.generate_uuid5(f"{record['topic']}|{record['datetime']}"),
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    records = load_records()
    print(f"{len(records)} decision records in {DECISIONS_FILE.name}")
    if args.dry_run:
        for r in records[:5]:
            print(f"  {r['datetime'][:10]}  {r['topic']}")
        print(f"  ... ({len(records)} total)")
        return

    oll = ollama_client.Client(host=f"http://{OLLAMA_HOST}:{OLLAMA_PORT}")
    client = get_client()
    try:
        ensure_collection(client)
        collection = client.collections.get(COLLECTION_NAME)

        removed = collection.data.delete_many(where=wvq.Filter.by_property("chunk_type").equal("decision"))
        print(f"  cleared {removed.successful} existing decision objects")

        objects, done = [], 0
        for record in records:
            content = _format_decision_content(record)[:EMBEDDING_CHAR_BUDGET]
            vector = oll.embeddings(model=EMBEDDING_MODEL, prompt=content)["embedding"]
            objects.append(to_object(record, vector))
            if len(objects) >= BATCH:
                collection.data.insert_many(objects)
                done += len(objects)
                print(f"  indexed {done}/{len(records)}")
                objects = []
        if objects:
            collection.data.insert_many(objects)
            done += len(objects)
        print(f"indexed {done} decision records into {COLLECTION_NAME}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
