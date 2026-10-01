"""Read the decision log. No heavy dependencies, by design.

Extracted from index.py so that reading decisions.jsonl does not drag in ollama,
weaviate and the chunkers. Two reasons, and the second matters more.

Cost: those imports were 0.49s of bootstrap.py's 0.54s import time, paid on every
session start for a module that only reads a text file.

Fragility: the SessionStart preamble must fail open. Depending on the whole
indexing stack to parse JSONL means a broken weaviate client kills the preamble —
which is precisely the section that warns a session it is about to read retracted
documentation. The part that must survive should depend on the least.

index.py re-exports the readers, so existing callers are unaffected.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path


def iter_decision_records(decisions_path: Path) -> Iterator[dict]:
    """Yield every well-formed record in the decision log, in file order.

    The single place decisions.jsonl is parsed. Two consumers need different
    questions answered — which retractions are active, and which decisions look
    like retractions but record none — and both read through here so there is one
    definition of a well-formed record.

    A malformed line is skipped, not fatal. A decision log that fails to parse
    must not take down indexing or a session start.
    """
    if not decisions_path.exists():
        return
    with open(decisions_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


PROVENANCE_KINDS = ("human", "agent", "sendesis_run")
_PROVENANCE_FIELDS = ("actor", "run_id", "role")


def decision_id(topic: str, datetime_: str) -> str:
    return "dec-" + hashlib.sha256(f"{topic}|{datetime_}".encode()).hexdigest()[:12]


def record_id(record: dict) -> str:
    explicit = record.get("id")
    if isinstance(explicit, str) and explicit:
        return explicit
    return decision_id(str(record.get("topic", "")), str(record.get("datetime", "")))


@dataclass(frozen=True)
class Retraction:
    path: str
    retraction_summary: str
    decision_id: str
    topic: str
    date: str

    @property
    def file_path(self) -> str:
        return self.path.partition("#")[0]

    @property
    def section(self) -> str | None:
        return self.path.partition("#")[2] or None


class DecisionLog:
    """The decision log with ids filled in and status computed (spec 3.2)."""

    def __init__(self, records: Sequence[dict]):
        self.records = [{**r, "id": record_id(r)} for r in records]
        self._by_id = {r["id"]: r for r in self.records}
        self._superseded_by: dict[str, list[str]] = {}
        for r in self.records:
            if r.get("status", "active") != "active":
                continue
            for target in r.get("supersedes_records") or []:
                if isinstance(target, str):
                    self._superseded_by.setdefault(target, []).append(r["id"])

    @classmethod
    def load(cls, path: Path) -> "DecisionLog":
        return cls(list(iter_decision_records(path)))

    @classmethod
    def from_text(cls, text: str) -> "DecisionLog":
        records = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(value)
        return cls(records)

    def get(self, id: str) -> dict | None:
        return self._by_id.get(id)

    def status(self, id: str) -> str:
        record = self._by_id.get(id)
        if record is None:
            return "unknown"
        if record.get("status", "active") != "active" or id in self._superseded_by:
            return "superseded"
        return "active"

    def superseded_by(self, id: str) -> list[str]:
        return list(self._superseded_by.get(id, []))

    def active(self) -> list[dict]:
        return [r for r in self.records if self.status(r["id"]) == "active"]

    def retractions(self) -> list[Retraction]:
        out: list[Retraction] = []
        for r in self.active():
            entries = r.get("supersedes")
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                path, summary = entry.get("path"), entry.get("retraction_summary")
                if path and summary:
                    out.append(Retraction(path, summary, r["id"], str(r.get("topic", "")), str(r.get("datetime", ""))))
        return out

    def retraction_sha256(self) -> str:
        payload = {
            "retractions": [[r.path, r.retraction_summary, r.decision_id] for r in self.retractions()],
            "superseded": sorted(self._superseded_by),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def iter_supersedes_rows(decisions_path: Path) -> Iterator[tuple[str, str, str, str]]:
    """Yield (date, topic, path, retraction_summary) for every active retraction.

    Same shape as the seed; "active" is now the computed status, so a decision
    retired through supersedes_records stops retracting."""
    for r in DecisionLog.load(decisions_path).retractions():
        yield r.date, r.topic, r.path, r.retraction_summary


def validate_provenance(provenance: dict | None) -> dict:
    if not isinstance(provenance, dict) or provenance.get("kind") not in PROVENANCE_KINDS:
        raise ValueError(f"provenance.kind must be one of {', '.join(PROVENANCE_KINDS)}")
    clean = {"kind": provenance["kind"]}
    for key in _PROVENANCE_FIELDS:
        value = provenance.get(key)
        if value is not None:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"provenance.{key} must be a non-empty string")
            clean[key] = value.strip()
    return clean


def validate_supersedes(supersedes: list[dict] | None) -> list[dict]:
    """Validate the supersedes list. Returns a normalized list.

    Each entry must be a dict with non-empty "path" (str) and
    "retraction_summary" (str). Raises ValueError on malformed input.
    """
    if not supersedes:
        return []
    validated: list[dict] = []
    for i, entry in enumerate(supersedes):
        if not isinstance(entry, dict):
            raise ValueError(f"supersedes[{i}] must be a dict, got {type(entry).__name__}")
        path = entry.get("path")
        summary = entry.get("retraction_summary")
        if not isinstance(path, str) or not path.strip():
            raise ValueError(f"supersedes[{i}].path must be a non-empty string")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError(f"supersedes[{i}].retraction_summary must be a non-empty string")
        validated.append({"path": path.strip(), "retraction_summary": summary.strip()})
    return validated


def format_decision_content(record: dict, status: str | None = None) -> str:
    """Format a decision record into searchable text content."""
    alternatives = record.get("alternatives_considered", [])
    alt_str = ", ".join(alternatives) if alternatives else "none"
    supersedes = record.get("supersedes", []) or []

    lines = [
        f"Decision: {record.get('decision', '')}",
        f"Topic: {record.get('topic', '')}",
        f"Rationale: {record.get('rationale', '')}",
        f"Alternatives considered: {alt_str}",
        f"Context: {record.get('session_context', '')}",
        f"Date: {record.get('datetime', '')}",
        f"Status: {status or record.get('status', 'active')}",
    ]
    if supersedes:
        lines.append("Supersedes:")
        for entry in supersedes:
            lines.append(f"  - {entry.get('path', '')}: {entry.get('retraction_summary', '')}")
    if record.get("id"):
        lines.append(f"Id: {record['id']}")
    return "\n".join(lines)
