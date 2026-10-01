"""`reasonhold check`: validate the manifest, the decision log and the sidecar."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources

import jsonschema
import yaml

from reasonhold.decisions import record_id

_GLOB_CHARS = "*?["


@dataclass(frozen=True)
class Problem:
    severity: str
    file: str
    line: int | None
    message: str


def load_schema(name: str) -> dict:
    return json.loads(resources.files("reasonhold").joinpath(f"schemas/{name}.schema.json").read_text())


def _schema_errors(validator, value) -> list[str]:
    return [f"{'/'.join(map(str, e.absolute_path)) or '(record)'}: {e.message}" for e in validator.iter_errors(value)]


def _manifest_problems(project) -> list[Problem]:
    rel = project.manifest_rel
    raw = yaml.safe_load(project.manifest_path.read_text()) or {}
    problems = [Problem("error", rel, None, m) for m in _schema_errors(jsonschema.Draft202012Validator(load_schema("manifest")), raw)]

    def literal(label: str, path: str) -> None:
        if any(c in path for c in _GLOB_CHARS):
            return
        if not (project.root / path.rstrip("/")).exists():
            problems.append(Problem("warning", rel, None, f"{label} references missing path {path}"))

    m = project.manifest
    for path in m.global_docs:
        literal("global.docs", path)
    for path in m.global_archival:
        literal("global.archival", path)
    for area in m.areas:
        for path in area.docs:
            literal(f"areas.{area.name}.docs", path)
    for check_spec in m.checks:
        for path in check_spec.reads:
            literal(f"checks.{check_spec.name}.reads", path)
        for path in check_spec.validates_against:
            literal(f"checks.{check_spec.name}.validates_against", path)
    defined = {c.name for c in m.checks}
    for name in m.global_checks:
        if name not in defined:
            problems.append(Problem("warning", rel, None, f"global.checks names undefined check {name}"))
    for area in m.areas:
        for name in area.checks:
            if name not in defined:
                problems.append(Problem("warning", rel, None, f"areas.{area.name}.checks names undefined check {name}"))
    return problems


def _jsonl_lines(path):
    if not path.exists():
        return
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if line.strip():
            yield number, line


def _decision_problems(project) -> list[Problem]:
    rel = project.decisions_rel
    validator = jsonschema.Draft202012Validator(load_schema("decision"))
    problems, seen, parsed = [], {}, []
    for number, line in _jsonl_lines(project.decisions_path):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(Problem("error", rel, number, f"not JSON: {exc.msg}"))
            continue
        errors = _schema_errors(validator, record)
        if errors:
            problems.extend(Problem("error", rel, number, e) for e in errors)
            continue
        rid = record_id(record)
        if rid in seen:
            problems.append(Problem("error", rel, number, f"duplicate id {rid} (first on line {seen[rid]})"))
            continue
        seen[rid] = number
        parsed.append((number, record))
    for number, record in parsed:
        for target in record.get("supersedes_records") or []:
            if target not in seen:
                problems.append(Problem("error", rel, number, f"supersedes_records names unknown record {target}"))
    return problems


def _pending_problems(project) -> list[Problem]:
    rel = project.pending_rel
    validator = jsonschema.Draft202012Validator(load_schema("pending"))
    problems, ids, resolutions = [], set(), []
    for number, line in _jsonl_lines(project.pending_path):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(Problem("error", rel, number, f"not JSON: {exc.msg}"))
            continue
        errors = _schema_errors(validator, record)
        if errors:
            problems.extend(Problem("error", rel, number, e) for e in errors)
            continue
        ids.add(record["id"])
        if record["kind"] == "resolution":
            resolutions.append((number, record))
    for number, record in resolutions:
        for target in record["resolves"]:
            if target not in ids:
                problems.append(Problem("warning", rel, number, f"resolution names unknown record {target}"))
    return problems


def check(project) -> list[Problem]:
    return _manifest_problems(project) + _decision_problems(project) + _pending_problems(project)
