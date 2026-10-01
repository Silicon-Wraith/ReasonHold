"""The pending sidecar (spec 3.3): agents' proposals, reported conflicts,
resolutions and mechanical-curation history. Append-only; humans never edit it."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

KINDS = ("candidate_binding", "conflict", "resolution", "path_alias", "curation")
OPEN_KINDS = ("candidate_binding", "conflict")
OUTCOMES = ("promoted", "rejected", "resolved")
_ENVELOPE = ("id", "kind", "datetime", "provenance")


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def pending_id(kind: str, datetime_: str, payload: dict) -> str:
    return "pen-" + hashlib.sha256(f"{kind}|{datetime_}|{_canonical(payload)}".encode()).hexdigest()[:12]


def make_record(kind: str, payload: dict, provenance: dict, *, datetime_: str | None = None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"unknown pending kind {kind!r}")
    when = datetime_ or datetime.now(UTC).isoformat()
    return {"id": pending_id(kind, when, payload), "kind": kind, "datetime": when, "provenance": provenance, **payload}


def follow_alias(path: str, aliases: Mapping[str, str]) -> str:
    seen = {path}
    while path in aliases:
        path = aliases[path]
        if path in seen:
            break
        seen.add(path)
    return path


class PendingLog:
    def __init__(self, records: Sequence[dict]):
        self.records = [r for r in records if isinstance(r, dict) and r.get("kind") in KINDS and r.get("id")]
        self._by_id = {r["id"]: r for r in self.records}
        self._resolution: dict[str, dict] = {}
        for r in self.records:
            if r["kind"] == "resolution":
                for target in r.get("resolves") or []:
                    self._resolution.setdefault(target, r)

    @classmethod
    def load(cls, path: Path) -> "PendingLog":
        return cls.from_text(path.read_text()) if path.exists() else cls([])

    @classmethod
    def from_text(cls, text: str) -> "PendingLog":
        records = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return cls(records)

    def get(self, id: str) -> dict | None:
        return self._by_id.get(id)

    def resolved_ids(self) -> set[str]:
        return set(self._resolution)

    def is_open(self, id: str) -> bool:
        record = self._by_id.get(id)
        return record is not None and record["kind"] in OPEN_KINDS and id not in self._resolution

    def open(self, kind: str | None = None) -> list[dict]:
        return [r for r in self.records if self.is_open(r["id"]) and (kind is None or r["kind"] == kind)]

    def resolution_for(self, id: str) -> dict | None:
        return self._resolution.get(id)

    def aliases(self) -> dict[str, str]:
        return {r["old_path"]: r["new_path"] for r in self.records if r["kind"] == "path_alias"}

    def former_names(self, path: str) -> set[str]:
        aliases = self.aliases()
        names = {path}
        for old in aliases:
            if follow_alias(old, aliases) == path:
                names.add(old)
        return names
