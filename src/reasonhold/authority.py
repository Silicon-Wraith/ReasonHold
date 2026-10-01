"""The authority ladder (R-10): which documents outrank which.

The ladder is data in the manifest. When a manifest has no `authority` block,
DEFAULT_LADDER applies; it reproduces Ariadne's seed classification exactly.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase

from reasonhold.errors import ManifestInvalid

FALLBACK = ("reference", "reference")
BUILTIN_LEVEL_WEIGHTS = {"decision": 0.0, "project-manifest": -0.06}


@dataclass(frozen=True)
class AuthorityRule:
    level: str
    document_kind: str
    paths: tuple[str, ...]
    weight: float = 0.0


DEFAULT_LADDER: tuple[AuthorityRule, ...] = (
    AuthorityRule("project-guidance", "project_guidance", ("AGENTS.md", "CLAUDE.md"), 0.03),
    AuthorityRule("architecture", "architecture_doc", ("docs/architecture/**",), 0.08),
    AuthorityRule("implementation-spec", "implementation_spec", ("docs/specs/**",), 0.06),
    AuthorityRule("implementation-plan", "implementation_plan", ("docs/plans/**",), 0.05),
    AuthorityRule("review", "review_finding", ("docs/reviews/**",), 0.0),
    AuthorityRule("review", "bug_investigation", ("docs/bugs/**",), 0.0),
    AuthorityRule("reference", "operational_guide", ("docs/**",), -0.02),
    AuthorityRule(
        "deployment",
        "deployment_config",
        ("justfile", "compose.infra.yml", "compose.app.yml", "compose.dev.yml", "Dockerfile*", "compose.*"),
        0.02,
    ),
    AuthorityRule("tooling", "skill_definition", (".claude/skills/**",), -0.04),
    AuthorityRule("tooling", "tooling_code", ("docs-rag/**", "devtools/**", "scripts/**", "benchmarks/**"), -0.04),
    AuthorityRule("implementation", "source_code", ("src/**",), 0.0),
    AuthorityRule("implementation", "frontend_code", ("ui/src/**",), 0.0),
    AuthorityRule("test", "test_code", ("tests/**",), -0.05),
    AuthorityRule("tooling", "tooling_code", ("*.py",), -0.04),
)


def path_matches(file_path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        return file_path.startswith(pattern[:-2])
    if any(ch in pattern for ch in "*?["):
        return fnmatchcase(file_path, pattern)
    return file_path == pattern


def classify(
    file_path: str,
    ladder: Sequence[AuthorityRule],
    *,
    decisions_rel: str | None,
    manifest_rel: str | None,
) -> tuple[str, str]:
    if decisions_rel and file_path == decisions_rel:
        return "decision", "decision_log"
    if manifest_rel and file_path == manifest_rel:
        return "project-manifest", "sync_doc_manifest"
    for rule in ladder:
        if any(path_matches(file_path, p) for p in rule.paths):
            return rule.level, rule.document_kind
    return FALLBACK


def level_weights(ladder: Sequence[AuthorityRule]) -> dict[str, float]:
    weights: dict[str, float] = dict(BUILTIN_LEVEL_WEIGHTS)
    for rule in ladder:
        weights.setdefault(rule.level, rule.weight)
    weights.setdefault("reference", -0.02)
    return weights


def _check_pattern(pattern: object, where: str) -> str:
    if not isinstance(pattern, str) or not pattern:
        raise ManifestInvalid(f"{where}: path patterns must be non-empty strings")
    if pattern.startswith("/") or pattern.startswith("..") or "/../" in pattern:
        raise ManifestInvalid(f"{where}: path pattern {pattern!r} must be relative to the repository and stay inside it")
    return pattern


def parse_ladder(raw: object) -> tuple[AuthorityRule, ...]:
    if not isinstance(raw, list) or not raw:
        raise ManifestInvalid("authority must be a non-empty list of rules")
    rules = []
    for i, item in enumerate(raw):
        where = f"authority[{i}]"
        if not isinstance(item, dict) or not isinstance(item.get("level"), str) or not item["level"]:
            raise ManifestInvalid(f"{where}: needs a non-empty 'level'")
        paths = item.get("paths")
        if not isinstance(paths, list) or not paths:
            raise ManifestInvalid(f"{where}: needs a non-empty 'paths' list")
        weight = item.get("weight", 0.0)
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise ManifestInvalid(f"{where}: 'weight' must be a number")
        rules.append(
            AuthorityRule(
                level=item["level"],
                document_kind=str(item.get("document_kind") or item["level"]),
                paths=tuple(_check_pattern(p, where) for p in paths),
                weight=float(weight),
            )
        )
    return tuple(rules)


def ladder_sha256(ladder: Sequence[AuthorityRule]) -> str:
    data = [[r.level, r.document_kind, list(r.paths), r.weight] for r in ladder]
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
