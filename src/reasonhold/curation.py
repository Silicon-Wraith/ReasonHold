"""Mechanical manifest curation (spec 6.1) and the human-only promote/reject (6.2).
Edits use a comment-preserving YAML round trip and land uncommitted."""

from __future__ import annotations

import io
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ruamel.yaml import YAML

from reasonhold.decisions import DecisionLog
from reasonhold.errors import ManifestInvalid, UnknownRecord
from reasonhold.identity import git
from reasonhold.jsonl import append_jsonl
from reasonhold.pending import PendingLog, make_record

CURATION_PROVENANCE = {"kind": "agent", "actor": "reasonhold-curate"}


@dataclass
class CurationEdit:
    cause: str
    old_path: str
    new_path: str | None
    locations: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)

    def describe(self) -> str:
        if self.cause == "rename":
            return f"{self.old_path} -> {self.new_path} in {', '.join(self.locations)}"
        removed = f"removed {self.old_path} from {', '.join(self.locations)}" if self.locations else ""
        kept = f"kept {self.old_path} in {', '.join(self.kept)} (last entry)" if self.kept else ""
        return "; ".join(x for x in (removed, kept) if x)


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    return y


def _lists(data) -> Iterator[tuple[str, list]]:
    g = data.get("global") or {}
    for key in ("docs", "archival", "index"):
        if isinstance(g.get(key), list):
            yield f"global.{key}", g[key]
    for name, area in (data.get("areas") or {}).items():
        for key in ("docs", "index"):
            if isinstance(area, dict) and isinstance(area.get(key), list):
                yield f"areas.{name}.{key}", area[key]
    for name, check in (data.get("checks") or {}).items():
        if isinstance(check, dict) and isinstance(check.get("reads"), list):
            yield f"checks.{name}.reads", check["reads"]


def detect_changes(root: Path, since: str) -> tuple[dict[str, str], list[str]]:
    out = git(root, "diff", "--find-renames", "--name-status", since) or ""
    renames: dict[str, str] = {}
    deletions: list[str] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if parts[0].startswith("R") and len(parts) == 3:
            renames[parts[1]] = parts[2]
        elif parts[0] == "D" and len(parts) == 2:
            deletions.append(parts[1])
    return renames, sorted(deletions)


def _write_checked(project, data, original: str) -> None:
    buf = io.StringIO()
    _yaml().dump(data, buf)
    project.manifest_path.write_text(buf.getvalue())
    try:
        from reasonhold.project import Project

        Project.load(project.root)
    except ManifestInvalid:
        project.manifest_path.write_text(original)  # never leave a manifest the indexer would refuse
        raise


def curate(project, *, since: str | None, dry_run: bool = True) -> list[CurationEdit]:
    if not since:
        return []
    renames, deletions = detect_changes(project.root, since)
    if not renames and not deletions:
        return []
    original = project.manifest_path.read_text()
    data = _yaml().load(original)
    edits: list[CurationEdit] = []
    for old, new in sorted(renames.items()):
        edit = CurationEdit("rename", old, new)
        for location, seq in _lists(data):
            for i, value in enumerate(seq):
                if value == old:
                    seq[i] = new
                    edit.locations.append(location)
        edits.append(edit)
    for old in deletions:
        edit = CurationEdit("deletion", old, None)
        for location, seq in _lists(data):
            if old in seq:
                if len(seq) > 1:
                    seq.remove(old)
                    edit.locations.append(location)
                else:
                    edit.kept.append(location)
        if edit.locations or edit.kept:
            edits.append(edit)

    pending = PendingLog.load(project.pending_path)
    retracted = {r.file_path for r in DecisionLog.load(project.decisions_path).retractions()}
    aliases = pending.aliases()
    edits = [e for e in edits if e.locations or e.kept or (e.cause == "rename" and e.old_path in retracted
                                                             and aliases.get(e.old_path) != e.new_path)]
    if dry_run or not edits:
        return edits
    if any(e.locations for e in edits):
        _write_checked(project, data, original)
    for e in edits:
        if e.cause == "rename" and aliases.get(e.old_path) != e.new_path:
            append_jsonl(project.pending_path, make_record(
                "path_alias", {"old_path": e.old_path, "new_path": e.new_path}, CURATION_PROVENANCE))
        if e.locations:
            append_jsonl(project.pending_path, make_record(
                "curation", {"edit": e.describe(), "cause": e.cause}, CURATION_PROVENANCE))
    return edits


def _open_candidate(project, pending_id: str) -> dict:
    log = PendingLog.load(project.pending_path)
    record = log.get(pending_id)
    if record is None or record["kind"] != "candidate_binding" or not log.is_open(pending_id):
        raise UnknownRecord(f"{pending_id} is not an open candidate binding in {project.pending_rel}")
    return record


def _extend(seq, values) -> None:
    for v in values:
        if v not in seq:
            seq.append(v)


def promote(project, pending_id: str, *, provenance: dict) -> dict:
    from reasonhold.writes import resolve

    record = _open_candidate(project, pending_id)
    original = project.manifest_path.read_text()
    data = _yaml().load(original)
    target = record["target"]
    areas = data.get("areas") or {}
    created = False
    if target in areas:
        kind = "area"
        _extend(areas[target]["docs"], record["reads"])
    else:
        kind = "check"
        checks = data.get("checks")
        if checks is None:
            data["checks"] = checks = {}
        if target in checks:
            _extend(checks[target].setdefault("reads", []), record["reads"])
            _extend(checks[target].setdefault("validates_against", []), record["validates_against"])
        else:
            checks[target] = {
                "description": record["reason"],
                "mode": "index",
                "reads": list(record["reads"]),
                "validates_against": list(record["validates_against"]),
            }
            created = True
    _write_checked(project, data, original)
    resolution = resolve(project, pending_ids=[pending_id], outcome="promoted",
                         note=f"added to {kind} {target}", provenance=provenance)
    return {"promoted": pending_id, "target": target, "kind": kind, "created": created, "resolution": resolution["id"]}


def reject(project, pending_id: str, *, note: str | None = None, provenance: dict) -> dict:
    from reasonhold.writes import resolve

    _open_candidate(project, pending_id)
    resolution = resolve(project, pending_ids=[pending_id], outcome="rejected", note=note, provenance=provenance)
    return {"rejected": pending_id, "resolution": resolution["id"]}
