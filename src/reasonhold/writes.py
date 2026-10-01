"""Append-only writes (spec section 5, Writes). Validate, embed, append, index."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

import weaviate

from reasonhold.decisions import (
    DecisionLog,
    decision_id,
    format_decision_content,
    validate_provenance,
    validate_supersedes,
)
from reasonhold.errors import UnknownRecord
from reasonhold.jsonl import append_jsonl


def apply_retraction_to_chunks(collection, path, retraction_summary, retraction_decision, retraction_date) -> int:
    """Seed server.apply_retraction_to_chunks, taking the collection instead of a client."""
    if "#" in path:
        file_path, _, anchor = path.partition("#")
        anchor_lower = anchor.strip().lower()
    else:
        file_path, anchor_lower = path, None
    updated = 0
    for obj in collection.iterator(include_vector=False):
        props = obj.properties or {}
        if props.get("file_path") != file_path or props.get("chunk_type") == "decision":
            continue
        if anchor_lower is not None:
            heading = (props.get("section_heading") or "").strip().lower()
            if not heading or anchor_lower not in heading:
                continue
        collection.data.update(
            uuid=obj.uuid,
            properties={
                "retraction_summary": retraction_summary,
                "retraction_decision": retraction_decision,
                "retraction_date": retraction_date,
            },
        )
        updated += 1
    return updated


def mark_records_superseded(collection, record_ids: Iterable[str]) -> int:
    wanted = set(record_ids)
    updated = 0
    for obj in collection.iterator(include_vector=False):
        props = obj.properties or {}
        if props.get("chunk_type") == "decision" and props.get("record_id") in wanted:
            collection.data.update(uuid=obj.uuid, properties={"decision_status": "superseded"})
            updated += 1
    return updated


def _required_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def store_decision(
    project,
    collection,
    provider,
    *,
    topic,
    decision,
    rationale,
    alternatives_considered=None,
    session_context="",
    tags=None,
    status="active",
    supersedes=None,
    supersedes_records=None,
    provenance,
    datetime_=None,
) -> dict:
    # 1. Validate. Nothing is written or embedded on a validation failure.
    topic = _required_text("topic", topic)
    decision = _required_text("decision", decision)
    rationale = _required_text("rationale", rationale)
    if status not in ("active", "superseded"):
        raise ValueError("status must be 'active' or 'superseded'")
    supersedes_list = validate_supersedes(supersedes)
    clean_provenance = validate_provenance(provenance)
    log = DecisionLog.load(project.decisions_path)
    retired = list(dict.fromkeys(supersedes_records or []))
    for rid in retired:
        if log.get(rid) is None:
            raise UnknownRecord(f"supersedes_records names {rid}, which is not in {project.decisions_rel}")

    when = datetime_ or datetime.now(UTC).isoformat()
    rid = decision_id(topic, when)
    existing = log.get(rid)
    if existing is not None:
        return {"record": existing, "status": log.status(rid), "indexed": True, "annotated_chunks": 0,
                "warnings": ["already recorded"]}

    record = {
        "id": rid,
        "topic": topic,
        "decision": decision,
        "rationale": rationale,
        "alternatives_considered": list(alternatives_considered or []),
        "datetime": when,
        "session_context": session_context,
        "tags": list(tags or []),
        "status": status,
        "supersedes": supersedes_list,
        "supersedes_records": retired,
        "provenance": clean_provenance,
    }

    # 2. Embed. An unreachable embedding service raises StoreUnavailable here,
    #    before the append, so a retry cannot produce a duplicate (seed bug fixed).
    content = format_decision_content(record)
    vector = provider.embed([content])[0]

    # 3. Append. From here on the record is durable.
    append_jsonl(project.decisions_path, record)

    # 4. Index. Failures are warnings: the next `reasonhold index` catches up.
    result = {"record": record, "status": status, "indexed": False, "annotated_chunks": 0, "warnings": []}
    if collection is None:
        result["warnings"].append("no index for this branch: recorded in the log only; run `reasonhold index`")
        return result
    try:
        collection.data.insert(
            properties={
                "content": content,
                "file_path": project.decisions_rel,
                "chunk_type": "decision",
                "file_type": "decisions",
                "authority_level": "decision",
                "document_kind": "decision_log",
                "section_heading": topic,
                "section_path": topic,
                "semantic_label": "decision_record",
                "decision_topic": topic,
                "decision_status": status,
                "record_id": rid,
                "chunk_index": 0,
                "last_modified": when,
            },
            vector=vector,
            uuid=weaviate.util.generate_uuid5(f"{topic}|{when}"),
        )
        annotated = 0
        if status == "active":
            for entry in supersedes_list:
                annotated += apply_retraction_to_chunks(collection, entry["path"], entry["retraction_summary"], topic, when)
            mark_records_superseded(collection, retired)
        result.update(indexed=True, annotated_chunks=annotated)
    except Exception as exc:  # the store client raises many unrelated types
        result["warnings"].append(f"recorded in the log but not indexed ({exc}); run `reasonhold index`")
    return result
