"""Governance (spec section 5): what governs a path, what is retracted,
what is in conflict, what the manifest fails to place. Manifest and logs only:
no vector search and no code chunks (the code-index seam stays narrow)."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

from reasonhold.authority import classify, level_weights, path_matches
from reasonhold.decisions import DecisionLog
from reasonhold.errors import UnknownRecord
from reasonhold.identity import git
from reasonhold.indexer import EXCLUDED_PATH_PARTS
from reasonhold.pending import PendingLog, follow_alias

SOURCE_SUFFIXES = (".py", ".cs", ".sql", ".ts", ".tsx", ".js", ".jsx", ".vue", ".go", ".rs", ".java", ".kt", ".rb", ".sh")
_BINDING_ORDER = {"check": 0, "area": 1, "global": 2}
_GLOB = "*?["


def normalize_path(path: str) -> str:
    text = str(path).strip()
    if text.startswith("/") or ".." in PurePosixPath(text).parts:
        raise ValueError(f"{path!r} must be relative to the repository and stay inside it")
    return PurePosixPath(text).as_posix().removeprefix("./")


def covers(pattern: str, path: str) -> bool:
    if pattern.endswith("/"):
        return path.startswith(pattern)
    if any(c in pattern for c in _GLOB):
        return path_matches(path, pattern)
    return path == pattern or path.startswith(pattern + "/")


def _level(project, doc: str) -> tuple[int, str, float]:
    level, _ = classify(doc, project.ladder, decisions_rel=project.decisions_rel, manifest_rel=project.manifest_rel)
    order = [rule.level for rule in project.ladder]
    position = order.index(level) if level in order else len(order)
    return position, level, level_weights(project.ladder).get(level, 0.0)


def _doc_of(ref: str, aliases) -> str:
    return follow_alias(ref.partition("#")[0], aliases)


def retractions_for(project, path: str) -> list[dict]:
    log = DecisionLog.load(project.decisions_path)
    pending = PendingLog.load(project.pending_path)
    file_path, _, section = normalize_path(path).partition("#")
    current = follow_alias(file_path, pending.aliases())
    names = pending.former_names(current) | {file_path}
    wanted = section.strip().lower()
    out = []
    for r in log.retractions():
        if r.file_path not in names:
            continue
        if wanted and r.section:
            have = r.section.strip().lower()
            if have not in wanted and wanted not in have:
                continue
        out.append({
            "path": r.path,
            "section": r.section,
            "retraction_summary": r.retraction_summary,
            "decision_id": r.decision_id,
            "topic": r.topic,
            "date": r.date,
            "via_alias": r.file_path != current,
        })
    return out


def governing_docs(project, path: str) -> dict:
    path = normalize_path(path)
    m = project.manifest
    found: dict[str, tuple[str, str]] = {}
    for check in m.checks:
        if any(covers(v, path) for v in check.validates_against):
            for doc in check.reads:
                found.setdefault(doc, ("check", check.name))
    area = m.infer_area(path)
    if area:
        for a in m.areas:
            if a.name == area:
                for doc in a.docs:
                    found.setdefault(doc, ("area", area))
    for doc in m.global_docs:
        found.setdefault(doc, ("global", "global"))
    for doc in m.global_archival:
        found.pop(doc, None)

    pending = PendingLog.load(project.pending_path)
    aliases = pending.aliases()
    open_conflicts = pending.open("conflict")
    open_candidates = pending.open("candidate_binding")
    documents = []
    for doc, (kind, name) in found.items():
        position, level, weight = _level(project, doc)
        documents.append({
            "path": doc,
            "exists": (project.root / doc).exists(),
            "binding": {"kind": kind, "name": name},
            "authority_level": level,
            "weight": weight,
            "retractions": retractions_for(project, doc),
            "open_conflicts": [c for c in open_conflicts if doc in (_doc_of(c["doc_a"], aliases), _doc_of(c["doc_b"], aliases))],
            "open_candidates": [c for c in open_candidates if doc in c["reads"]],
            "_sort": (-weight, position, _BINDING_ORDER[kind], doc),
        })
    documents.sort(key=lambda d: d.pop("_sort"))

    by_level: dict[str, list[str]] = {}
    for d in documents:
        if not any(r["section"] is None for r in d["retractions"]):
            by_level.setdefault(d["authority_level"], []).append(d["path"])
    hints = [
        {"level": level, "documents": docs, "note": "same authority level and both govern this path; check that they agree"}
        for level, docs in by_level.items()
        if len(docs) > 1
    ]
    return {
        "path": path,
        "area": area,
        "documents": documents,
        "overlap_hints": hints,
        "open_candidates": [c for c in open_candidates if any(covers(v, path) for v in c["validates_against"])],
    }


def decision(project, id: str) -> dict:
    log = DecisionLog.load(project.decisions_path)
    record = log.get(id)
    if record is None:
        raise UnknownRecord(f"{id} is not in {project.decisions_rel}")
    return {"record": record, "status": log.status(id), "superseded_by": log.superseded_by(id)}


def conflicts(project, path: str | None = None, open_only: bool = True) -> list[dict]:
    pending = PendingLog.load(project.pending_path)
    aliases = pending.aliases()
    wanted = normalize_path(path) if path else None
    out = []
    for r in pending.records:
        if r["kind"] != "conflict":
            continue
        is_open = pending.is_open(r["id"])
        if open_only and not is_open:
            continue
        if wanted and wanted not in (_doc_of(r["doc_a"], aliases), _doc_of(r["doc_b"], aliases)) and not any(
            covers(p, wanted) for p in r["paths"]
        ):
            continue
        out.append({**r, "open": is_open, "resolution": pending.resolution_for(r["id"])})
    return out


def _repo_files(project) -> list[str]:
    listed = git(project.root, "ls-files", "--cached", "--others", "--exclude-standard")
    if listed is not None:
        files = listed.splitlines()
    else:
        files = []
        for dirpath, dirnames, filenames in os.walk(project.root):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_PATH_PARTS]
            for name in filenames:
                files.append((Path(dirpath) / name).relative_to(project.root).as_posix())
    return sorted(f for f in set(files) if (project.root / f).is_file())


def coverage(project) -> dict:
    m = project.manifest
    files = _repo_files(project)
    sources = [f for f in files if f.endswith(SOURCE_SUFFIXES)]
    uncovered = [f for f in sources if m.infer_area(f) is None]
    unbound = [f for f in sources if m.infer_area(f) is not None
               and not any(covers(v, f) for c in m.checks for v in c.validates_against)]
    placed = set(m.global_docs) | set(m.global_archival)
    placed |= {g for g in m.global_index if not any(ch in g for ch in _GLOB)}
    placed |= {d for a in m.areas for d in a.docs} | {d for c in m.checks for d in c.reads}
    docs = [f for f in files if f.endswith(".md") and _level(project, f)[1] not in ("tooling", "test")]
    unplaced = [f for f in docs if f not in placed]
    literal = list(m.global_docs) + list(m.global_archival) + [d for a in m.areas for d in a.docs] + [
        d for c in m.checks for d in c.reads
    ]
    missing = sorted({p for p in literal if not any(ch in p for ch in _GLOB) and not (project.root / p).exists()})
    return {
        "uncovered_sources": uncovered,
        "unplaced_docs": unplaced,
        "unbound_sources": unbound,
        "missing_references": missing,
        "holes": len(uncovered) + len(unplaced) + len(missing),
    }
