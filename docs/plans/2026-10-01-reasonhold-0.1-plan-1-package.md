# ReasonHold 0.1, Plan 1: the `reasonhold` package

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `reasonhold` Python package (spec build steps 1 to 8): Ariadne's `docs-rag/` extracted behind its 189-test parity suite, then project and branch identity, embedding providers, the decision log v2, the index lifecycle, governance, curation, search, preamble, CLI, MCP server, Agno extra and skill pack.

**Architecture:** Step 1 copies the seed modules into `src/reasonhold/` unchanged except for imports, and the 189 seed tests must pass before anything else changes. Later tasks replace the seed's module-level configuration (`config.py` globals) with a `Project` object loaded from the repository's manifest, split the seed's large modules along the spec's responsibilities, and add the new capabilities. A thin `ReasonHold` facade (`api.py`) is the single library surface; the CLI, MCP server and Agno toolkit wrap it.

**Tech Stack:** Python 3.11+, `weaviate-client` 4.x, `pyyaml`, `ruamel.yaml`, `jsonschema`, `fastmcp` 3.x, Ollama over HTTP, pytest. Optional `agno` 3.0.x.

**Spec:** `docs/specs/2026-10-01-reasonhold-0.1-design.md` (this repository). Requirements R-01 to R-23: `docs/architecture/requirements.md`. Embedding evidence and the 40 benchmark questions: `docs/reviews/2026-10-01-embedding-spike.md`.

**Scope ruling:** the spec's build step 9 (migrating Sendesis and Ariadne) is Plan 2. It changes two other repositories and depends on this package's finished CLI, so it is planned after this plan lands.

## Global Constraints

- Repository `/mnt/ml_storage/dev/projects/ReasonHold`. All work happens in the worktree `/mnt/ml_storage/dev/projects/ReasonHold/.worktrees/m2-package` on branch `m2-package`, created from `plan/m2-package` (`main` after the merged PR #1, plus this plan). `.worktrees/` is gitignored.
- Nothing is pushed and nothing is merged by an agent. Pull requests are merged by the operator only.
- Python `>=3.11`. Virtualenv `.venv` in the worktree, created with `/usr/bin/python3.11`. No global installs.
- Runtime dependencies exactly: `weaviate-client>=4.20,<5`, `pyyaml>=6`, `ruamel.yaml>=0.18`, `jsonschema>=4.18`, `fastmcp>=3.0,<4`. Extra `agno`: `agno>=3.0.11,<3.1`. Dev: `pytest>=8`, plus `ollama>=0.4` only while seed modules that import the `ollama` client still exist (`index.py`, `server.py`); Task 14 removes it from the dev extra.
- Seed source: Ariadne commit `8c5c451`, directory `docs-rag/`, read with `git -C /mnt/ml_storage/dev/projects/Ariadne show 8c5c451:docs-rag/<file>`. Never edit files in the Ariadne repository.
- Unit tests never touch the network, Weaviate or Ollama. Real-service tests are marked `@pytest.mark.integration` and deselected by default.
- Integration tests use only Weaviate collections whose names start with `RH_Test` and always delete them.
- Collections ReasonHold creates are named `RH_<Project>__<branch slug>` and match `^[A-Z][A-Za-z0-9_]*$`.
- Default embedding: provider `ollama`, model `qwen3-embedding:0.6b`, base URL `http://localhost:11434`.
- Decision record id: `dec-` + first 12 hex digits of `sha256(topic + "|" + datetime)`.
- Pending record id: `pen-` + first 12 hex digits of `sha256(kind + "|" + datetime + "|" + canonical JSON of the payload)`.
- `decisions.jsonl` and `reasonhold.pending.jsonl` are append-only. No code path rewrites or deletes a line in either.
- The manifest file is `reasonhold.yaml`, or `sync-doc.yaml` as the legacy name; `reasonhold.yaml` wins when both exist.
- Preamble budget: at most 60 lines and 4096 bytes; rows are dropped whole, never truncated; it always exits 0.
- ReasonHold never generates text. No LLM calls anywhere in the package.
- No MCP or Agno tool can promote or reject a candidate.
- In docs and user-facing text, do not use em dashes.

## Review Focus

1. **A project directory that is not a git repository** (or has no commits yet). Expected: indexing and queries still work using branch `no-git`; the merge rule and `curate` are skipped with a one-line warning instead of crashing. Pinned in Task 4 (`test_non_git_directory_uses_no_git_branch`) and Task 9 (`test_index_state_without_git`).
2. **Branch names that are long, contain `/`, dots, uppercase or non-ASCII characters, or differ only after sanitizing** (`feat/a-b` vs `feat/a_b`). Expected: always a valid, distinct collection name. Pinned in Task 4 (`test_collection_names_are_valid_and_distinct`).
3. **Embedding service down while recording a decision.** Expected: nothing is appended to `decisions.jsonl` and the caller gets `StoreUnavailable`; a retry later succeeds and produces exactly one record. Pinned in Task 6 (`test_store_decision_appends_nothing_when_embedding_fails`).
4. **A manifest that references files that do not exist, absolute paths, or `..` paths.** Expected: `reasonhold check` reports each problem; indexing skips the missing file instead of crashing; absolute or escaping paths are rejected as `ManifestInvalid`. Pinned in Task 3 (`test_manifest_rejects_escaping_paths`) and Task 7 (`test_check_reports_missing_referenced_files`).
5. **Session start when Weaviate or Ollama is down, or no index exists yet.** Expected: the preamble still prints within budget with an "index unavailable" or "index missing" line, and exits 0. Pinned in Task 12 (`test_preamble_fails_open_without_store`).

---

## File Structure

```
ReasonHold/ (worktree .worktrees/m2-package)
  pyproject.toml
  .gitignore                      (adds .venv/, .worktrees/, __pycache__/, *.egg-info/, .pytest_cache/)
  src/reasonhold/
    __init__.py                   version
    errors.py                     typed errors
    settings.py                   Weaviate connection settings from the environment
    authority.py                  authority ladder: rules, default ladder, classify, weights
    manifest.py                   manifest model and loader (seed, extended)
    project.py                    Project: root, manifest, paths, embedding config, ladder
    identity.py                   git helpers, branch, collection naming
    schema.py                     Weaviate property definitions (seed, trimmed)
    store.py                      connection factory, collection metadata, ensure/drop/list
    embedding.py                  provider protocol, Ollama and OpenAI-compatible providers, model guard
    chunkers.py                   structure-aware chunkers (seed, unchanged)
    enrichment.py                 enrich and render (seed, ladder-driven)
    jsonl.py                      append-only JSONL writer shared by both logs
    decisions.py                  decision log v2 (seed decisions_io, extended)
    pending.py                    pending sidecar
    overlay.py                    retraction overlay (moved from seed index.py, alias-aware)
    indexer.py                    per-file indexing (seed index.py, minus main)
    lifecycle.py                  index state, full-rebuild rule, lock, run_index, gc
    codeindex.py                  exact queries and freshness (seed symbols.py): the Serena seam
    search.py                     search_docs, search_decisions, reranker (seed server.py logic)
    writes.py                     store_decision, propose_binding, report_conflict, resolve
    governance.py                 governing_docs, retractions_for, conflicts, decision, coverage
    curation.py                   mechanical curate, promote, reject
    validation.py                 JSON Schemas and `check`
    schemas/manifest.schema.json
    schemas/decision.schema.json
    schemas/pending.schema.json
    preamble.py                   session preamble (seed bootstrap.py, extended)
    audit.py                      audit_supersedes (seed, unchanged logic)
    api.py                        ReasonHold facade
    cli.py                        `reasonhold` command
    mcp_server.py                 stdio MCP server
    agno.py                       ReasonHoldTools, ReasonHoldKnowledge, reasonhold_context
    resources/skills/<name>/SKILL.md   skill pack
    resources/agents-snippet.md        AGENTS.md section for other CLIs
    resources/hooks/claude-settings.json, resources/hooks/post-merge
    resources/mcp.json                 MCP client entry for `reasonhold mcp`
  tests/                          seed tests (adapted) plus one file per new module
  tests/fixtures/                 seed fixtures plus small sample repos built in tmp_path
  README.md
```

Seed modules that disappear by the end: `config.py` (Task 14, with `server.py`, its last importer; until then new code takes explicit parameters with seed-compatible defaults), `index.py` (split into `overlay.py` and `indexer.py` in Task 8; its `main` becomes `lifecycle.run_index` in Task 9), `server.py` (split into `search.py`, `writes.py`, `mcp_server.py` in Tasks 6, 11 and 14), `symbols.py` (becomes `codeindex.py` in Task 11), `bootstrap.py` (becomes `preamble.py` in Task 12), `decisions_io.py` (becomes `decisions.py` in Task 6), `audit_supersedes.py` (becomes `audit.py` in Task 6), `backfill_decisions.py` (removed in Task 8 with `index.py`, which it imports; full re-index covers it).

---

### Task 1: Seed extraction and the parity gate

**Files:**
- Create: `pyproject.toml`, `.gitignore` additions, `src/reasonhold/__init__.py`
- Create (copied from seed): `src/reasonhold/{config,manifest,chunkers,enrichment,schema,decisions_io,index,server,symbols,bootstrap,audit_supersedes,backfill_decisions}.py`
- Create (copied from seed): `tests/*.py` (18 files), `tests/fixtures/*`

**Interfaces:**
- Produces: the package `reasonhold` with the seed modules importable as `reasonhold.<module>`; 189 passing tests.

- [ ] **Step 1: Create the worktree, venv and packaging**

```bash
cd /mnt/ml_storage/dev/projects/ReasonHold
grep -qx '.worktrees/' .gitignore 2>/dev/null || printf '.worktrees/\n' >> .gitignore
git add .gitignore && git commit -q -m "Ignore local worktrees" || true
# Base: plan/m2-package (main after PR #1, plus this plan).
git worktree add .worktrees/m2-package -b m2-package plan/m2-package
cd .worktrees/m2-package
printf '.venv/\n__pycache__/\n*.egg-info/\n.pytest_cache/\n' >> .gitignore
```

`pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "reasonhold"
version = "0.1.0.dev0"
description = "Tells coding agents what to believe about a repository: governing documents, retractions, authority and decisions."
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.11"
dependencies = [
    "weaviate-client>=4.20,<5",
    "pyyaml>=6",
    "ruamel.yaml>=0.18",
    "jsonschema>=4.18",
    "fastmcp>=3.0,<4",
]

[project.optional-dependencies]
agno = ["agno>=3.0.11,<3.1"]
dev = ["pytest>=8", "ollama>=0.4"]  # ollama: seed index.py and server.py only; removed in Task 14

[project.scripts]
reasonhold = "reasonhold.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
reasonhold = ["schemas/*.json", "resources/**/*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--strict-markers -m 'not integration'"
markers = ["integration: needs the local Weaviate (port 8081) and Ollama; run on purpose"]
```

`src/reasonhold/__init__.py`:

```python
"""ReasonHold: what a coding agent should believe about a repository."""

__version__ = "0.1.0.dev0"
```

```bash
/usr/bin/python3.11 -m venv .venv && .venv/bin/pip install -q -e '.[dev]'
```

- [ ] **Step 2: Copy the seed modules and tests verbatim**

```bash
SEED="git -C /mnt/ml_storage/dev/projects/Ariadne show 8c5c451:docs-rag"
for m in config manifest chunkers enrichment schema decisions_io index server symbols bootstrap audit_supersedes backfill_decisions; do
  $SEED/$m.py > src/reasonhold/$m.py
done
mkdir -p tests/fixtures
for f in $(git -C /mnt/ml_storage/dev/projects/Ariadne ls-tree --name-only 8c5c451 docs-rag/tests/ | grep '\.py$'); do
  $SEED/tests/$(basename $f) > tests/$(basename $f)
done
for f in $(git -C /mnt/ml_storage/dev/projects/Ariadne ls-tree --name-only 8c5c451 docs-rag/tests/fixtures/); do
  $SEED/tests/fixtures/$(basename $f) > tests/fixtures/$(basename $f)
done
git add -A && git commit -q -m "Seed: copy docs-rag (Ariadne 8c5c451) verbatim"
```

- [ ] **Step 3: Run the tests and watch them fail on imports**

Run: `.venv/bin/pytest -q`
Expected: collection errors such as `ModuleNotFoundError: No module named 'manifest'`. This is the expected RED: the code is unchanged and only the import paths are wrong.

- [ ] **Step 4: Rewrite imports to the package, with no behavior change**

Apply exactly these rewrites (a one-off Python script in the scratchpad is fine; do not commit the script):

1. In every `src/reasonhold/*.py`: a top-level `from <seed> import X` or `import <seed>` where `<seed>` is one of `config manifest chunkers enrichment schema decisions_io index server symbols bootstrap audit_supersedes backfill_decisions` becomes `from reasonhold.<seed> import X` or `import reasonhold.<seed> as <seed>`. Also rewrite the function-local imports in `symbols.py` (`from index import gather_files`, `from index import get_indexed_mtimes`, `from schema import get_client`).
2. Remove any `sys.path.insert(...)` line and any `# noqa: E402` comment that existed only because of it.
3. `config.py`: replace the two path lines with:

```python
# Project root: the repository being indexed. Seed behavior assumed the tool was
# vendored one level below the root; the package reads it from the environment
# or the current directory instead. Task 3 replaces this module entirely.
PROJECT_ROOT = Path(os.getenv("REASONHOLD_ROOT", os.getcwd())).resolve()
SYNC_DOC_PATH = PROJECT_ROOT / "sync-doc.yaml"
```

and replace the `DECISIONS_FILE` line with:

```python
DECISIONS_FILE = PROJECT_ROOT / os.getenv("REASONHOLD_DECISIONS", "docs-rag/decisions.jsonl")
```

4. `bootstrap.py` `render_role_c`: replace the freshness subprocess (which ran `docs-rag/.venv/bin/python symbols.py`) with `[sys.executable, str(Path(__file__).with_name("symbols.py")), "--freshness"]` (a seed test asserts the source names `symbols.py` and `--freshness`).
5. In every `tests/*.py`: delete `sys.path.insert(0, str(Path(__file__).parent.parent))` (and an `import sys` left unused by it); `from <seed> import ...` becomes `from reasonhold.<seed> import ...`; `import <seed> as <alias>` becomes `import reasonhold.<seed> as <alias>`.
6. Delete `tests/__init__.py` if present.
7. Seed tests that read module source as `Path(__file__).parent.parent / "<mod>.py"` (in `test_bootstrap.py`, `test_symbols.py`, `test_audit_supersedes.py`) read `Path(reasonhold.<mod>.__file__)` instead, with `import reasonhold.<mod>` added. Later tasks that move a module (`audit.py` in Task 6, `codeindex.py` in Task 11, `preamble.py` in Task 12) re-point these reads at the new module.

- [ ] **Step 5: Run the parity gate**

Run: `.venv/bin/pytest -q -p no:cacheprovider`
Expected: `189 passed`. Any failure here is an import or path rewrite mistake; fix the rewrite, never the assertions.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -q -m "Seed: package imports; 189 seed tests pass (parity gate)"
```

---

### Task 2: Typed errors and the authority ladder

**Files:**
- Create: `src/reasonhold/errors.py`, `src/reasonhold/authority.py`, `tests/test_authority.py`

**Interfaces:**
- Produces:

```python
# errors.py
class ReasonHoldError(Exception): ...
class ManifestInvalid(ReasonHoldError): ...
class IndexMissing(ReasonHoldError): ...
class IndexStale(ReasonHoldError): ...
class ModelMismatch(ReasonHoldError): ...
class UnknownRecord(ReasonHoldError): ...
class StoreUnavailable(ReasonHoldError): ...

# authority.py
@dataclass(frozen=True)
class AuthorityRule:
    level: str
    document_kind: str
    paths: tuple[str, ...]
    weight: float = 0.0
DEFAULT_LADDER: tuple[AuthorityRule, ...]
BUILTIN_LEVEL_WEIGHTS: dict[str, float]          # "decision": 0.0, "project-manifest": -0.06
def path_matches(file_path: str, pattern: str) -> bool
def classify(file_path: str, ladder: Sequence[AuthorityRule], *, decisions_rel: str | None, manifest_rel: str | None) -> tuple[str, str]
def level_weights(ladder: Sequence[AuthorityRule]) -> dict[str, float]
def parse_ladder(raw: object) -> tuple[AuthorityRule, ...]   # raises ManifestInvalid
def ladder_sha256(ladder: Sequence[AuthorityRule]) -> str
```

`path_matches` semantics: a pattern ending in `/**` matches that directory prefix; a pattern containing `*`, `?` or `[` uses `fnmatch.fnmatchcase` (where `*` crosses `/`, matching the seed's `endswith`/`startswith` behavior); anything else is an exact path.

- [ ] **Step 1: Write the failing tests**

`tests/test_authority.py`:

```python
import pytest

from reasonhold.authority import (
    BUILTIN_LEVEL_WEIGHTS,
    DEFAULT_LADDER,
    AuthorityRule,
    classify,
    ladder_sha256,
    level_weights,
    parse_ladder,
    path_matches,
)
from reasonhold.errors import ManifestInvalid

SEED_CASES = [
    ("docs-rag/decisions.jsonl", ("decision", "decision_log")),
    ("sync-doc.yaml", ("project-manifest", "sync_doc_manifest")),
    ("AGENTS.md", ("project-guidance", "project_guidance")),
    ("CLAUDE.md", ("project-guidance", "project_guidance")),
    ("docs/architecture/x.md", ("architecture", "architecture_doc")),
    ("docs/specs/x.md", ("implementation-spec", "implementation_spec")),
    ("docs/plans/x.md", ("implementation-plan", "implementation_plan")),
    ("docs/reviews/x.md", ("review", "review_finding")),
    ("docs/bugs/x.md", ("review", "bug_investigation")),
    ("docs/runbook.md", ("reference", "operational_guide")),
    ("justfile", ("deployment", "deployment_config")),
    ("compose.infra.yml", ("deployment", "deployment_config")),
    ("Dockerfile", ("deployment", "deployment_config")),
    (".claude/skills/x/SKILL.md", ("tooling", "skill_definition")),
    ("docs-rag/index.py", ("tooling", "tooling_code")),
    ("scripts/x.sh", ("tooling", "tooling_code")),
    ("src/worker/x.py", ("implementation", "source_code")),
    ("ui/src/x.vue", ("implementation", "frontend_code")),
    ("tests/test_x.py", ("test", "test_code")),
    ("tools/x.py", ("tooling", "tooling_code")),
    ("README.txt", ("reference", "reference")),
]


@pytest.mark.parametrize("path, expected", SEED_CASES)
def test_default_ladder_reproduces_seed_classification(path, expected):
    got = classify(path, DEFAULT_LADDER, decisions_rel="docs-rag/decisions.jsonl", manifest_rel="sync-doc.yaml")
    assert got == expected


def test_seed_weights_are_reproduced():
    w = level_weights(DEFAULT_LADDER)
    assert w["architecture"] == 0.08 and w["implementation-spec"] == 0.06 and w["implementation-plan"] == 0.05
    assert w["project-guidance"] == 0.03 and w["deployment"] == 0.02 and w["implementation"] == 0.0
    assert w["review"] == 0.0 and w["reference"] == -0.02 and w["tooling"] == -0.04 and w["test"] == -0.05
    assert w["decision"] == BUILTIN_LEVEL_WEIGHTS["decision"] == 0.0
    assert w["project-manifest"] == BUILTIN_LEVEL_WEIGHTS["project-manifest"] == -0.06


def test_path_matches():
    assert path_matches("docs/specs/a/b.md", "docs/specs/**")
    assert not path_matches("docs/specsx/a.md", "docs/specs/**")
    assert path_matches("a/b/c.py", "*.py")
    assert path_matches("CLAUDE.md", "CLAUDE.md") and not path_matches("x/CLAUDE.md", "CLAUDE.md")


def test_custom_ladder_from_manifest_data():
    ladder = parse_ladder([
        {"level": "spec", "paths": ["design/**"], "document_kind": "design_doc", "weight": 0.07},
        {"level": "implementation", "paths": ["lib/**"]},
    ])
    assert classify("design/a.md", ladder, decisions_rel=None, manifest_rel=None) == ("spec", "design_doc")
    assert classify("lib/x.py", ladder, decisions_rel=None, manifest_rel=None) == ("implementation", "implementation")
    assert classify("other.md", ladder, decisions_rel=None, manifest_rel=None) == ("reference", "reference")
    assert level_weights(ladder)["spec"] == 0.07


@pytest.mark.parametrize("raw", [
    "not a list",
    [{"paths": ["x/**"]}],
    [{"level": "a", "paths": []}],
    [{"level": "a", "paths": ["/abs/**"]}],
    [{"level": "a", "paths": ["../up/**"]}],
    [{"level": "a", "paths": ["x/**"], "weight": "high"}],
])
def test_parse_ladder_rejects_bad_input(raw):
    with pytest.raises(ManifestInvalid):
        parse_ladder(raw)


def test_ladder_hash_changes_with_rules():
    a = ladder_sha256(DEFAULT_LADDER)
    b = ladder_sha256(DEFAULT_LADDER + (AuthorityRule("x", "x", ("x/**",)),))
    assert a != b and len(a) == 64
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_authority.py -q`
Expected: collection error, `No module named 'reasonhold.authority'`.

- [ ] **Step 3: Implement `errors.py`**

```python
"""Typed errors. Ordinary questions never raise for staleness; they warn."""


class ReasonHoldError(Exception):
    """Base class for every error ReasonHold raises on purpose."""


class ManifestInvalid(ReasonHoldError):
    """The manifest, decision log or pending sidecar does not validate."""


class IndexMissing(ReasonHoldError):
    """No index exists for this project and branch yet."""


class IndexStale(ReasonHoldError):
    """An absence question was asked of a stale index."""


class ModelMismatch(ReasonHoldError):
    """The index was built with a different embedding model or dimension."""


class UnknownRecord(ReasonHoldError):
    """A decision or pending record id does not exist."""


class StoreUnavailable(ReasonHoldError):
    """Weaviate or the embedding provider could not be reached."""
```

- [ ] **Step 4: Implement `authority.py`**

```python
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
```

- [ ] **Step 5: Run the tests, then the whole suite**

Run: `.venv/bin/pytest tests/test_authority.py -q && .venv/bin/pytest -q`
Expected: authority tests pass; whole suite still `189 passed` plus the new ones.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -q -m "Typed errors and a data-driven authority ladder reproducing the seed ranking"
```

---

### Task 3: Manifest v1, Project and settings

**Files:**
- Modify: `src/reasonhold/manifest.py`, `src/reasonhold/enrichment.py`
- Create: `src/reasonhold/settings.py`, `src/reasonhold/project.py`, `tests/test_project.py`
- Modify tests: `tests/test_manifest.py`, `tests/test_enrichment.py`

**Interfaces:**
- Consumes: `AuthorityRule`, `DEFAULT_LADDER`, `classify`, `parse_ladder` (Task 2); `ManifestInvalid` (Task 2).
- Produces:

```python
# manifest.py
@dataclass(frozen=True)
class CheckSpec:
    name: str
    description: str
    mode: str                         # "index" or "fs"
    reads: tuple[str, ...]
    validates_against: tuple[str, ...]
@dataclass(frozen=True)
class AreaManifest:                   # seed fields plus:
    checks: tuple[str, ...] = ()
@dataclass(frozen=True)
class Manifest:                       # seed fields plus:
    global_docs: tuple[str, ...] = ()
    global_archival: tuple[str, ...] = ()
    global_checks: tuple[str, ...] = ()
    checks: tuple[CheckSpec, ...] = ()
    project_raw: dict = field(default_factory=dict)
    authority_raw: object = None
    def iter_corpus_globs(self, area_names: set[str] | None = None, extra: Sequence[str] = ()) -> list[str]
    def check(self, name: str) -> CheckSpec | None
def load_manifest(path: Path) -> Manifest            # path is required; raises ManifestInvalid

# settings.py
@dataclass(frozen=True)
class WeaviateSettings:
    host: str = "localhost"
    http_port: int = 8081
    grpc_port: int = 50052
    cloud_url: str | None = None
    api_key_env: str = "WEAVIATE_API_KEY"
def weaviate_settings_from_env(environ: Mapping[str, str] | None = None) -> WeaviateSettings

# project.py
MANIFEST_NAMES = ("reasonhold.yaml", "sync-doc.yaml")
@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str = "ollama"
    model: str = "qwen3-embedding:0.6b"
    base_url: str = "http://localhost:11434"
    api_key_env: str | None = None
@dataclass(frozen=True)
class Project:
    root: Path
    manifest_path: Path
    manifest: Manifest
    id: str
    decisions_path: Path
    pending_path: Path
    embedding: EmbeddingConfig
    branch_isolation: bool
    ladder: tuple[AuthorityRule, ...]
    manifest_rel: str        # property
    decisions_rel: str       # property
    pending_rel: str         # property
    @classmethod
    def load(cls, root: Path | str | None = None) -> "Project"     # raises ManifestInvalid
    def rel(self, path: Path) -> str
    def corpus_globs(self, area_names: set[str] | None = None) -> list[str]

# enrichment.py
def enrich_chunk(chunk: dict, manifest: Manifest, *, ladder=DEFAULT_LADDER,
                 decisions_rel: str | None = "docs-rag/decisions.jsonl",
                 manifest_rel: str | None = "sync-doc.yaml") -> dict
def enrich_for_project(chunk: dict, project: Project) -> dict
def file_type_for(path: str, decisions_rel: str | None) -> str
```

Decision-log path resolution in `Project.load`: `project.decisions` from the manifest if set; else `docs-rag/decisions.jsonl` if the manifest file is the legacy `sync-doc.yaml` and that file exists (pre-migration Ariadne); else `decisions.jsonl` at the root. Project id: `project.id` if set, else the root directory name lowercased with runs of non-alphanumerics replaced by `-`.

- [ ] **Step 1: Write the failing tests**

`tests/test_project.py`:

```python
import textwrap

import pytest

from reasonhold.authority import DEFAULT_LADDER
from reasonhold.errors import ManifestInvalid
from reasonhold.project import EmbeddingConfig, Project
from reasonhold.settings import weaviate_settings_from_env

LEGACY = """\
global:
  checks: [source-layout]
  docs: [docs/architecture/overview.md]
  archival: [docs/old.md]
  index: [AGENTS.md, sync-doc.yaml]
areas:
  worker:
    description: Worker
    projects: [worker]
    docs: [docs/specs/worker.md]
    index: ["src/worker/**/*.py"]
    checks: [worker-contract]
checks:
  worker-contract:
    description: Worker follows its spec
    mode: index
    reads: [docs/specs/worker.md]
    validates_against: [src/worker/]
"""


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))
    return path


def test_legacy_manifest_loads_with_defaults(tmp_path):
    write(tmp_path, "sync-doc.yaml", LEGACY)
    p = Project.load(tmp_path)
    assert p.manifest_rel == "sync-doc.yaml"
    assert p.ladder == DEFAULT_LADDER
    assert p.embedding == EmbeddingConfig()
    assert p.id == tmp_path.name.lower().replace("_", "-")
    assert p.decisions_rel == "decisions.jsonl"
    assert p.pending_rel == "reasonhold.pending.jsonl"
    assert p.branch_isolation is True
    assert p.manifest.global_docs == ("docs/architecture/overview.md",)
    assert p.manifest.global_archival == ("docs/old.md",)
    assert p.manifest.check("worker-contract").reads == ("docs/specs/worker.md",)
    assert p.manifest.areas[0].checks == ("worker-contract",)


def test_legacy_decision_log_location_is_honored(tmp_path):
    write(tmp_path, "sync-doc.yaml", LEGACY)
    write(tmp_path, "docs-rag/decisions.jsonl", "")
    assert Project.load(tmp_path).decisions_rel == "docs-rag/decisions.jsonl"


def test_reasonhold_yaml_wins_and_reads_new_blocks(tmp_path):
    write(tmp_path, "sync-doc.yaml", LEGACY)
    write(tmp_path, "reasonhold.yaml", LEGACY + """\
project:
  id: Ariadne
  decisions: docs/decisions.jsonl
  embedding: {provider: openai_compatible, model: m, base_url: "http://h:1/v1", api_key_env: KEY}
  index: {branch_isolation: false}
authority:
  - {level: architecture, paths: ["docs/architecture/**"], weight: 0.08}
""")
    p = Project.load(tmp_path)
    assert p.manifest_rel == "reasonhold.yaml" and p.id == "ariadne"
    assert p.decisions_rel == "docs/decisions.jsonl"
    assert p.embedding == EmbeddingConfig("openai_compatible", "m", "http://h:1/v1", "KEY")
    assert p.branch_isolation is False and p.ladder[0].level == "architecture"


def test_corpus_globs_include_the_decision_log(tmp_path):
    write(tmp_path, "sync-doc.yaml", LEGACY)
    assert Project.load(tmp_path).corpus_globs()[-1] == "decisions.jsonl"


def test_missing_manifest_is_manifest_invalid(tmp_path):
    with pytest.raises(ManifestInvalid):
        Project.load(tmp_path)


@pytest.mark.parametrize("bad", ["/etc/passwd", "../outside.md", "docs/../../x.md"])
def test_manifest_rejects_escaping_paths(tmp_path, bad):
    write(tmp_path, "sync-doc.yaml", LEGACY.replace("docs/old.md", bad))
    with pytest.raises(ManifestInvalid):
        Project.load(tmp_path)


def test_bad_check_mode_is_rejected(tmp_path):
    write(tmp_path, "sync-doc.yaml", LEGACY.replace("mode: index", "mode: vector"))
    with pytest.raises(ManifestInvalid):
        Project.load(tmp_path)


def test_weaviate_settings_from_env():
    s = weaviate_settings_from_env({"REASONHOLD_WEAVIATE_PORT": "9000", "DOCS_RAG_WEAVIATE_HOST": "h"})
    assert (s.host, s.http_port, s.grpc_port, s.cloud_url) == ("h", 9000, 50052, None)
    c = weaviate_settings_from_env({"REASONHOLD_WEAVIATE_CLOUD_URL": "https://x.weaviate.cloud", "REASONHOLD_WEAVIATE_API_KEY_ENV": "K"})
    assert c.cloud_url == "https://x.weaviate.cloud" and c.api_key_env == "K"
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_project.py -q`
Expected: collection error, `No module named 'reasonhold.project'`.

- [ ] **Step 3: Implement `settings.py`**

```python
"""Weaviate connection settings. Environment only: they describe the machine,
not the project, so they never live in the committed manifest."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class WeaviateSettings:
    host: str = "localhost"
    http_port: int = 8081
    grpc_port: int = 50052
    cloud_url: str | None = None
    api_key_env: str = "WEAVIATE_API_KEY"


def _get(env: Mapping[str, str], name: str, default: str | None) -> str | None:
    return env.get(f"REASONHOLD_{name}") or env.get(f"DOCS_RAG_{name}") or default


def weaviate_settings_from_env(environ: Mapping[str, str] | None = None) -> WeaviateSettings:
    env = os.environ if environ is None else environ
    return WeaviateSettings(
        host=_get(env, "WEAVIATE_HOST", "localhost"),
        http_port=int(_get(env, "WEAVIATE_PORT", "8081")),
        grpc_port=int(_get(env, "WEAVIATE_GRPC_PORT", "50052")),
        cloud_url=env.get("REASONHOLD_WEAVIATE_CLOUD_URL") or None,
        api_key_env=env.get("REASONHOLD_WEAVIATE_API_KEY_ENV") or "WEAVIATE_API_KEY",
    )
```

- [ ] **Step 4: Extend `manifest.py`**

Keep the seed's `AreaManifest`, `Manifest.infer_area`, `Manifest.infer_project`, `_select_areas`, `_matches_area`, `_require_string_list` and `_dedupe` exactly. Apply these changes:

1. Remove `from reasonhold.config import ...`. Add `from collections.abc import Sequence`, `from dataclasses import field`, `from reasonhold.errors import ManifestInvalid`.
2. `_require_string_list` raises `ManifestInvalid` instead of `ValueError` (same messages), and rejects escaping paths:

```python
def _safe(value: str, label: str) -> str:
    if value.startswith("/") or value.startswith("..") or "/../" in value or value.endswith("/.."):
        raise ManifestInvalid(f"{label}: path {value!r} must be relative to the repository and stay inside it")
    return value
```

   Every string returned by `_require_string_list` and `_optional_string_list` passes through `_safe`.
3. Add the new dataclass and fields shown in Interfaces. `AreaManifest.checks` defaults to `()`.
4. `iter_corpus_globs(self, area_names=None, extra=())`: same body as the seed except the `DECISIONS_FILE` lines are replaced by `globs.extend(extra)`.
5. Add `check(self, name)` returning the `CheckSpec` with that name or `None`.
6. `load_manifest(path)`: `path` is required. Read with `yaml.safe_load`; a YAML error raises `ManifestInvalid(f"{path.name}: {exc}")`. Seed validation stays (messages now say the file name instead of `sync-doc.yaml`). Additionally parse:

```python
def _optional_string_list(section: dict, key: str, label: str, *, paths: bool = True) -> tuple[str, ...]:
    value = section.get(key)
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise ManifestInvalid(f"{label} must be a list of non-empty strings")
    return tuple(_safe(v, label) for v in value) if paths else tuple(value)


def _parse_checks(raw: object, name: str) -> tuple[CheckSpec, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        raise ManifestInvalid(f"{name}: 'checks' must be a mapping")
    checks = []
    for check_name, body in raw.items():
        label = f"checks.{check_name}"
        if not isinstance(body, dict):
            raise ManifestInvalid(f"{label} must be a mapping")
        mode = body.get("mode", "index")
        if mode not in ("index", "fs"):
            raise ManifestInvalid(f"{label}.mode must be 'index' or 'fs'")
        checks.append(
            CheckSpec(
                name=str(check_name),
                description=str(body.get("description", "")),
                mode=mode,
                reads=_optional_string_list(body, "reads", f"{label}.reads"),
                validates_against=_optional_string_list(body, "validates_against", f"{label}.validates_against"),
            )
        )
    return tuple(checks)
```

   `global.docs` and `global.archival` use `_optional_string_list`; `global.checks` and `areas.<n>.checks` are optional name lists, parsed with `_optional_string_list(..., paths=False)` (names, not paths, so not passed through `_safe`). `project_raw = data.get("project") or {}` (must be a mapping), `authority_raw = data.get("authority")`.

- [ ] **Step 5: Implement `project.py`**

```python
"""The project ReasonHold answers about: one repository root and its manifest."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from reasonhold.authority import DEFAULT_LADDER, AuthorityRule, parse_ladder
from reasonhold.errors import ManifestInvalid
from reasonhold.manifest import Manifest, load_manifest

MANIFEST_NAMES = ("reasonhold.yaml", "sync-doc.yaml")
LEGACY_DECISIONS = "docs-rag/decisions.jsonl"


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str = "ollama"
    model: str = "qwen3-embedding:0.6b"
    base_url: str = "http://localhost:11434"
    api_key_env: str | None = None


@dataclass(frozen=True)
class Project:
    root: Path
    manifest_path: Path
    manifest: Manifest
    id: str
    decisions_path: Path
    pending_path: Path
    embedding: EmbeddingConfig
    branch_isolation: bool
    ladder: tuple[AuthorityRule, ...]

    @property
    def manifest_rel(self) -> str:
        return self.rel(self.manifest_path)

    @property
    def decisions_rel(self) -> str:
        return self.rel(self.decisions_path)

    @property
    def pending_rel(self) -> str:
        return self.rel(self.pending_path)

    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def corpus_globs(self, area_names: set[str] | None = None) -> list[str]:
        return self.manifest.iter_corpus_globs(area_names, extra=[self.decisions_rel])

    @classmethod
    def load(cls, root: Path | str | None = None) -> "Project":
        base = Path(root or Path.cwd()).resolve()
        manifest_path = next((base / n for n in MANIFEST_NAMES if (base / n).is_file()), None)
        if manifest_path is None:
            raise ManifestInvalid(f"no reasonhold.yaml or sync-doc.yaml in {base}")
        manifest = load_manifest(manifest_path)
        raw = manifest.project_raw
        if not isinstance(raw, dict):
            raise ManifestInvalid("'project' must be a mapping")

        project_id = _slug(str(raw.get("id") or base.name))
        decisions_rel = raw.get("decisions")
        if not decisions_rel:
            legacy = manifest_path.name == "sync-doc.yaml" and (base / LEGACY_DECISIONS).is_file()
            decisions_rel = LEGACY_DECISIONS if legacy else "decisions.jsonl"
        pending_rel = raw.get("pending") or (manifest_path.parent / "reasonhold.pending.jsonl").relative_to(base).as_posix()
        for label, value in (("project.decisions", decisions_rel), ("project.pending", pending_rel)):
            if not isinstance(value, str) or value.startswith("/") or ".." in Path(value).parts:
                raise ManifestInvalid(f"{label} must be a relative path inside the repository")

        emb = raw.get("embedding") or {}
        if not isinstance(emb, dict):
            raise ManifestInvalid("project.embedding must be a mapping")
        defaults = EmbeddingConfig()
        embedding = EmbeddingConfig(
            provider=str(emb.get("provider", defaults.provider)),
            model=str(emb.get("model", defaults.model)),
            base_url=str(emb.get("base_url", defaults.base_url)),
            api_key_env=emb.get("api_key_env"),
        )
        if embedding.provider not in ("ollama", "openai_compatible"):
            raise ManifestInvalid("project.embedding.provider must be 'ollama' or 'openai_compatible'")

        index_cfg = raw.get("index") or {}
        ladder = DEFAULT_LADDER if manifest.authority_raw is None else parse_ladder(manifest.authority_raw)
        return cls(
            root=base,
            manifest_path=manifest_path,
            manifest=manifest,
            id=project_id,
            decisions_path=base / decisions_rel,
            pending_path=base / pending_rel,
            embedding=embedding,
            branch_isolation=bool(index_cfg.get("branch_isolation", True)),
            ladder=ladder,
        )


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise ManifestInvalid("project id is empty after normalization")
    return slug
```

- [ ] **Step 6: Make enrichment ladder-driven, keeping seed call sites working**

In `enrichment.py`: remove `_classify_authority`, `_DEPLOYMENT_ROOT_FILES`, `_TOOLING_PREFIXES`. Replace `enrich_chunk` and `_file_type`:

```python
from reasonhold.authority import DEFAULT_LADDER, classify


def enrich_chunk(
    chunk: dict[str, object],
    manifest: Manifest,
    *,
    ladder=DEFAULT_LADDER,
    decisions_rel: str | None = "docs-rag/decisions.jsonl",
    manifest_rel: str | None = "sync-doc.yaml",
) -> dict[str, object]:
    enriched = dict(chunk)
    file_path = str(enriched["file_path"])
    enriched.setdefault("file_type", file_type_for(file_path, decisions_rel))
    enriched.setdefault("area", manifest.infer_area(file_path))
    enriched.setdefault("project", manifest.infer_project(file_path))
    level, kind = classify(file_path, ladder, decisions_rel=decisions_rel, manifest_rel=manifest_rel)
    enriched.setdefault("authority_level", level)
    enriched.setdefault("document_kind", kind)
    return enriched


def enrich_for_project(chunk: dict[str, object], project) -> dict[str, object]:
    return enrich_chunk(
        chunk,
        project.manifest,
        ladder=project.ladder,
        decisions_rel=project.decisions_rel,
        manifest_rel=project.manifest_rel,
    )


def file_type_for(file_path: str, decisions_rel: str | None) -> str:
    if decisions_rel and file_path == decisions_rel:
        return "decisions"
    suffix = PurePosixPath(file_path).suffix.lower()
    return {
        ".md": "markdown", ".cs": "csharp", ".py": "python", ".sql": "sql",
        ".yaml": "yaml", ".yml": "yaml", ".jsonl": "jsonl",
    }.get(suffix, "text")
```

- [ ] **Step 7: Adapt the seed tests to the new signatures**

- `tests/test_manifest.py`: call sites that relied on the implicit decisions path now pass it: `manifest.iter_corpus_globs(extra=["docs-rag/decisions.jsonl"])` where the test expected that entry; `ValueError` expectations become `ManifestInvalid`.
- `tests/test_enrichment.py`: replace `from reasonhold.enrichment import _classify_authority` with a local helper and use it everywhere `_classify_authority(path)` appeared:

```python
from reasonhold.authority import DEFAULT_LADDER, classify


def _classify_authority(path):
    return classify(path, DEFAULT_LADDER, decisions_rel="docs-rag/decisions.jsonl", manifest_rel="sync-doc.yaml")
```

- Seed code that still imports `reasonhold.config` keeps working: `index.py` calls `enrich_chunk(chunk, manifest)` with the seed defaults until Task 8. Seed call sites of `load_manifest()` with no argument (`index.main`, `symbols.scan_working_tree`) become `load_manifest(SYNC_DOC_PATH)`, importing `SYNC_DOC_PATH` from `reasonhold.config`.

- [ ] **Step 8: Run the tests and the whole suite**

Run: `.venv/bin/pytest -q`
Expected: all seed tests and the new project tests pass.

- [ ] **Step 9: Commit**

```bash
git add -A && git commit -q -m "Manifest v1 (checks, global docs, project and authority blocks), Project and settings"
```

---

### Task 4: Git identity and collection naming

**Files:**
- Create: `src/reasonhold/identity.py`, `tests/test_identity.py`

**Interfaces:**
- Produces:

```python
NO_GIT_BRANCH = "no-git"
def git(root: Path, *args: str, timeout: float = 5.0) -> str | None   # stdout stripped, None on any failure
def current_branch(root: Path) -> str          # branch, "detached-<short sha>", or NO_GIT_BRANCH
def head_commit(root: Path) -> str | None
def is_ancestor(root: Path, older: str, newer: str) -> bool
def merges_between(root: Path, older: str, newer: str) -> list[str]
def changed_since(root: Path, older: str, rel_path: str) -> bool   # file differs between older and the working tree
def local_branches(root: Path) -> set[str]
def default_branch(root: Path) -> str          # origin HEAD if known, else "main" if it exists, else current branch
def collection_name(project_id: str, branch: str) -> str
```

Every subprocess runs with `stdin=subprocess.DEVNULL`, a timeout, and `cwd=root`.

- [ ] **Step 1: Write the failing tests**

`tests/test_identity.py`:

```python
import re
import subprocess

import pytest

from reasonhold.identity import (
    NO_GIT_BRANCH,
    changed_since,
    collection_name,
    current_branch,
    head_commit,
    is_ancestor,
    local_branches,
    merges_between,
)

NAME = re.compile(r"^[A-Z][A-Za-z0-9_]*$")


def run(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, stdin=subprocess.DEVNULL)


@pytest.fixture
def repo(tmp_path):
    run(tmp_path, "init", "-q", "-b", "main")
    run(tmp_path, "config", "user.email", "t@example.com")
    run(tmp_path, "config", "user.name", "t")
    (tmp_path / "a.md").write_text("one\n")
    run(tmp_path, "add", "a.md")
    run(tmp_path, "commit", "-q", "-m", "one")
    return tmp_path


def test_branch_and_head(repo):
    assert current_branch(repo) == "main"
    assert len(head_commit(repo)) == 40


def test_detached_head(repo):
    run(repo, "checkout", "-q", "--detach")
    assert current_branch(repo).startswith("detached-")


def test_non_git_directory_uses_no_git_branch(tmp_path):
    assert current_branch(tmp_path) == NO_GIT_BRANCH
    assert head_commit(tmp_path) is None


def test_merges_and_ancestry(repo):
    base = head_commit(repo)
    run(repo, "checkout", "-q", "-b", "feat")
    (repo / "b.md").write_text("b\n")
    run(repo, "add", "b.md")
    run(repo, "commit", "-q", "-m", "b")
    run(repo, "checkout", "-q", "main")
    (repo / "c.md").write_text("c\n")
    run(repo, "add", "c.md")
    run(repo, "commit", "-q", "-m", "c")
    run(repo, "merge", "-q", "--no-ff", "feat", "-m", "merge feat")
    assert merges_between(repo, base, head_commit(repo))
    assert is_ancestor(repo, base, head_commit(repo))
    assert not is_ancestor(repo, head_commit(repo), base)
    assert local_branches(repo) == {"main", "feat"}


def test_changed_since(repo):
    base = head_commit(repo)
    assert not changed_since(repo, base, "a.md")
    (repo / "a.md").write_text("two\n")
    assert changed_since(repo, base, "a.md")


@pytest.mark.parametrize("branch", ["main", "feat/a-b", "feat/a_b", "Feat/A.b", "ünïcode", "x" * 300, "detached-abc1234"])
def test_collection_names_are_valid(branch):
    name = collection_name("ariadne", branch)
    assert NAME.match(name) and name.startswith("RH_Ariadne__") and len(name) <= 100


def test_collection_names_are_valid_and_distinct():
    names = {collection_name("ariadne", b) for b in ["feat/a-b", "feat/a_b", "feat-a-b", "Feat/A-B", "main"]}
    assert len(names) == 5
    assert collection_name("ariadne", "main") == "RH_Ariadne__main"
    assert NAME.match(collection_name("9lives", "main"))
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_identity.py -q`
Expected: collection error, `No module named 'reasonhold.identity'`.

- [ ] **Step 3: Implement `identity.py`**

```python
"""Git facts about the checkout, and the collection name derived from them."""

from __future__ import annotations

import hashlib
import re
import subprocess
import unicodedata
from pathlib import Path

NO_GIT_BRANCH = "no-git"
MAX_NAME = 100


def git(root: Path, *args: str, timeout: float = 5.0) -> str | None:
    try:
        done = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def head_commit(root: Path) -> str | None:
    return git(root, "rev-parse", "--verify", "-q", "HEAD")


def current_branch(root: Path) -> str:
    branch = git(root, "symbolic-ref", "--short", "-q", "HEAD")
    if branch:
        return branch
    head = git(root, "rev-parse", "--short", "--verify", "-q", "HEAD")
    return f"detached-{head}" if head else NO_GIT_BRANCH


def is_ancestor(root: Path, older: str, newer: str) -> bool:
    try:
        done = subprocess.run(
            ["git", "merge-base", "--is-ancestor", older, newer],
            cwd=root, capture_output=True, timeout=5.0, stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


def merges_between(root: Path, older: str, newer: str) -> list[str]:
    out = git(root, "rev-list", "--merges", f"{older}..{newer}")
    return out.split() if out else []


def changed_since(root: Path, older: str, rel_path: str) -> bool:
    try:
        done = subprocess.run(
            ["git", "diff", "--quiet", older, "--", rel_path],
            cwd=root, capture_output=True, timeout=5.0, stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return True
    return done.returncode != 0


def local_branches(root: Path) -> set[str]:
    out = git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    return set(out.split()) if out else set()


def default_branch(root: Path) -> str:
    ref = git(root, "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD")
    if ref and "/" in ref:
        return ref.split("/", 1)[1]
    branches = local_branches(root)
    return "main" if "main" in branches else current_branch(root)


def _sanitize(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9_]", "_", ascii_value)).strip("_")


def collection_name(project_id: str, branch: str) -> str:
    project = _sanitize(project_id) or "P"
    project = project[0].upper() + project[1:]
    if not project[0].isalpha():
        project = "P" + project
    slug = _sanitize(branch) or "branch"
    lossy = slug != branch
    name = f"RH_{project}__{slug}"
    if lossy or len(name) > MAX_NAME:
        digest = hashlib.sha256(branch.encode()).hexdigest()[:8]
        name = f"{name[: MAX_NAME - 9]}_{digest}"
    return name
```

- [ ] **Step 4: Run the tests and the suite**

Run: `.venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -q -m "Git identity helpers and branch-aware collection naming"
```

---

### Task 5: Store (connection factory, collection metadata) and embedding providers

**Files:**
- Create: `src/reasonhold/store.py`, `src/reasonhold/embedding.py`, `tests/test_store.py`, `tests/test_embedding.py`
- Modify: `src/reasonhold/schema.py` (properties only), `tests/test_full_reindex_semantics.py`

**Interfaces:**
- Consumes: `WeaviateSettings`, `weaviate_settings_from_env` (Task 3); `EmbeddingConfig` (Task 3); errors (Task 2).
- Produces:

```python
# schema.py (trimmed: properties only)
EXPECTED_PROPERTIES: set[str]          # seed set plus "record_id"
def collection_properties() -> list[wvc.Property]
def collection_matches_expected_schema(client, name: str) -> bool     # property names only

# store.py
META_PREFIX = "reasonhold-meta:"
@dataclass
class CollectionMeta:
    project: str
    branch: str
    model_id: str
    dims: int
    manifest_sha256: str = ""
    authority_sha256: str = ""
    retraction_sha256: str = ""
    indexed_commit: str | None = None
    last_full_index: str | None = None
    def to_description(self) -> str
    @classmethod
    def from_description(cls, text: str | None) -> "CollectionMeta | None"
def connect(settings: WeaviateSettings | None = None) -> weaviate.WeaviateClient    # StoreUnavailable on failure
def read_meta(client, name: str) -> CollectionMeta | None
def write_meta(client, name: str, meta: CollectionMeta) -> None
def create_collection(client, name: str, meta: CollectionMeta) -> None
def drop_collection(client, name: str) -> None
def ensure_collection(client, name: str, meta: CollectionMeta, recreate: bool = False) -> None
def list_collections(client, prefix: str) -> list[str]

# embedding.py
class EmbeddingProvider(Protocol):
    model_id: str
    @property
    def dims(self) -> int: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...
class OllamaProvider:                          # POST {base_url}/api/embed
    def __init__(self, model: str, base_url: str, batch_size: int = 8, char_budget: int = 12000,
                 timeout: float = 120.0, post: Callable[[str, dict], dict] | None = None)
class OpenAICompatibleProvider:                # POST {base_url}/embeddings
    def __init__(self, model: str, base_url: str, api_key_env: str | None = None, batch_size: int = 32,
                 char_budget: int = 12000, timeout: float = 120.0, post: Callable[[str, dict], dict] | None = None)
def make_provider(config: EmbeddingConfig) -> EmbeddingProvider
def check_model(meta: CollectionMeta | None, provider: EmbeddingProvider) -> None    # ModelMismatch
```

`model_id` is `"ollama:<model>"` or `"openai_compatible:<base_url>|<model>"`. `dims` is probed once by embedding `"dimension probe"` and cached. Network errors and non-2xx responses raise `StoreUnavailable` naming the URL.

- [ ] **Step 1: Write the failing tests**

`tests/test_embedding.py`:

```python
import pytest

from reasonhold.embedding import OllamaProvider, OpenAICompatibleProvider, check_model, make_provider
from reasonhold.errors import ModelMismatch, StoreUnavailable
from reasonhold.project import EmbeddingConfig
from reasonhold.store import CollectionMeta


class FakePost:
    def __init__(self, dims=4, fail=False):
        self.dims, self.fail, self.calls = dims, fail, []

    def __call__(self, url, payload):
        self.calls.append((url, payload))
        if self.fail:
            raise StoreUnavailable(f"cannot reach {url}")
        texts = payload.get("input")
        if "/api/embed" in url:
            return {"embeddings": [[0.1] * self.dims for _ in texts]}
        return {"data": [{"embedding": [0.1] * self.dims, "index": i} for i, _ in enumerate(texts)]}


def test_ollama_batches_and_truncates():
    post = FakePost()
    p = OllamaProvider("qwen3-embedding:0.6b", "http://h:11434", batch_size=2, char_budget=5, post=post)
    out = p.embed(["abcdefgh", "b", "c"])
    assert len(out) == 3 and len(post.calls) == 2
    assert post.calls[0][0] == "http://h:11434/api/embed"
    assert post.calls[0][1]["input"] == ["abcde", "b"]
    assert p.model_id == "ollama:qwen3-embedding:0.6b"


def test_openai_compatible_shape():
    post = FakePost(dims=3)
    p = OpenAICompatibleProvider("m", "http://h/v1", post=post)
    assert p.embed(["x"]) == [[0.1, 0.1, 0.1]] and post.calls[0][0] == "http://h/v1/embeddings"
    assert p.model_id == "openai_compatible:http://h/v1|m"


def test_dims_probed_once():
    post = FakePost(dims=7)
    p = OllamaProvider("m", "http://h", post=post)
    assert p.dims == 7 and p.dims == 7 and len(post.calls) == 1


def test_unreachable_provider_is_store_unavailable():
    with pytest.raises(StoreUnavailable):
        OllamaProvider("m", "http://h", post=FakePost(fail=True)).embed(["x"])


def test_make_provider():
    assert isinstance(make_provider(EmbeddingConfig()), OllamaProvider)
    assert isinstance(make_provider(EmbeddingConfig("openai_compatible", "m", "http://h/v1")), OpenAICompatibleProvider)


def test_model_guard():
    p = OllamaProvider("m", "http://h", post=FakePost(dims=4))
    check_model(None, p)
    check_model(CollectionMeta("p", "main", "ollama:m", 4), p)
    with pytest.raises(ModelMismatch, match="index --full"):
        check_model(CollectionMeta("p", "main", "ollama:other", 4), p)
    with pytest.raises(ModelMismatch):
        check_model(CollectionMeta("p", "main", "ollama:m", 8), p)
```

`tests/test_store.py`:

```python
from reasonhold.schema import EXPECTED_PROPERTIES
from reasonhold.store import CollectionMeta, ensure_collection


def test_meta_round_trip():
    meta = CollectionMeta("ariadne", "main", "ollama:m", 1024, "a", "b", "c", "deadbeef", "2026-10-01T00:00:00+00:00")
    assert CollectionMeta.from_description(meta.to_description()) == meta
    assert CollectionMeta.from_description("Some human description") is None
    assert CollectionMeta.from_description(None) is None


def test_record_id_property_added():
    assert "record_id" in EXPECTED_PROPERTIES and "file_path" in EXPECTED_PROPERTIES


class FakeCollections:
    def __init__(self, existing):
        self.names = set(existing)
        self.calls = []

    def exists(self, name):
        return name in self.names


class FakeClient:
    def __init__(self, existing=()):
        self.collections = FakeCollections(existing)


def test_ensure_creates_missing(monkeypatch):
    import reasonhold.store as store

    calls = []
    monkeypatch.setattr(store, "create_collection", lambda c, n, m: calls.append(("create", n)))
    ensure_collection(FakeClient(), "RH_X__main", CollectionMeta("x", "main", "ollama:m", 4))
    assert calls == [("create", "RH_X__main")]


def test_ensure_recreate_drops_then_creates(monkeypatch):
    import reasonhold.store as store

    calls = []
    monkeypatch.setattr(store, "drop_collection", lambda c, n: calls.append(("drop", n)))
    monkeypatch.setattr(store, "create_collection", lambda c, n, m: calls.append(("create", n)))
    ensure_collection(FakeClient({"RH_X__main"}), "RH_X__main", CollectionMeta("x", "main", "ollama:m", 4), recreate=True)
    assert calls == [("drop", "RH_X__main"), ("create", "RH_X__main")]
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_embedding.py tests/test_store.py -q`
Expected: collection errors, modules not found.

- [ ] **Step 3: Trim `schema.py` to properties**

Keep the seed's `EXPECTED_PROPERTIES` and the property list, renamed `collection_properties()` (public). Add to both:

```python
        wvc.Property(
            name="record_id",
            data_type=wvc.DataType.TEXT,
            description="Decision or pending record id for record chunks; empty for document and code chunks.",
            index_searchable=False,
            index_filterable=True,
            tokenization=wvc.Tokenization.FIELD,
        ),
```

Replace `collection_matches_expected_schema` with a version that takes the collection name and compares property names only (dimension checks move to the model guard):

```python
def collection_matches_expected_schema(client, name: str) -> bool:
    if not client.collections.exists(name):
        return False
    config = client.collections.get(name).config.get(simple=False)
    return {prop.name for prop in config.properties} == EXPECTED_PROPERTIES
```

Remove `get_client`, `create_collection`, `drop_collection`, `ensure_collection` and the `__main__` block from `schema.py` (they move to `store.py`). Delete `schema.py`'s `from reasonhold.config import ...` line; it no longer needs any of those names. Seed modules that imported `get_client` from `schema` (`index.py`, `symbols.py`) switch to `from reasonhold.store import connect as get_client` until Tasks 8 and 11 replace them. In `index.py`, replace `from reasonhold.schema import ensure_collection, get_client` with `from reasonhold.store import CollectionMeta, ensure_collection, connect as get_client`, add `EMBEDDING_DIMS` to its `reasonhold.config` import list, and change its `ensure_collection(client, recreate=...)` call to `ensure_collection(client, COLLECTION_NAME, CollectionMeta("seed", "seed", "ollama:" + EMBEDDING_MODEL, EMBEDDING_DIMS), recreate=...)`. `backfill_decisions.py` still imports the removed schema functions and stays import-broken until Task 8 deletes it; nothing imports it and no test covers it, so leave it.

- [ ] **Step 4: Implement `store.py`**

```python
"""Weaviate access: one connection factory (local or Cloud), collection
lifecycle, and per-collection metadata kept in the collection description."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

import weaviate
import weaviate.classes.config as wvc

from reasonhold.errors import ReasonHoldError, StoreUnavailable
from reasonhold.schema import collection_matches_expected_schema, collection_properties
from reasonhold.settings import WeaviateSettings, weaviate_settings_from_env

META_PREFIX = "reasonhold-meta:"


@dataclass
class CollectionMeta:
    project: str
    branch: str
    model_id: str
    dims: int
    manifest_sha256: str = ""
    authority_sha256: str = ""
    retraction_sha256: str = ""
    indexed_commit: str | None = None
    last_full_index: str | None = None

    def to_description(self) -> str:
        return META_PREFIX + json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_description(cls, text: str | None) -> "CollectionMeta | None":
        if not text or not text.startswith(META_PREFIX):
            return None
        try:
            return cls(**json.loads(text[len(META_PREFIX):]))
        except (ValueError, TypeError):
            return None


def connect(settings: WeaviateSettings | None = None) -> weaviate.WeaviateClient:
    s = settings or weaviate_settings_from_env()
    try:
        if s.cloud_url:
            key = os.environ.get(s.api_key_env, "")
            return weaviate.connect_to_weaviate_cloud(
                cluster_url=s.cloud_url, auth_credentials=weaviate.auth.AuthApiKey(key)
            )
        return weaviate.connect_to_custom(
            http_host=s.host, http_port=s.http_port, http_secure=False,
            grpc_host=s.host, grpc_port=s.grpc_port, grpc_secure=False,
        )
    except Exception as exc:  # the client raises several unrelated types on connect
        where = s.cloud_url or f"{s.host}:{s.http_port}"
        raise StoreUnavailable(f"cannot reach Weaviate at {where}: {exc}") from exc


def read_meta(client, name: str) -> CollectionMeta | None:
    if not client.collections.exists(name):
        return None
    return CollectionMeta.from_description(client.collections.get(name).config.get().description)


def write_meta(client, name: str, meta: CollectionMeta) -> None:
    client.collections.get(name).config.update(description=meta.to_description())


def create_collection(client, name: str, meta: CollectionMeta) -> None:
    client.collections.create(
        name=name,
        description=meta.to_description(),
        vectorizer_config=wvc.Configure.Vectorizer.none(),
        vector_index_config=wvc.Configure.VectorIndex.hnsw(distance_metric=wvc.VectorDistances.COSINE),
        properties=collection_properties(),
    )


def drop_collection(client, name: str) -> None:
    if client.collections.exists(name):
        client.collections.delete(name)


def ensure_collection(client, name: str, meta: CollectionMeta, recreate: bool = False) -> None:
    if not client.collections.exists(name):
        create_collection(client, name, meta)
        return
    if recreate:
        # Recreate, never reuse: delete-then-insert on the same deterministic
        # UUIDs raced Weaviate's asynchronous deletes in the seed.
        drop_collection(client, name)
        create_collection(client, name, meta)
        return
    if not collection_matches_expected_schema(client, name):
        # Drift on an incremental run is never silently repaired (R-17).
        raise ReasonHoldError(f"{name}: schema drift detected; run `reasonhold index --full` to recreate it")


def list_collections(client, prefix: str) -> list[str]:
    return sorted(n for n in client.collections.list_all(simple=True) if n.startswith(prefix))
```

- [ ] **Step 5: Implement `embedding.py`**

```python
"""Embedding providers (R-15) and the model guard (R-16). Plain HTTP, no SDKs."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Protocol

from reasonhold.errors import ModelMismatch, StoreUnavailable
from reasonhold.project import EmbeddingConfig
from reasonhold.store import CollectionMeta

Post = Callable[[str, dict], dict]


def _http_post(timeout: float, headers: dict[str, str] | None = None) -> Post:
    def post(url: str, payload: dict) -> dict:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", **(headers or {})}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise StoreUnavailable(f"embedding request to {url} failed: {exc}") from exc

    return post


class EmbeddingProvider(Protocol):
    model_id: str

    @property
    def dims(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class _Base:
    batch_size: int
    char_budget: int
    _dims: int | None = None

    def _batch_embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            out.extend(self._batch_embed([t[: self.char_budget] for t in texts[i : i + self.batch_size]]))
        return out

    @property
    def dims(self) -> int:
        if self._dims is None:
            self._dims = len(self.embed(["dimension probe"])[0])
        return self._dims


class OllamaProvider(_Base):
    def __init__(self, model, base_url, batch_size=8, char_budget=12000, timeout=120.0, post=None):
        self.model, self.base_url = model, base_url.rstrip("/")
        self.batch_size, self.char_budget = batch_size, char_budget
        self.model_id = f"ollama:{model}"
        self._post = post or _http_post(timeout)

    def _batch_embed(self, texts):
        return self._post(f"{self.base_url}/api/embed", {"model": self.model, "input": texts, "truncate": True})["embeddings"]


class OpenAICompatibleProvider(_Base):
    def __init__(self, model, base_url, api_key_env=None, batch_size=32, char_budget=12000, timeout=120.0, post=None):
        self.model, self.base_url = model, base_url.rstrip("/")
        self.batch_size, self.char_budget = batch_size, char_budget
        self.model_id = f"openai_compatible:{self.base_url}|{model}"
        headers = {"Authorization": f"Bearer {os.environ[api_key_env]}"} if api_key_env and os.environ.get(api_key_env) else None
        self._post = post or _http_post(timeout, headers)

    def _batch_embed(self, texts):
        data = self._post(f"{self.base_url}/embeddings", {"model": self.model, "input": texts})["data"]
        return [row["embedding"] for row in sorted(data, key=lambda r: r["index"])]


def make_provider(config: EmbeddingConfig) -> EmbeddingProvider:
    if config.provider == "openai_compatible":
        return OpenAICompatibleProvider(config.model, config.base_url, config.api_key_env)
    return OllamaProvider(config.model, config.base_url)


def check_model(meta: CollectionMeta | None, provider: EmbeddingProvider) -> None:
    if meta is None:
        return
    if meta.model_id != provider.model_id or meta.dims != provider.dims:
        raise ModelMismatch(
            f"index built with {meta.model_id} ({meta.dims} dims) but the project is configured for "
            f"{provider.model_id} ({provider.dims} dims); run `reasonhold index --full`"
        )
```

- [ ] **Step 6: Adapt `tests/test_full_reindex_semantics.py`**

Its monkeypatches move from `reasonhold.schema` to `reasonhold.store` (patch the names as `store` sees them) and gain the new arguments: `lambda c, n: True` for `collection_matches_expected_schema`, `lambda c, n: calls.append("drop")` for `drop_collection`, `lambda c, n, m: calls.append("create")` for `create_collection`. Its `schema_mod.ensure_collection(FakeClient(exists=...), recreate=...)` calls become `store_mod.ensure_collection(FakeClient(exists=...), "RH_T__main", CollectionMeta("t", "main", "ollama:m", 4), recreate=...)`. In `tests/test_file_path_exact_match.py`, `schema_mod._collection_properties()` becomes `schema_mod.collection_properties()`; that test's tokenization assertions are otherwise unchanged.

- [ ] **Step 7: Run the tests and the suite**

Run: `.venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -q -m "Store connection factory and collection metadata; Ollama and OpenAI-compatible embedding providers with the model guard"
```

---

### Task 6: Decision log v2, `store_decision` and the audit

**Files:**
- Create: `src/reasonhold/jsonl.py`, `src/reasonhold/decisions.py`, `src/reasonhold/writes.py`, `tests/helpers.py`, `tests/test_decisions.py`, `tests/test_writes.py`
- Move: `src/reasonhold/audit_supersedes.py` to `src/reasonhold/audit.py` (`git mv`); delete `src/reasonhold/decisions_io.py`
- Modify: `src/reasonhold/chunkers.py` (`chunk_decisions`), `src/reasonhold/server.py`, `src/reasonhold/index.py`, `src/reasonhold/bootstrap.py` (imports only)
- Modify tests: `tests/test_apply_retraction_overlay.py`, `tests/test_store_decision_supersedes.py`, `tests/test_audit_supersedes.py`, `tests/test_decision_chunker.py`

**Interfaces:**
- Consumes: `Project` (Task 3); `EmbeddingProvider` (Task 5); `UnknownRecord`, `StoreUnavailable` (Task 2).
- Produces:

```python
# jsonl.py
def append_jsonl(path: Path, record: dict) -> None      # one line, newline-safe, fsync

# decisions.py
PROVENANCE_KINDS = ("human", "agent", "sendesis_run")
def decision_id(topic: str, datetime_: str) -> str
def record_id(record: dict) -> str                      # explicit id, else derived
def iter_decision_records(decisions_path: Path) -> Iterator[dict]       # seed, unchanged
def iter_supersedes_rows(decisions_path: Path) -> Iterator[tuple[str, str, str, str]]   # seed shape, computed status
@dataclass(frozen=True)
class Retraction:
    path: str                  # as written, may carry "#section"
    retraction_summary: str
    decision_id: str
    topic: str
    date: str
    file_path: str             # property: path before "#"
    section: str | None        # property: text after "#", or None
class DecisionLog:
    records: list[dict]        # every record has "id"
    @classmethod
    def load(cls, path: Path) -> "DecisionLog"
    @classmethod
    def from_text(cls, text: str) -> "DecisionLog"
    def get(self, id: str) -> dict | None
    def status(self, id: str) -> str                   # "active" | "superseded"
    def superseded_by(self, id: str) -> list[str]
    def active(self) -> list[dict]
    def retractions(self) -> list[Retraction]          # active records only, file order
    def retraction_sha256(self) -> str
def validate_supersedes(supersedes: list[dict] | None) -> list[dict]   # seed _validate_supersedes; ValueError
def validate_provenance(provenance: dict | None) -> dict               # ValueError
def format_decision_content(record: dict, status: str | None = None) -> str   # seed _format_decision_content

# writes.py
def apply_retraction_to_chunks(collection, path: str, retraction_summary: str,
                               retraction_decision: str, retraction_date: str) -> int
def mark_records_superseded(collection, record_ids: Iterable[str]) -> int
def store_decision(project, collection, provider, *, topic: str, decision: str, rationale: str,
                   alternatives_considered: list[str] | None = None, session_context: str = "",
                   tags: list[str] | None = None, status: str = "active",
                   supersedes: list[dict] | None = None, supersedes_records: list[str] | None = None,
                   provenance: dict, datetime_: str | None = None) -> dict
# returns {"record": dict, "status": str, "indexed": bool, "annotated_chunks": int, "warnings": list[str]}

# tests/helpers.py (test-only)
class FakeProvider       # model_id "ollama:fake", dims 4, embed() records calls, fail=True raises StoreUnavailable
class FakeCollection     # data.insert/insert_many/update/delete_by_id, iterator(), query.fetch_objects(), config.get()/update(), aggregate
class FakeClient         # collections.exists/get/create/delete/list_all
def write(root: Path, rel: str, text: str) -> Path
def git(root: Path, *args: str) -> str
def make_repo(root: Path, manifest: str = MINIMAL_MANIFEST, *, commit: bool = True) -> Path
MINIMAL_MANIFEST: str
```

Status rule (spec 3.2): a record is superseded when it was written with `status: superseded`, or when any record written with `status: active` lists its id in `supersedes_records`. Only active records contribute retractions. `retraction_sha256` hashes, in canonical JSON, the list of `(path, retraction_summary, decision_id)` for every retraction plus the sorted list of superseded ids; Task 9 compares it with the value stored in the collection metadata.

`store_decision` order is fixed: validate, then embed, then append, then index. Validation and embedding failures leave the log untouched. A failure while indexing after the append is a warning in the result, not an exception, because the record is already durable and the next `reasonhold index` picks it up. Passing the same `topic` and `datetime_` again returns the stored record without appending (idempotent retry).

- [ ] **Step 1: Write the test helpers**

`tests/helpers.py`:

```python
"""Test doubles and repository builders shared by the unit tests. No network."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path
from types import SimpleNamespace

from reasonhold.errors import StoreUnavailable
from reasonhold.schema import EXPECTED_PROPERTIES

MINIMAL_MANIFEST = """\
global:
  docs: [docs/architecture/overview.md]
  index: [AGENTS.md]
areas:
  worker:
    description: Worker
    projects: [worker]
    docs: [docs/specs/worker.md]
    index: ["docs/specs/*.md", "src/worker/*.py"]
    checks: [worker-contract]
checks:
  worker-contract:
    description: Worker follows its spec
    mode: index
    reads: [docs/specs/worker.md]
    validates_against: [src/worker/]
"""


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))
    return path


def git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL
    )
    return done.stdout.strip()


def make_repo(root: Path, manifest: str = MINIMAL_MANIFEST, *, commit: bool = True) -> Path:
    write(root, "sync-doc.yaml", manifest)
    write(root, "AGENTS.md", "# Agents\n")
    write(root, "docs/architecture/overview.md", "# Overview\n\n## Queue\n\nThe queue is FIFO.\n")
    write(root, "docs/specs/worker.md", "# Worker\n\n## Retries\n\nRetry three times.\n")
    write(root, "src/worker/main.py", "def run():\n    return 1\n")
    write(root, "decisions.jsonl", "")
    if commit:
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.email", "t@example.com")
        git(root, "config", "user.name", "t")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "initial")
    return root


class FakeProvider:
    model_id = "ollama:fake"

    def __init__(self, dims: int = 4, fail: bool = False):
        self._dims, self.fail, self.calls = dims, fail, []

    @property
    def dims(self) -> int:
        return self._dims

    def embed(self, texts):
        self.calls.append(list(texts))
        if self.fail:
            raise StoreUnavailable("embedding request to http://fake/api/embed failed: connection refused")
        return [[0.1] * self._dims for _ in texts]


class _Obj(SimpleNamespace):
    pass


class _Data:
    def __init__(self, owner):
        self.owner = owner

    def insert(self, properties, vector=None, uuid=None):
        if self.owner.fail_inserts:
            raise RuntimeError("insert failed")
        self.owner.objects[str(uuid)] = _Obj(uuid=str(uuid), properties=dict(properties), vector=vector)
        return uuid

    def insert_many(self, objects):
        for obj in objects:
            self.insert(obj.properties, obj.vector, obj.uuid)
        return SimpleNamespace(has_errors=False, errors={})

    def update(self, uuid, properties):
        self.owner.objects[str(uuid)].properties.update(properties)

    def delete_by_id(self, uuid):
        self.owner.objects.pop(str(uuid), None)


class _Config:
    def __init__(self, owner):
        self.owner = owner

    def get(self, simple=True):
        props = [SimpleNamespace(name=n) for n in sorted(EXPECTED_PROPERTIES)]
        return SimpleNamespace(description=self.owner.description, properties=props)

    def update(self, description=None):
        self.owner.description = description


class FakeCollection:
    def __init__(self, name="RH_T__main", description=None):
        self.name, self.description = name, description
        self.objects: dict[str, _Obj] = {}
        self.fail_inserts = False
        self.data = _Data(self)
        self.config = _Config(self)
        self.aggregate = SimpleNamespace(over_all=lambda total_count=True: SimpleNamespace(total_count=len(self.objects)))
        # Filters are ignored: every seed caller of fetch_objects re-checks the exact
        # file_path itself, so returning everything is a faithful double.
        self.query = SimpleNamespace(fetch_objects=lambda **kw: SimpleNamespace(objects=list(self.objects.values())))

    def iterator(self, include_vector=False, return_properties=None):
        return iter(list(self.objects.values()))

    def add(self, uuid, **properties):
        self.objects[uuid] = _Obj(uuid=uuid, properties=properties, vector=None)


class _Collections:
    def __init__(self, owner):
        self.owner = owner

    def exists(self, name):
        return name in self.owner.store

    def get(self, name):
        return self.owner.store[name]

    def create(self, name, description=None, **_):
        self.owner.store[name] = FakeCollection(name, description)
        self.owner.created.append(name)

    def delete(self, name):
        self.owner.store.pop(name, None)
        self.owner.deleted.append(name)

    def list_all(self, simple=True):
        return {name: None for name in self.owner.store}


class FakeClient:
    def __init__(self, *collections: FakeCollection):
        self.store = {c.name: c for c in collections}
        self.created: list[str] = []
        self.deleted: list[str] = []
        self.collections = _Collections(self)
        self.closed = False

    def close(self):
        self.closed = True
```

- [ ] **Step 2: Write the failing tests**

`tests/test_decisions.py`:

```python
import hashlib
import json

from reasonhold.chunkers import chunk_decisions
from reasonhold.decisions import DecisionLog, decision_id, iter_supersedes_rows, record_id


def rec(topic, dt, **extra):
    return {"topic": topic, "decision": "d", "rationale": "r", "datetime": dt, **extra}


def dump(path, *records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


def test_decision_id_matches_the_constraint():
    expected = "dec-" + hashlib.sha256(b"topic-a|2026-10-01T00:00:00+00:00").hexdigest()[:12]
    assert decision_id("topic-a", "2026-10-01T00:00:00+00:00") == expected


def test_ids_are_derived_for_legacy_records_and_kept_when_explicit():
    assert record_id(rec("a", "t1")) == decision_id("a", "t1")
    assert record_id(rec("a", "t1", id="dec-000000000000")) == "dec-000000000000"


def test_status_is_computed_from_supersedes_records(tmp_path):
    a = rec("a", "t1")
    b = rec("b", "t2", supersedes_records=[decision_id("a", "t1")])
    c = rec("c", "t3", status="superseded")
    log = DecisionLog.load(dump(tmp_path / "d.jsonl", a, b, c))
    assert log.status(decision_id("a", "t1")) == "superseded"
    assert log.superseded_by(decision_id("a", "t1")) == [decision_id("b", "t2")]
    assert log.status(decision_id("b", "t2")) == "active"
    assert log.status(decision_id("c", "t3")) == "superseded"
    assert [r["topic"] for r in log.active()] == ["b"]


def test_a_superseded_record_stops_retracting(tmp_path):
    a = rec("a", "t1", supersedes=[{"path": "docs/x.md", "retraction_summary": "x is wrong"}])
    b = rec("b", "t2", supersedes_records=[decision_id("a", "t1")])
    path = dump(tmp_path / "d.jsonl", a)
    assert [r.path for r in DecisionLog.load(path).retractions()] == ["docs/x.md"]
    path = dump(tmp_path / "d.jsonl", a, b)
    assert DecisionLog.load(path).retractions() == []
    assert list(iter_supersedes_rows(path)) == []


def test_retraction_fields_and_hash(tmp_path):
    a = rec("a", "t1", supersedes=[{"path": "docs/x.md#Queue", "retraction_summary": "LIFO now"}])
    log = DecisionLog.load(dump(tmp_path / "d.jsonl", a))
    (r,) = log.retractions()
    assert (r.file_path, r.section, r.topic, r.decision_id) == ("docs/x.md", "Queue", "a", decision_id("a", "t1"))
    before = log.retraction_sha256()
    log2 = DecisionLog.load(dump(tmp_path / "d.jsonl", a, rec("b", "t2")))
    assert log2.retraction_sha256() == before
    log3 = DecisionLog.load(dump(tmp_path / "d.jsonl", a, rec("b", "t2", supersedes_records=[decision_id("a", "t1")])))
    assert log3.retraction_sha256() != before


def test_malformed_lines_are_skipped(tmp_path):
    path = tmp_path / "d.jsonl"
    path.write_text('{"topic": "a", "datetime": "t1"}\nnot json\n\n')
    assert [r["topic"] for r in DecisionLog.load(path).records] == ["a"]
    assert DecisionLog.load(tmp_path / "missing.jsonl").records == []


def test_decision_chunks_carry_record_id_and_computed_status():
    a = rec("a", "t1")
    b = rec("b", "t2", supersedes_records=[decision_id("a", "t1")])
    chunks = chunk_decisions(json.dumps(a) + "\n" + json.dumps(b) + "\n", "decisions.jsonl")
    assert [c["record_id"] for c in chunks] == [decision_id("a", "t1"), decision_id("b", "t2")]
    assert [c["decision_status"] for c in chunks] == ["superseded", "active"]
    assert "Status: superseded" in chunks[0]["content"]
```

`tests/test_writes.py`:

```python
import json

import pytest

from helpers import FakeCollection, FakeProvider, make_repo
from reasonhold.decisions import DecisionLog, decision_id
from reasonhold.errors import StoreUnavailable, UnknownRecord
from reasonhold.project import Project
from reasonhold.writes import apply_retraction_to_chunks, mark_records_superseded, store_decision

HUMAN = {"kind": "human", "actor": "operator"}


@pytest.fixture
def project(tmp_path):
    make_repo(tmp_path, commit=False)
    return Project.load(tmp_path)


def lines(project):
    return [json.loads(x) for x in project.decisions_path.read_text().splitlines() if x.strip()]


def call(project, collection, provider, **kw):
    args = dict(topic="queue-order", decision="LIFO", rationale="because", provenance=HUMAN)
    args.update(kw)
    return store_decision(project, collection, provider, **args)


def test_store_decision_appends_then_indexes(project):
    col = FakeCollection()
    col.add("u1", file_path="docs/architecture/overview.md", chunk_type="markdown_section", section_heading="Queue")
    out = call(project, col, FakeProvider(), datetime_="2026-10-01T00:00:00+00:00",
               supersedes=[{"path": "docs/architecture/overview.md#queue", "retraction_summary": "LIFO now"}])
    (stored,) = lines(project)
    assert stored["id"] == decision_id("queue-order", "2026-10-01T00:00:00+00:00")
    assert stored["provenance"] == HUMAN and stored["supersedes_records"] == []
    assert out["indexed"] is True and out["annotated_chunks"] == 1 and out["warnings"] == []
    decision_chunks = [o for o in col.objects.values() if o.properties.get("chunk_type") == "decision"]
    assert decision_chunks[0].properties["record_id"] == stored["id"]
    assert decision_chunks[0].properties["file_path"] == "decisions.jsonl"
    assert col.objects["u1"].properties["retraction_summary"] == "LIFO now"


def test_store_decision_appends_nothing_when_embedding_fails(project):
    with pytest.raises(StoreUnavailable):
        call(project, FakeCollection(), FakeProvider(fail=True))
    assert project.decisions_path.read_text() == ""
    call(project, FakeCollection(), FakeProvider())
    assert len(lines(project)) == 1


def test_same_topic_and_datetime_is_idempotent(project):
    for _ in range(2):
        out = call(project, FakeCollection(), FakeProvider(), datetime_="2026-10-01T00:00:00+00:00")
    assert len(lines(project)) == 1 and out["warnings"] == ["already recorded"]


def test_unknown_supersedes_record_is_rejected_before_anything_happens(project):
    provider = FakeProvider()
    with pytest.raises(UnknownRecord):
        call(project, FakeCollection(), provider, supersedes_records=["dec-000000000000"])
    assert provider.calls == [] and project.decisions_path.read_text() == ""


def test_invalid_input_is_rejected(project):
    with pytest.raises(ValueError):
        call(project, FakeCollection(), FakeProvider(), topic="")
    with pytest.raises(ValueError):
        call(project, FakeCollection(), FakeProvider(), provenance={"kind": "robot"})
    with pytest.raises(ValueError):
        call(project, FakeCollection(), FakeProvider(), supersedes=[{"path": "x"}])


def test_supersedes_records_marks_old_chunks_superseded(project):
    first = call(project, FakeCollection(), FakeProvider(), topic="a", datetime_="t1")["record"]
    col = FakeCollection()
    col.add("old", chunk_type="decision", record_id=first["id"], decision_status="active")
    out = call(project, col, FakeProvider(), topic="b", datetime_="t2", supersedes_records=[first["id"]])
    assert col.objects["old"].properties["decision_status"] == "superseded"
    assert DecisionLog.load(project.decisions_path).status(first["id"]) == "superseded"
    assert out["status"] == "active"


def test_index_failure_after_append_is_a_warning(project):
    col = FakeCollection()
    col.fail_inserts = True
    out = call(project, col, FakeProvider())
    assert len(lines(project)) == 1 and out["indexed"] is False
    assert "run `reasonhold index`" in out["warnings"][0]


def test_missing_index_is_a_warning(project):
    out = call(project, None, FakeProvider())
    assert len(lines(project)) == 1 and out["indexed"] is False and out["warnings"]


def test_helpers_respect_decision_chunks():
    col = FakeCollection()
    col.add("d", chunk_type="decision", file_path="docs/x.md", record_id="dec-1")
    assert apply_retraction_to_chunks(col, "docs/x.md", "s", "t", "d") == 0
    assert mark_records_superseded(col, ["dec-1"]) == 1
```

- [ ] **Step 3: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_decisions.py tests/test_writes.py -q`
Expected: collection errors, `No module named 'reasonhold.decisions'` and `'reasonhold.writes'`.

- [ ] **Step 4: Implement `jsonl.py`**

```python
"""The one writer for append-only JSONL logs. No code path rewrites a line."""

from __future__ import annotations

import json
import os
from pathlib import Path


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with open(path, "a+b") as fh:
        fh.seek(0, os.SEEK_END)
        if fh.tell() > 0:
            fh.seek(-1, os.SEEK_END)
            if fh.read(1) != b"\n":
                fh.write(b"\n")  # a hand edit left no trailing newline; never glue two records
        fh.write(line.encode())
        fh.flush()
        os.fsync(fh.fileno())
```

- [ ] **Step 5: Implement `decisions.py`**

`git rm src/reasonhold/decisions_io.py` and create `decisions.py`. Copy the seed's module docstring rationale (dependency-light because the preamble imports it) and `iter_decision_records` verbatim, then add:

```python
import hashlib
import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

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
```

Move the seed's `_validate_supersedes` and `_format_decision_content` from `server.py` into `decisions.py` as `validate_supersedes` and `format_decision_content` with their bodies unchanged, except that `format_decision_content(record, status=None)` writes `Status: {status or record.get('status', 'active')}` and, when the record has an `id`, appends a final line `Id: {record['id']}`.

- [ ] **Step 6: Make `chunk_decisions` use the computed status**

In `chunkers.py`, `chunk_decisions`: add `from reasonhold.decisions import DecisionLog, record_id` at the top of the module; before the loop add `log = DecisionLog.from_text(text)`; inside the loop, after `record = json.loads(line)`, add `rid = record_id(record)` and `status = log.status(rid)`; the content line becomes `f"Status: {status}"`; the chunk dict gains `"record_id": rid` and `"decision_status": status`. Nothing else changes.

- [ ] **Step 7: Implement `writes.py`**

```python
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
```

- [ ] **Step 8: Re-point the seed modules and tests**

- `server.py`: delete its `apply_retraction_to_chunks`, `_format_decision_content` and `_validate_supersedes` definitions; add `from reasonhold.decisions import format_decision_content as _format_decision_content, validate_supersedes as _validate_supersedes` and `from reasonhold.writes import apply_retraction_to_chunks`. Its `store_decision` tool calls `apply_retraction_to_chunks(collection, ...)` with `collection = client.collections.get(COLLECTION_NAME)` already in scope. The rest of `server.py` is replaced in Task 14.
- `index.py` and `bootstrap.py`: `from reasonhold.decisions_io import ...` becomes `from reasonhold.decisions import ...`.
- `git mv src/reasonhold/audit_supersedes.py src/reasonhold/audit.py`; replace `from reasonhold.config import DECISIONS_FILE` with nothing and make `find_candidates(decisions_file: Path)` and `main()`'s use take the path explicitly (`main` reads `REASONHOLD_DECISIONS` relative to the current directory, default `decisions.jsonl`; Task 13 replaces it with `reasonhold decisions audit`). If a seed test relies on the old default, pass the fixture path explicitly. In `audit.py`, replace any em dash in user-facing strings (`render_report`) with a colon or a comma, and point `test_audit_supersedes.py`'s source read at `Path(reasonhold.audit.__file__)`.
- `tests/test_audit_supersedes.py`: import from `reasonhold.audit`.
- `tests/test_store_decision_supersedes.py`: `from reasonhold.decisions import format_decision_content as _format_decision_content, validate_supersedes as _validate_supersedes`.
- `tests/test_apply_retraction_overlay.py`: `from reasonhold.writes import apply_retraction_to_chunks`; every call passes the collection instead of the client: `apply_retraction_to_chunks(client.collections.get("RH_T__main"), ...)` (the fake's `get` ignores the name).

- [ ] **Step 9: Run the tests and the suite**

Run: `.venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add -A && git commit -q -m "Decision log v2: ids, supersedes_records, provenance, computed status; store_decision validates, embeds, appends, then indexes"
```

---

### Task 7: Pending sidecar, validation and `check`

**Files:**
- Create: `src/reasonhold/pending.py`, `src/reasonhold/validation.py`, `src/reasonhold/schemas/{manifest,decision,pending}.schema.json`, `tests/test_pending.py`, `tests/test_validation.py`
- Modify: `src/reasonhold/writes.py` (new writes; `resolves` on `store_decision`)

**Interfaces:**
- Consumes: `append_jsonl` (Task 6); `DecisionLog`, `validate_provenance` (Task 6); `Project` (Task 3); `UnknownRecord` (Task 2).
- Produces:

```python
# pending.py
KINDS = ("candidate_binding", "conflict", "resolution", "path_alias", "curation")
OPEN_KINDS = ("candidate_binding", "conflict")
OUTCOMES = ("promoted", "rejected", "resolved")
def pending_id(kind: str, datetime_: str, payload: dict) -> str
def make_record(kind: str, payload: dict, provenance: dict, *, datetime_: str | None = None) -> dict
def follow_alias(path: str, aliases: Mapping[str, str]) -> str        # chain-following, loop-safe
class PendingLog:
    records: list[dict]
    @classmethod
    def load(cls, path: Path) -> "PendingLog"
    @classmethod
    def from_text(cls, text: str) -> "PendingLog"
    def get(self, id: str) -> dict | None
    def resolved_ids(self) -> set[str]
    def is_open(self, id: str) -> bool
    def open(self, kind: str | None = None) -> list[dict]
    def resolution_for(self, id: str) -> dict | None
    def aliases(self) -> dict[str, str]                 # old_path -> new_path, file order, later wins
    def former_names(self, path: str) -> set[str]       # path plus every old path that now resolves to it

# writes.py (added)
def propose_binding(project, *, target: str, reads: list[str], validates_against: list[str], reason: str,
                    provenance: dict, datetime_: str | None = None) -> dict
def report_conflict(project, *, doc_a: str, doc_b: str, paths: list[str], claim: str,
                    evidence_a: str, evidence_b: str, provenance: dict, datetime_: str | None = None) -> dict
def resolve(project, *, pending_ids: list[str], outcome: str, decision_id: str | None = None,
            note: str | None = None, provenance: dict, datetime_: str | None = None) -> dict
# store_decision gains: resolves: list[str] | None = None

# validation.py
@dataclass(frozen=True)
class Problem:
    severity: str             # "error" | "warning"
    file: str
    line: int | None
    message: str
def load_schema(name: str) -> dict                      # "manifest" | "decision" | "pending"
def check(project) -> list[Problem]
```

The pending id is `pen-` + first 12 hex digits of `sha256(kind + "|" + datetime + "|" + canonical JSON of the payload)`, where canonical JSON is `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` and the payload is the record minus `id`, `kind`, `datetime` and `provenance`. A record `{"id", "kind", "datetime", "provenance", **payload}`. A `candidate_binding` or `conflict` is open until some `resolution` lists its id in `resolves`.

- [ ] **Step 1: Write the failing tests**

`tests/test_pending.py`:

```python
import json

import pytest

from helpers import FakeCollection, FakeProvider, make_repo
from reasonhold.errors import UnknownRecord
from reasonhold.pending import PendingLog, follow_alias, make_record, pending_id
from reasonhold.project import Project
from reasonhold.writes import propose_binding, report_conflict, resolve, store_decision

AGENT = {"kind": "agent", "actor": "architect"}


@pytest.fixture
def project(tmp_path):
    make_repo(tmp_path, commit=False)
    return Project.load(tmp_path)


def test_pending_id_matches_the_constraint():
    import hashlib

    payload = {"old_path": "a.md", "new_path": "b.md"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    expected = "pen-" + hashlib.sha256(f"path_alias|t1|{canonical}".encode()).hexdigest()[:12]
    assert pending_id("path_alias", "t1", payload) == expected
    assert make_record("path_alias", payload, AGENT, datetime_="t1")["id"] == expected


def test_open_until_resolved(project):
    cand = propose_binding(project, target="worker-contract", reads=["docs/specs/retry.md"],
                           validates_against=["src/worker/"], reason="new spec", provenance=AGENT)
    log = PendingLog.load(project.pending_path)
    assert [r["id"] for r in log.open("candidate_binding")] == [cand["id"]]
    resolve(project, pending_ids=[cand["id"]], outcome="rejected", note="no", provenance={"kind": "human"})
    log = PendingLog.load(project.pending_path)
    assert log.open() == [] and log.resolution_for(cand["id"])["outcome"] == "rejected"


def test_resolve_refuses_unknown_or_closed_ids(project):
    with pytest.raises(UnknownRecord):
        resolve(project, pending_ids=["pen-000000000000"], outcome="resolved", provenance={"kind": "human"})
    conflict = report_conflict(project, doc_a="docs/a.md#Queue", doc_b="docs/b.md", paths=["src/q.py"],
                               claim="FIFO or LIFO", evidence_a="FIFO", evidence_b="LIFO", provenance=AGENT)
    resolve(project, pending_ids=[conflict["id"]], outcome="resolved", provenance={"kind": "human"})
    with pytest.raises(UnknownRecord):
        resolve(project, pending_ids=[conflict["id"]], outcome="resolved", provenance={"kind": "human"})


def test_invalid_writes_append_nothing(project):
    with pytest.raises(ValueError):
        report_conflict(project, doc_a="docs/a.md", doc_b="docs/a.md", paths=[], claim="x",
                        evidence_a="a", evidence_b="b", provenance=AGENT)
    with pytest.raises(ValueError):
        propose_binding(project, target="", reads=["x.md"], validates_against=["src/"], reason="r", provenance=AGENT)
    with pytest.raises(ValueError):
        propose_binding(project, target="t", reads=["/etc/passwd"], validates_against=["src/"], reason="r", provenance=AGENT)
    assert not project.pending_path.exists()


def test_store_decision_resolves_a_conflict_in_one_call(project):
    conflict = report_conflict(project, doc_a="docs/a.md", doc_b="docs/b.md", paths=["src/q.py"],
                               claim="c", evidence_a="a", evidence_b="b", provenance=AGENT)
    out = store_decision(project, FakeCollection(), FakeProvider(), topic="queue", decision="FIFO",
                         rationale="r", resolves=[conflict["id"]], provenance={"kind": "human"})
    log = PendingLog.load(project.pending_path)
    assert not log.is_open(conflict["id"])
    assert log.resolution_for(conflict["id"])["decision_id"] == out["record"]["id"]
    assert out["record"]["resolves"] == [conflict["id"]]


def test_store_decision_with_unknown_resolves_appends_nothing(project):
    with pytest.raises(UnknownRecord):
        store_decision(project, FakeCollection(), FakeProvider(), topic="t", decision="d", rationale="r",
                       resolves=["pen-000000000000"], provenance={"kind": "human"})
    assert project.decisions_path.read_text() == ""


def test_aliases_follow_chains_and_survive_loops():
    log = PendingLog([
        make_record("path_alias", {"old_path": "a.md", "new_path": "b.md"}, AGENT, datetime_="t1"),
        make_record("path_alias", {"old_path": "b.md", "new_path": "c.md"}, AGENT, datetime_="t2"),
    ])
    assert follow_alias("a.md", log.aliases()) == "c.md"
    assert log.former_names("c.md") == {"a.md", "b.md", "c.md"}
    assert follow_alias("x.md", {"x.md": "y.md", "y.md": "x.md"}) in {"x.md", "y.md"}
```

`tests/test_validation.py`:

```python
import json
from pathlib import Path

from helpers import make_repo, write
from reasonhold.project import Project
from reasonhold.validation import check

REPO_ROOT = Path(__file__).resolve().parents[1]


def messages(problems, severity=None):
    return [p.message for p in problems if severity is None or p.severity == severity]


def test_clean_repo_has_no_problems(tmp_path):
    make_repo(tmp_path, commit=False)
    assert check(Project.load(tmp_path)) == []


def test_check_reports_missing_referenced_files(tmp_path):
    make_repo(tmp_path, commit=False)
    (tmp_path / "docs/specs/worker.md").unlink()
    problems = check(Project.load(tmp_path))
    warnings = messages(problems, "warning")
    assert any("docs/specs/worker.md" in m for m in warnings)
    assert sum("docs/specs/worker.md" in m for m in warnings) == 2   # areas.worker.docs and checks.worker-contract.reads


def test_check_reports_bad_decision_lines_with_line_numbers(tmp_path):
    make_repo(tmp_path, commit=False)
    good = {"topic": "a", "decision": "d", "rationale": "r", "datetime": "t1"}
    (tmp_path / "decisions.jsonl").write_text(
        json.dumps(good) + "\nnot json\n" + json.dumps({"topic": "b"}) + "\n"
        + json.dumps({**good, "topic": "c", "datetime": "t2", "supersedes_records": ["dec-000000000000"]}) + "\n"
        + json.dumps(good) + "\n"
    )
    problems = [p for p in check(Project.load(tmp_path)) if p.file == "decisions.jsonl"]
    assert sorted({p.line for p in problems if p.severity == "error"}) == [2, 3, 4, 5]
    assert any("duplicate id" in p.message for p in problems)


def test_check_reports_undefined_check_names(tmp_path):
    make_repo(tmp_path, commit=False)
    text = (tmp_path / "sync-doc.yaml").read_text().replace("checks: [worker-contract]", "checks: [nope]")
    write(tmp_path, "sync-doc.yaml", text)
    assert any("nope" in m for m in messages(check(Project.load(tmp_path))))


def test_this_repository_validates():
    """ReasonHold's own decision log (Auctor's 8 records plus 10) must pass its own check."""
    problems = [p for p in check(Project.load(REPO_ROOT)) if p.file == "decisions.jsonl" and p.severity == "error"]
    assert problems == []
```

`test_this_repository_validates` needs a manifest at the repository root. Add the ReasonHold repository's own `reasonhold.yaml` in this task:

```yaml
project:
  id: reasonhold
global:
  docs: [docs/specs/2026-10-01-reasonhold-0.1-design.md, docs/architecture/requirements.md]
  archival: [docs/reviews/2026-09-23-origin-extraction-triage.md]
  index: [README.md, "docs/**/*.md"]
areas:
  package:
    description: The reasonhold Python package
    projects: [reasonhold]
    docs: [docs/specs/2026-10-01-reasonhold-0.1-design.md]
    index: ["src/reasonhold/*.py", "tests/*.py"]
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_pending.py tests/test_validation.py -q`
Expected: collection errors, `No module named 'reasonhold.pending'` and `'reasonhold.validation'`.

- [ ] **Step 3: Implement `pending.py`**

```python
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
```

- [ ] **Step 4: Add the pending writes to `writes.py`**

```python
from reasonhold.pending import OUTCOMES, PendingLog, make_record


def _relative_paths(name: str, values, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(values, list) or (not values and not allow_empty):
        raise ValueError(f"{name} must be a non-empty list of repository-relative paths")
    out = []
    for value in values:
        path = _required_text(name, value)
        if path.startswith("/") or ".." in path.split("/"):
            raise ValueError(f"{name}: {path!r} must be relative to the repository and stay inside it")
        out.append(path)
    return out


def _append_pending(project, kind: str, payload: dict, provenance: dict, datetime_) -> dict:
    record = make_record(kind, payload, validate_provenance(provenance), datetime_=datetime_)
    if PendingLog.load(project.pending_path).get(record["id"]) is None:
        append_jsonl(project.pending_path, record)
    return record


def propose_binding(project, *, target, reads, validates_against, reason, provenance, datetime_=None) -> dict:
    payload = {
        "target": _required_text("target", target),
        "reads": _relative_paths("reads", reads),
        "validates_against": _relative_paths("validates_against", validates_against),
        "reason": _required_text("reason", reason),
    }
    return _append_pending(project, "candidate_binding", payload, provenance, datetime_)


def report_conflict(project, *, doc_a, doc_b, paths, claim, evidence_a, evidence_b, provenance, datetime_=None) -> dict:
    a, b = _required_text("doc_a", doc_a), _required_text("doc_b", doc_b)
    if a == b:
        raise ValueError("doc_a and doc_b must differ")
    _relative_paths("doc_a", [a.partition("#")[0]])
    _relative_paths("doc_b", [b.partition("#")[0]])
    payload = {
        "doc_a": a,
        "doc_b": b,
        "paths": _relative_paths("paths", paths, allow_empty=True),
        "claim": _required_text("claim", claim),
        "evidence_a": _required_text("evidence_a", evidence_a),
        "evidence_b": _required_text("evidence_b", evidence_b),
    }
    return _append_pending(project, "conflict", payload, provenance, datetime_)


def _require_open(project, pending_ids) -> list[str]:
    if not isinstance(pending_ids, list) or not pending_ids:
        raise ValueError("pending_ids must be a non-empty list")
    log = PendingLog.load(project.pending_path)
    for pid in pending_ids:
        if not log.is_open(pid):
            raise UnknownRecord(f"{pid} is not an open candidate or conflict in {project.pending_rel}")
    return list(dict.fromkeys(pending_ids))


def resolve(project, *, pending_ids, outcome, decision_id=None, note=None, provenance, datetime_=None) -> dict:
    ids = _require_open(project, pending_ids)
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {', '.join(OUTCOMES)}")
    if decision_id is not None and DecisionLog.load(project.decisions_path).get(decision_id) is None:
        raise UnknownRecord(f"{decision_id} is not in {project.decisions_rel}")
    payload = {"resolves": ids, "outcome": outcome}
    if decision_id:
        payload["decision_id"] = decision_id
    if note:
        payload["note"] = note
    return _append_pending(project, "resolution", payload, provenance, datetime_)
```

In `store_decision`: add the keyword `resolves=None`. During validation (before embedding) run `resolve_ids = _require_open(project, resolves) if resolves else []`. The record gains `"resolves": resolve_ids`. Directly after `append_jsonl(project.decisions_path, record)` add:

```python
    if resolve_ids:
        _append_pending(project, "resolution",
                        {"resolves": resolve_ids, "outcome": "resolved", "decision_id": rid},
                        clean_provenance, when)
```

- [ ] **Step 5: Write the three JSON Schemas**

`src/reasonhold/schemas/decision.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ReasonHold decision record",
  "type": "object",
  "required": ["topic", "decision", "datetime"],
  "properties": {
    "id": {"type": "string", "pattern": "^dec-[0-9a-f]{12}$"},
    "topic": {"type": "string", "minLength": 1},
    "decision": {"type": "string", "minLength": 1},
    "rationale": {"type": "string"},
    "alternatives_considered": {"type": "array", "items": {"type": "string"}},
    "datetime": {"type": "string", "minLength": 1},
    "session_context": {"type": "string"},
    "tags": {"type": "array", "items": {"type": "string"}},
    "status": {"enum": ["active", "superseded"]},
    "supersedes": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["path", "retraction_summary"],
        "properties": {
          "path": {"type": "string", "minLength": 1},
          "retraction_summary": {"type": "string", "minLength": 1}
        }
      }
    },
    "supersedes_records": {"type": "array", "items": {"type": "string", "pattern": "^dec-[0-9a-f]{12}$"}},
    "resolves": {"type": "array", "items": {"type": "string", "pattern": "^pen-[0-9a-f]{12}$"}},
    "provenance": {"$ref": "#/$defs/provenance"}
  },
  "$defs": {
    "provenance": {
      "type": "object",
      "required": ["kind"],
      "properties": {
        "kind": {"enum": ["human", "agent", "sendesis_run"]},
        "actor": {"type": "string"},
        "run_id": {"type": "string"},
        "role": {"type": "string"}
      }
    }
  }
}
```

`src/reasonhold/schemas/pending.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ReasonHold pending record",
  "type": "object",
  "required": ["id", "kind", "datetime", "provenance"],
  "properties": {
    "id": {"type": "string", "pattern": "^pen-[0-9a-f]{12}$"},
    "kind": {"enum": ["candidate_binding", "conflict", "resolution", "path_alias", "curation"]},
    "datetime": {"type": "string", "minLength": 1},
    "provenance": {
      "type": "object",
      "required": ["kind"],
      "properties": {"kind": {"enum": ["human", "agent", "sendesis_run"]}}
    }
  },
  "allOf": [
    {"if": {"properties": {"kind": {"const": "candidate_binding"}}},
     "then": {"required": ["target", "reads", "validates_against", "reason"],
              "properties": {"target": {"type": "string", "minLength": 1},
                             "reads": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                             "validates_against": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                             "reason": {"type": "string"}}}},
    {"if": {"properties": {"kind": {"const": "conflict"}}},
     "then": {"required": ["doc_a", "doc_b", "paths", "claim", "evidence_a", "evidence_b"],
              "properties": {"paths": {"type": "array", "items": {"type": "string"}}}}},
    {"if": {"properties": {"kind": {"const": "resolution"}}},
     "then": {"required": ["resolves", "outcome"],
              "properties": {"resolves": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                             "outcome": {"enum": ["promoted", "rejected", "resolved"]}}}},
    {"if": {"properties": {"kind": {"const": "path_alias"}}},
     "then": {"required": ["old_path", "new_path"]}},
    {"if": {"properties": {"kind": {"const": "curation"}}},
     "then": {"required": ["edit", "cause"]}}
  ]
}
```

`src/reasonhold/schemas/manifest.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ReasonHold manifest (reasonhold.yaml or legacy sync-doc.yaml)",
  "type": "object",
  "required": ["areas"],
  "$defs": {
    "paths": {"type": "array", "items": {"type": "string", "minLength": 1}},
    "nonEmptyPaths": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}}
  },
  "properties": {
    "global": {
      "type": "object",
      "properties": {
        "checks": {"$ref": "#/$defs/paths"},
        "docs": {"$ref": "#/$defs/paths"},
        "archival": {"$ref": "#/$defs/paths"},
        "index": {"$ref": "#/$defs/paths"}
      }
    },
    "areas": {
      "type": "object",
      "minProperties": 1,
      "additionalProperties": {
        "type": "object",
        "required": ["projects", "docs", "index"],
        "properties": {
          "description": {"type": "string"},
          "projects": {"$ref": "#/$defs/nonEmptyPaths"},
          "docs": {"$ref": "#/$defs/nonEmptyPaths"},
          "index": {"$ref": "#/$defs/nonEmptyPaths"},
          "checks": {"$ref": "#/$defs/paths"}
        }
      }
    },
    "checks": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "properties": {
          "description": {"type": "string"},
          "mode": {"enum": ["index", "fs"]},
          "reads": {"$ref": "#/$defs/paths"},
          "validates_against": {"$ref": "#/$defs/paths"}
        }
      }
    },
    "project": {
      "type": "object",
      "properties": {
        "id": {"type": "string", "minLength": 1},
        "decisions": {"type": "string", "minLength": 1},
        "pending": {"type": "string", "minLength": 1},
        "embedding": {
          "type": "object",
          "properties": {
            "provider": {"enum": ["ollama", "openai_compatible"]},
            "model": {"type": "string"},
            "base_url": {"type": "string"},
            "api_key_env": {"type": "string"}
          }
        },
        "index": {"type": "object", "properties": {"branch_isolation": {"type": "boolean"}}}
      }
    },
    "authority": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["level", "paths"],
        "properties": {
          "level": {"type": "string", "minLength": 1},
          "document_kind": {"type": "string"},
          "paths": {"$ref": "#/$defs/nonEmptyPaths"},
          "weight": {"type": "number"}
        }
      }
    }
  }
}
```

Before committing, confirm the seed's own `load_manifest` rules agree with this schema (areas required with non-empty `projects`, `docs`, `index`). If the seed loader accepts something the schema rejects, relax the schema to match the loader; the loader is the parity-tested authority.

- [ ] **Step 6: Implement `validation.py`**

```python
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
```

- [ ] **Step 7: Run the tests and the suite**

Run: `.venv/bin/pytest -q`
Expected: all pass. If `test_this_repository_validates` fails, the fault is in the schema or the checker, never in `decisions.jsonl`: the log is append-only and must not be edited.

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -q -m "Pending sidecar, propose/report/resolve writes, JSON Schemas and reasonhold check"
```

---

### Task 8: Alias-aware retraction overlay and the indexer split

**Files:**
- Create: `src/reasonhold/overlay.py`, `src/reasonhold/indexer.py`, `tests/test_overlay.py`, `tests/test_indexer.py`
- Modify: `src/reasonhold/chunkers.py` (add `chunk_pending`), `src/reasonhold/symbols.py` (lazy imports only)
- Delete: `src/reasonhold/index.py`, `src/reasonhold/backfill_decisions.py`
- Modify tests: `tests/test_retraction_overlay.py`, `tests/test_binary_guard.py`, `tests/test_insert_verification.py`, `tests/test_full_reindex_semantics.py`, `tests/test_file_path_exact_match.py`

**Interfaces:**
- Consumes: `DecisionLog` (Task 6); `PendingLog`, `follow_alias` (Task 7); `enrich_chunk` (Task 3); `EmbeddingProvider` (Task 5).
- Produces:

```python
# overlay.py
def load_retraction_overlay(decisions_path: Path, aliases: Mapping[str, str] | None = None) -> dict[str, dict]
def retraction_for_chunk(chunk: dict, overlay: dict[str, dict]) -> dict | None          # seed, unchanged

# indexer.py (seed index.py minus main, verify_prerequisites, _assert_tcp_connectivity)
EXCLUDED_PATH_PARTS: frozenset[str]          # seed set plus ".worktrees"
def is_excluded_path(path: Path, root: Path) -> bool                    # parts relative to root only
def detect_file_type(path: Path, *, decisions_path: Path | None = None, pending_path: Path | None = None) -> str
def is_binary_file(path: Path) -> bool                                   # seed, unchanged
def gather_files(root: Path, globs: Sequence[str], *, decisions_path: Path | None = None,
                 pending_path: Path | None = None) -> list[tuple[str, Path]]
def get_indexed_mtimes(collection) -> dict[str, datetime]               # seed, unchanged
def embed_texts(embedder, texts: list[str]) -> list[list[float]]        # embedder.embed(texts)
def index_file(collection, embedder, manifest, file_type: str, path: Path, *, root: Path,
               dry_run: bool = False, retraction_overlay: dict | None = None,
               enrich: Callable[[dict], dict] | None = None, char_budget: int = 12000) -> int
def delete_file_chunks(collection, file_path: str) -> int               # seed, unchanged
def clean_orphans(collection, indexed_paths: set[str]) -> int           # seed, unchanged
def stable_chunk_identity(file_path: str, chunk: dict) -> str           # seed, unchanged
# _delete_stale_chunks, _insert_verified: seed, unchanged

# chunkers.py
def chunk_pending(text: str, file_path: str) -> list[Chunk]            # open candidate_binding and conflict records only
CHUNKER_MAP["pending"] = chunk_pending
```

`index_file` changes from the seed: `rel_path` is `path.relative_to(root).as_posix()`; chunks are enriched with `enrich` (default `lambda c: enrich_chunk(c, manifest)`); vectors come from `embed_texts(embedder, texts)` (a module-level function so tests can still patch it); the `chunk_type == "csharp"` call passes `char_budget`; the properties dict gains `"record_id": chunk.get("record_id")`. Pending chunks set their own enrichment fields (`file_type: "pending"`, `authority_level: "pending"`, `document_kind: "pending_record"`), which `enrich_chunk`'s `setdefault` keeps. `.worktrees` joins the excluded parts because a repository's other worktrees live there and must never be indexed into this branch's collection.

- [ ] **Step 1: Write the failing tests**

`tests/test_overlay.py`:

```python
import json

from reasonhold.overlay import load_retraction_overlay, retraction_for_chunk


def dump(path, *records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


RETRACT = {"topic": "a", "decision": "d", "rationale": "r", "datetime": "t1",
           "supersedes": [{"path": "docs/old.md#Queue", "retraction_summary": "LIFO now"}]}


def test_overlay_follows_path_alias(tmp_path):
    overlay = load_retraction_overlay(dump(tmp_path / "d.jsonl", RETRACT), {"docs/old.md": "docs/new.md"})
    chunk = {"file_path": "docs/new.md", "section_heading": "Queue rules"}
    assert retraction_for_chunk(chunk, overlay)["retraction_summary"] == "LIFO now"
    assert retraction_for_chunk({"file_path": "docs/old.md", "section_heading": "Queue"}, overlay)


def test_overlay_ignores_records_retired_by_supersedes_records(tmp_path):
    from reasonhold.decisions import decision_id

    retire = {"topic": "b", "decision": "d", "rationale": "r", "datetime": "t2",
              "supersedes_records": [decision_id("a", "t1")]}
    assert load_retraction_overlay(dump(tmp_path / "d.jsonl", RETRACT, retire)) == {}
```

`tests/test_indexer.py`:

```python
import json

from helpers import FakeCollection, FakeProvider, write
from reasonhold.chunkers import chunk_pending
from reasonhold.indexer import gather_files, index_file
from reasonhold.manifest import AreaManifest, Manifest
from reasonhold.pending import make_record

MANIFEST = Manifest(global_index=(), areas=(AreaManifest(name="w", description="w", projects=("w",), docs=("a.md",), index=("*.md",)),))
AGENT = {"kind": "agent"}


def test_gather_files_excludes_only_parts_inside_the_root(tmp_path):
    root = tmp_path / "node_modules" / "repo"          # an excluded name ABOVE the root must not hide the repo
    write(root, "docs/a.md", "# A\n")
    write(root, ".worktrees/feat/docs/a.md", "# other worktree\n")
    write(root, "decisions.jsonl", "")
    files = gather_files(root, ["docs/*.md", "**/*.md", "missing.md", "decisions.jsonl"],
                         decisions_path=root / "decisions.jsonl")
    assert [(t, p.relative_to(root).as_posix()) for t, p in files] == [
        ("markdown", "docs/a.md"),
        ("decisions", "decisions.jsonl"),
    ]


def test_index_file_writes_record_id_and_relative_path(tmp_path):
    path = write(tmp_path, "decisions.jsonl",
                 json.dumps({"topic": "a", "decision": "d", "rationale": "r", "datetime": "t1"}) + "\n")
    col = FakeCollection()
    assert index_file(col, FakeProvider(), MANIFEST, "decisions", path, root=tmp_path) == 1
    (obj,) = col.objects.values()
    assert obj.properties["file_path"] == "decisions.jsonl"
    assert obj.properties["record_id"].startswith("dec-")


def test_pending_file_chunks_only_open_records():
    cand = make_record("candidate_binding", {"target": "t", "reads": ["a.md"], "validates_against": ["src/"],
                                             "reason": "r"}, AGENT, datetime_="t1")
    closed = make_record("conflict", {"doc_a": "a.md", "doc_b": "b.md", "paths": [], "claim": "c",
                                      "evidence_a": "x", "evidence_b": "y"}, AGENT, datetime_="t2")
    res = make_record("resolution", {"resolves": [closed["id"]], "outcome": "resolved"}, AGENT, datetime_="t3")
    alias = make_record("path_alias", {"old_path": "a.md", "new_path": "b.md"}, AGENT, datetime_="t4")
    text = "".join(json.dumps(r) + "\n" for r in (cand, closed, res, alias))
    chunks = chunk_pending(text, "reasonhold.pending.jsonl")
    assert [c["record_id"] for c in chunks] == [cand["id"]]
    assert chunks[0]["authority_level"] == "pending" and "Candidate binding: t" in chunks[0]["content"]
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_overlay.py tests/test_indexer.py -q`
Expected: collection errors, `No module named 'reasonhold.overlay'`.

- [ ] **Step 3: Implement `overlay.py`**

Move `load_retraction_overlay` and `retraction_for_chunk` out of `index.py`. `retraction_for_chunk` keeps its body and docstring verbatim. `load_retraction_overlay` becomes:

```python
"""The retraction overlay: which chunks an active decision retracts (R-07)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from reasonhold.decisions import DecisionLog
from reasonhold.pending import follow_alias


def load_retraction_overlay(decisions_path: Path, aliases: Mapping[str, str] | None = None) -> dict[str, dict]:
    """Keyed by retracted path (optionally with #section). Later decisions win on
    collisions. A retraction recorded against a path that has since moved
    (a path_alias record) also applies under the current path."""
    overlay: dict[str, dict] = {}
    for r in DecisionLog.load(decisions_path).retractions():
        value = {"retraction_summary": r.retraction_summary, "retraction_decision": r.topic, "retraction_date": r.date}
        overlay[r.path] = value
        if aliases:
            current = follow_alias(r.file_path, aliases)
            if current != r.file_path:
                overlay[current + (f"#{r.section}" if r.section else "")] = value
    return overlay
```

- [ ] **Step 4: Add `chunk_pending` to `chunkers.py`**

```python
def chunk_pending(text: str, file_path: str) -> list[Chunk]:
    """One searchable chunk per OPEN candidate binding or conflict. Never a governing document."""
    from reasonhold.pending import PendingLog

    chunks: list[Chunk] = []
    for index, record in enumerate(PendingLog.from_text(text).open()):
        if record["kind"] == "candidate_binding":
            lines = [
                f"Candidate binding: {record['target']}",
                f"Reads: {', '.join(record['reads'])}",
                f"Validates against: {', '.join(record['validates_against'])}",
                f"Reason: {record['reason']}",
            ]
        else:
            lines = [
                f"Conflict: {record['claim']}",
                f"Between: {record['doc_a']} and {record['doc_b']}",
                f"Paths: {', '.join(record['paths']) or 'none given'}",
                f"Evidence A: {record['evidence_a']}",
                f"Evidence B: {record['evidence_b']}",
            ]
        lines.append(f"Id: {record['id']} (open)")
        chunks.append(
            {
                "content": "\n".join(lines),
                "chunk_type": "pending",
                "file_type": "pending",
                "authority_level": "pending",
                "document_kind": "pending_record",
                "section_heading": record["id"],
                "section_path": record["id"],
                "semantic_label": record["kind"],
                "record_id": record["id"],
                "chunk_index": index,
                "file_path": file_path,
            }
        )
    return chunks
```

Register it: `CHUNKER_MAP["pending"] = chunk_pending` (add the key to the seed's dict literal).

- [ ] **Step 5: Create `indexer.py` from `index.py`**

`git mv src/reasonhold/index.py src/reasonhold/indexer.py`, then:

1. Delete `load_retraction_overlay`, `retraction_for_chunk` (now in `overlay.py`; import `retraction_for_chunk` from there), `verify_prerequisites`, `_assert_tcp_connectivity`, `main`, the `if __name__ == "__main__"` block, and the imports only they used (`argparse`, `socket`, `time`, `ollama`, `schema`, `config`, `load_manifest`, the `decisions` re-exports).
2. Add:

```python
EXCLUDED_PATH_PARTS = frozenset(
    {".git", ".venv", "__pycache__", ".pytest_cache", "site-packages", "node_modules", ".ruff_cache", "htmlcov", ".worktrees"}
)


def is_excluded_path(path: Path, root: Path) -> bool:
    return any(part in EXCLUDED_PATH_PARTS for part in path.relative_to(root).parts)


def gather_files(root, globs, *, decisions_path=None, pending_path=None):
    """Resolve corpus globs into unique (file_type, path) pairs. A literal entry
    naming a missing file yields nothing; `reasonhold check` reports it."""
    files: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for pattern in globs:
        for path in sorted(root.glob(pattern)):
            if path.is_file() and not is_excluded_path(path, root) and path not in seen:
                seen.add(path)
                files.append((detect_file_type(path, decisions_path=decisions_path, pending_path=pending_path), path))
    return files


def embed_texts(embedder, texts: list[str]) -> list[list[float]]:
    return embedder.embed(texts)
```

3. `detect_file_type(path, *, decisions_path=None, pending_path=None)`: the seed's `if path == DECISIONS_FILE` becomes `if decisions_path is not None and path == decisions_path: return "decisions"`, followed by the same test for `pending_path` returning `"pending"`. The rest is unchanged.
4. `index_file(collection, embedder, manifest, file_type, path, *, root, dry_run=False, retraction_overlay=None, enrich=None, char_budget=12000)`: `rel_path = path.relative_to(root).as_posix()`; `enrich = enrich or (lambda c: enrich_chunk(c, manifest))`; `chunker(text, rel_path, char_budget)` for C#; `vectors = embed_texts(embedder, [render_embedding_text(c) for c in enriched_chunks])`; add `"record_id": chunk.get("record_id")` to the properties. The binary refusal, verified insert, stale-chunk deletion after insert and the retraction annotation are unchanged. Replace the em dashes in the two printed messages (`SKIPPED (binary content ...)` and `failed to insert, retrying ...`) with a colon; adjust a seed test literal only if it asserts that exact text.

- [ ] **Step 6: Re-point the remaining seed code and tests**

- `git rm src/reasonhold/backfill_decisions.py` (it imports the seed indexer and the seed server; a full re-index now does its job).
- `symbols.py`, function-local imports only: `scan_working_tree` uses

```python
    from reasonhold.config import DECISIONS_FILE, SYNC_DOC_PATH
    from reasonhold.indexer import gather_files

    globs = load_manifest(SYNC_DOC_PATH).iter_corpus_globs(extra=[DECISIONS_FILE.relative_to(PROJECT_ROOT).as_posix()])
    for _file_type, path in gather_files(PROJECT_ROOT, globs, decisions_path=DECISIONS_FILE):
```

  and `indexed_mtimes` imports `get_indexed_mtimes` from `reasonhold.indexer`. Task 11 replaces this module.
- `tests/test_retraction_overlay.py`: import from `reasonhold.overlay`.
- `tests/test_binary_guard.py`, `tests/test_insert_verification.py`, `tests/test_full_reindex_semantics.py`, `tests/test_file_path_exact_match.py`:
  - `import reasonhold.index as index_mod` becomes `import reasonhold.indexer as index_mod`; `from reasonhold.index import X` becomes `from reasonhold.indexer import X`.
  - Delete every `monkeypatch.setattr(index_mod, "PROJECT_ROOT", tmp_path)`. Every `index_file(...)` call gains `root=<dir>`, where `<dir>` is the directory the test wrote its file into (`tmp_path`, or `doc.parent` in tests that receive a `doc` fixture).
  - The keyword `oll_client=None` becomes `embedder=None`. Patches of `index_mod.embed_texts` stay as they are; the seed fakes accept `(client, texts, batch_size=8)` and `index_file` now calls `embed_texts(embedder, texts)`, which those fakes satisfy.
  - Assertions are not changed.

- [ ] **Step 7: Run the tests and the suite**

Run: `.venv/bin/pytest -q`
Expected: all pass, including every ported seed test.

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -q -m "Split the seed indexer: alias-aware overlay, root-relative gathering, pending chunks, record_id"
```

---

### Task 9: Index lifecycle: state, the full re-index rule, lock, `run_index`, `gc`

**Files:**
- Create: `src/reasonhold/lifecycle.py`, `tests/test_lifecycle.py`

**Interfaces:**
- Consumes: `identity` (Task 4); `store` and `embedding.check_model` (Task 5); `DecisionLog` (Task 6); `PendingLog` (Task 7); `indexer`, `overlay` (Task 8); `enrich_for_project` (Task 3); `ladder_sha256` (Task 2).
- Produces:

```python
def file_sha256(path: Path) -> str                     # "" when the file is missing
@dataclass
class IndexState:
    project: str
    branch: str                # the checkout's branch
    indexed_branch: str        # whose collection answers (default branch in single-collection mode)
    collection: str
    exists: bool
    meta: CollectionMeta | None
    head: str | None
    stale: list[str]           # causes an answer may be wrong; empty means fresh
    rebuild: list[str]         # causes the next `reasonhold index` must be a full re-index
    notes: list[str]           # informational (no git, single-collection mode)
    fresh: bool                # property: exists and not stale
    def as_dict(self) -> dict
def indexed_branch(project) -> str
def rebuild_reasons(project, meta: CollectionMeta, head: str | None) -> list[str]
def index_state(project, client) -> IndexState
@contextmanager
def index_lock(name: str, *, lock_dir: Path | None = None) -> Iterator[None]   # ReasonHoldError when held
@dataclass
class IndexReport:
    collection: str
    full: bool
    reasons: list[str]
    dry_run: bool = False
    files_indexed: int = 0
    files_skipped: int = 0
    chunks: int = 0
    orphans_removed: int = 0
    warnings: list[str] = field(default_factory=list)
    curation: list[dict] = field(default_factory=list)     # filled from Task 10
    def as_dict(self) -> dict
def corpus_files(project, area_names: set[str] | None = None) -> list[tuple[str, Path]]
def run_index(project, client, provider, *, full: bool = False, dry_run: bool = False,
              area_names: set[str] | None = None, out: Callable[[str], None] = print,
              now: datetime | None = None) -> IndexReport
def gc_candidates(project, client) -> list[str]
def gc(project, client, *, yes: bool = False, confirm: Callable[[str], str] | None = None,
       out: Callable[[str], None] = print) -> list[str]
```

Rules (spec section 4), in one place:
- **Full re-index** when `--full`, when no collection or no metadata exists, when `authority_sha256` differs from the project's ladder, when `retraction_sha256` differs from the decision log's, or (git only, and only when the checkout is on the indexed branch) when `indexed_commit` is not an ancestor of HEAD or `git rev-list --merges indexed_commit..HEAD` is non-empty.
- **Stale** (a warning on answers, a refusal for absence checks): every rebuild reason, plus HEAD moved since `indexed_commit`, plus a changed manifest file.
- **Notes** (never stale): no git repository; single-collection mode on a non-default branch.
- Queries never index. `run_index` in single-collection mode on a non-default branch does nothing and says why.
- The lock file is `$XDG_CACHE_HOME/reasonhold/locks/<collection>.lock` (default `~/.cache`), taken with a non-blocking `fcntl.flock`.

- [ ] **Step 1: Write the failing tests**

`tests/test_lifecycle.py`:

```python
import re

import pytest

from helpers import FakeClient, FakeCollection, FakeProvider, MINIMAL_MANIFEST, git, make_repo, write
from reasonhold.errors import ModelMismatch, ReasonHoldError
from reasonhold.lifecycle import gc, gc_candidates, index_lock, index_state, run_index
from reasonhold.project import Project
from reasonhold.store import CollectionMeta, read_meta
from reasonhold.writes import store_decision

NAME = re.compile(r"^[A-Z][A-Za-z0-9_]*$")
QUIET = dict(out=lambda *a: None)


@pytest.fixture(autouse=True)
def cache_dir(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path / "repo")


def build(root, client=None, provider=None):
    client = client or FakeClient()
    report = run_index(Project.load(root), client, provider or FakeProvider(), **QUIET)
    return client, report


def test_first_run_is_full_and_records_the_commit(repo):
    client, report = build(repo)
    assert report.full and report.reasons == ["no index for this branch yet"] and report.chunks > 0
    state = index_state(Project.load(repo), client)
    assert state.fresh and state.meta.indexed_commit == git(repo, "rev-parse", "HEAD")
    assert state.meta.last_full_index and state.meta.model_id == "ollama:fake" and state.meta.dims == 4


def test_second_run_is_incremental_and_skips_unchanged_files(repo):
    client, first = build(repo)
    _, second = build(repo, client)
    assert not second.full and second.files_indexed == 0 and second.files_skipped == first.files_indexed


def test_index_state_without_git(tmp_path):
    root = make_repo(tmp_path / "plain", commit=False)
    project = Project.load(root)
    client, report = build(root)
    state = index_state(project, client)
    assert state.branch == "no-git" and NAME.match(state.collection) and state.collection.startswith("RH_")
    assert any("not a git repository" in n for n in state.notes)
    assert state.fresh and report.full


def test_merge_forces_full_rebuild(repo):
    client, _ = build(repo)
    git(repo, "checkout", "-q", "-b", "feat")
    write(repo, "docs/specs/extra.md", "# Extra\n")
    git(repo, "add", "-A"); git(repo, "commit", "-q", "-m", "feat")
    git(repo, "checkout", "-q", "main")
    write(repo, "AGENTS.md", "# Agents v2\n")
    git(repo, "commit", "-qam", "main")
    git(repo, "merge", "-q", "--no-ff", "feat", "-m", "merge")
    state = index_state(Project.load(repo), client)
    assert any("merge commit" in r for r in state.rebuild)
    _, report = build(repo, client)
    assert report.full


def test_history_rewrite_forces_full_rebuild(repo):
    client, _ = build(repo)
    git(repo, "commit", "-q", "--amend", "-m", "rewritten")
    assert any("not an ancestor" in r for r in index_state(Project.load(repo), client).rebuild)


def test_head_moved_is_stale_but_not_a_rebuild(repo):
    client, _ = build(repo)
    write(repo, "AGENTS.md", "# Agents v2\n")
    git(repo, "commit", "-qam", "edit")
    state = index_state(Project.load(repo), client)
    assert state.rebuild == [] and any("HEAD moved" in s for s in state.stale)


def test_new_retraction_forces_full_rebuild(repo):
    client, _ = build(repo)
    project = Project.load(repo)
    store_decision(project, None, FakeProvider(), topic="t", decision="d", rationale="r",
                   supersedes=[{"path": "docs/specs/worker.md", "retraction_summary": "no retries"}],
                   provenance={"kind": "human"})
    assert any("decision log" in r for r in index_state(project, client).rebuild)


def test_authority_change_forces_full_rebuild(repo):
    client, _ = build(repo)
    write(repo, "sync-doc.yaml", MINIMAL_MANIFEST + "authority:\n  - {level: architecture, paths: [\"docs/**\"], weight: 0.1}\n")
    state = index_state(Project.load(repo), client)
    assert any("authority" in r for r in state.rebuild) and any("manifest changed" in s for s in state.stale)


def test_model_guard_blocks_an_incremental_run(repo):
    client, _ = build(repo)
    with pytest.raises(ModelMismatch):
        build(repo, client, FakeProvider(dims=8))


def test_full_run_replaces_a_mismatched_model(repo):
    client, _ = build(repo)
    report = run_index(Project.load(repo), client, FakeProvider(dims=8), full=True, **QUIET)
    assert report.full and read_meta(client, report.collection).dims == 8


def test_dry_run_touches_nothing(repo):
    client = FakeClient()
    report = run_index(Project.load(repo), client, FakeProvider(), dry_run=True, **QUIET)
    assert report.dry_run and report.chunks > 0 and client.created == []


def test_single_collection_mode_answers_from_the_default_branch(tmp_path):
    root = make_repo(tmp_path / "r", MINIMAL_MANIFEST + "project:\n  index: {branch_isolation: false}\n")
    client, _ = build(root)
    git(root, "checkout", "-q", "-b", "feat")
    project = Project.load(root)
    state = index_state(project, client)
    assert state.indexed_branch == "main" and state.collection == "RH_R__main"
    assert any("single-collection" in n for n in state.notes)
    report = run_index(project, client, FakeProvider(), **QUIET)
    assert report.chunks == 0 and "single-collection" in report.warnings[0]


def test_index_lock_refuses_a_concurrent_run(tmp_path):
    with index_lock("RH_X__main", lock_dir=tmp_path):
        with pytest.raises(ReasonHoldError, match="another"):
            with index_lock("RH_X__main", lock_dir=tmp_path):
                pass
    with index_lock("RH_X__main", lock_dir=tmp_path):
        pass


def meta_collection(name, project, branch):
    return FakeCollection(name, CollectionMeta(project, branch, "ollama:fake", 4).to_description())


def test_gc_drops_only_this_projects_deleted_branches(repo):
    client = FakeClient(
        meta_collection("RH_Repo__main", "repo", "main"),
        meta_collection("RH_Repo__gone", "repo", "gone"),
        meta_collection("RH_Repo__detached_abc_12345678", "repo", "detached-abc"),
        meta_collection("RH_Other__gone", "other", "gone"),
        FakeCollection("RH_Repo__nometa"),
        FakeCollection("AriadneDoc"),
    )
    project = Project.load(repo)
    assert gc_candidates(project, client) == ["RH_Repo__gone"]
    assert gc(project, client, confirm=lambda prompt: "n", **QUIET) == []
    assert gc(project, client, yes=True, **QUIET) == ["RH_Repo__gone"]
    assert client.deleted == ["RH_Repo__gone"]
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_lifecycle.py -q`
Expected: collection error, `No module named 'reasonhold.lifecycle'`.

- [ ] **Step 3: Implement `lifecycle.py`**

```python
"""Index lifecycle (spec section 4): which collection answers, whether it is
fresh, when a run must rebuild, the per-collection lock, run_index and gc.
Queries never call run_index."""

from __future__ import annotations

import fcntl
import hashlib
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from reasonhold.authority import ladder_sha256
from reasonhold.decisions import DecisionLog
from reasonhold.embedding import check_model
from reasonhold.enrichment import enrich_for_project
from reasonhold.errors import ReasonHoldError, StoreUnavailable
from reasonhold.identity import (
    collection_name,
    current_branch,
    default_branch,
    head_commit,
    is_ancestor,
    local_branches,
    merges_between,
)
from reasonhold.indexer import clean_orphans, gather_files, get_indexed_mtimes, index_file
from reasonhold.overlay import load_retraction_overlay
from reasonhold.pending import PendingLog
from reasonhold.store import CollectionMeta, drop_collection, ensure_collection, list_collections, read_meta, write_meta


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def _as_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


@dataclass
class IndexState:
    project: str
    branch: str
    indexed_branch: str
    collection: str
    exists: bool
    meta: CollectionMeta | None
    head: str | None
    stale: list[str]
    rebuild: list[str]
    notes: list[str]

    @property
    def fresh(self) -> bool:
        return self.exists and not self.stale

    def as_dict(self) -> dict:
        return {
            "project": self.project,
            "branch": self.branch,
            "indexed_branch": self.indexed_branch,
            "collection": self.collection,
            "exists": self.exists,
            "fresh": self.fresh,
            "stale": list(self.stale),
            "notes": list(self.notes),
            "indexed_commit": self.meta.indexed_commit if self.meta else None,
            "last_full_index": self.meta.last_full_index if self.meta else None,
            "model_id": self.meta.model_id if self.meta else None,
        }


def indexed_branch(project) -> str:
    return current_branch(project.root) if project.branch_isolation else default_branch(project.root)


def rebuild_reasons(project, meta: CollectionMeta, head: str | None) -> list[str]:
    reasons: list[str] = []
    if meta.authority_sha256 != ladder_sha256(project.ladder):
        reasons.append("the manifest's authority ladder changed since the index was built")
    if meta.retraction_sha256 != DecisionLog.load(project.decisions_path).retraction_sha256():
        reasons.append("the decision log gained or changed retractions or supersedes_records since the index was built")
    if head and meta.indexed_commit and head != meta.indexed_commit:
        short = meta.indexed_commit[:8]
        if not is_ancestor(project.root, meta.indexed_commit, head):
            reasons.append(f"indexed commit {short} is not an ancestor of HEAD (rebase, reset or forced update)")
        else:
            merges = merges_between(project.root, meta.indexed_commit, head)
            if merges:
                reasons.append(f"{len(merges)} merge commit(s) since indexed commit {short}")
    return reasons


def index_state(project, client) -> IndexState:
    branch = current_branch(project.root)
    target = indexed_branch(project)
    name = collection_name(project.id, target)
    exists = client.collections.exists(name)
    meta = read_meta(client, name) if exists else None
    head = head_commit(project.root)
    rules_head = head if branch == target else None   # another branch's HEAD says nothing about this collection
    stale: list[str] = []
    rebuild: list[str] = []
    notes: list[str] = []
    if head is None:
        notes.append("not a git repository (or no commits yet): merge, history and curation checks skipped")
    if branch != target:
        notes.append(f"single-collection mode: answers come from {target}; changes on {branch} are not reflected")
    if not exists:
        stale.append("index missing: run `reasonhold index`")
        rebuild.append("no index for this branch yet")
    elif meta is None:
        stale.append("collection has no ReasonHold metadata: run `reasonhold index --full`")
        rebuild.append("collection has no ReasonHold metadata")
    else:
        rebuild = rebuild_reasons(project, meta, rules_head)
        stale.extend(rebuild)
        if not rebuild and rules_head and meta.indexed_commit and rules_head != meta.indexed_commit:
            stale.append(
                f"HEAD moved since the index was built ({meta.indexed_commit[:8]}..{rules_head[:8]}): run `reasonhold index`"
            )
        if meta.manifest_sha256 != file_sha256(project.manifest_path):
            stale.append("the manifest changed since the index was built: run `reasonhold index`")
    return IndexState(project.id, branch, target, name, exists, meta, head, stale, rebuild, notes)


def _lock_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "reasonhold" / "locks"


@contextmanager
def index_lock(name: str, *, lock_dir: Path | None = None) -> Iterator[None]:
    directory = lock_dir or _lock_dir()
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / f"{name}.lock", "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ReasonHoldError(
                f"another `reasonhold index` is running for {name}; try again when it finishes"
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


@dataclass
class IndexReport:
    collection: str
    full: bool
    reasons: list[str]
    dry_run: bool = False
    files_indexed: int = 0
    files_skipped: int = 0
    chunks: int = 0
    orphans_removed: int = 0
    warnings: list[str] = field(default_factory=list)
    curation: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def corpus_files(project, area_names=None) -> list[tuple[str, Path]]:
    globs = project.corpus_globs(area_names)
    if project.pending_path.exists():
        globs.append(project.pending_rel)
    return gather_files(project.root, globs, decisions_path=project.decisions_path, pending_path=project.pending_path)


def run_index(project, client, provider, *, full=False, dry_run=False, area_names=None, out=print, now=None) -> IndexReport:
    state = index_state(project, client)
    if state.branch != state.indexed_branch:
        return IndexReport(state.collection, False, [], dry_run=dry_run,
                           warnings=[f"single-collection mode: `reasonhold index` runs only on {state.indexed_branch}"])
    reasons = (["--full requested"] if full else []) + list(state.rebuild)
    full = bool(reasons)
    report = IndexReport(state.collection, full, reasons, dry_run=dry_run)
    files = corpus_files(project, area_names)

    def enrich(chunk):
        return enrich_for_project(chunk, project)

    if dry_run:
        report.chunks = sum(
            index_file(None, None, project.manifest, t, p, root=project.root, dry_run=True, enrich=enrich) for t, p in files
        )
        return report

    if state.meta is not None and not full:
        check_model(state.meta, provider)
    previous = state.meta
    meta = CollectionMeta(
        project=project.id,
        branch=state.indexed_branch,
        model_id=provider.model_id,
        dims=provider.dims,
        manifest_sha256=file_sha256(project.manifest_path),
        authority_sha256=ladder_sha256(project.ladder),
        retraction_sha256=DecisionLog.load(project.decisions_path).retraction_sha256(),
        indexed_commit=previous.indexed_commit if previous else None,
        last_full_index=previous.last_full_index if previous else None,
    )
    with index_lock(state.collection):
        ensure_collection(client, state.collection, meta, recreate=full)
        collection = client.collections.get(state.collection)
        indexed = {} if full else get_indexed_mtimes(collection)
        overlay = load_retraction_overlay(project.decisions_path, PendingLog.load(project.pending_path).aliases())
        indexed_paths: set[str] = set()
        for file_type, path in files:
            rel = path.relative_to(project.root).as_posix()
            indexed_paths.add(rel)
            stored = _as_datetime(indexed.get(rel))
            if stored is not None and datetime.fromtimestamp(path.stat().st_mtime, tz=UTC) <= stored:
                report.files_skipped += 1
                continue
            try:
                count = index_file(collection, provider, project.manifest, file_type, path, root=project.root,
                                   retraction_overlay=overlay, enrich=enrich)
            except StoreUnavailable:
                raise  # the embedding service went away: stop, and leave indexed_commit where it was
            except Exception as exc:
                report.warnings.append(f"{rel}: skipped ({type(exc).__name__}: {exc})")
                continue
            if count:
                out(f"  {rel}: {count} chunks")
                report.files_indexed += 1
                report.chunks += count
        report.orphans_removed = clean_orphans(collection, indexed_paths)
        if full:
            stored_total = collection.aggregate.over_all(total_count=True).total_count
            if stored_total != report.chunks:
                report.warnings.append(
                    f"reported {report.chunks} chunks but the collection holds {stored_total}; "
                    "the index is incomplete, re-run with --full"
                )
        meta.indexed_commit = state.head
        if full:
            meta.last_full_index = (now or datetime.now(UTC)).isoformat()
        write_meta(client, state.collection, meta)
    return report


def gc_candidates(project, client) -> list[str]:
    if head_commit(project.root) is None:
        return []  # without git there is no list of live branches to compare against
    branches = local_branches(project.root)
    prefix = collection_name(project.id, "main").rsplit("__", 1)[0] + "__"
    out = []
    for name in list_collections(client, prefix):
        meta = read_meta(client, name)
        if meta is None or meta.project != project.id:
            continue
        if meta.branch.startswith("detached-") or meta.branch == "no-git":
            continue  # unresolvable: never collected
        if meta.branch not in branches:
            out.append(name)
    return out


def gc(project, client, *, yes=False, confirm=None, out=print) -> list[str]:
    candidates = gc_candidates(project, client)
    if not candidates:
        out("nothing to collect")
        return []
    for name in candidates:
        out(f"  {name}")
    if not yes:
        answer = (confirm or input)(f"Drop {len(candidates)} collection(s)? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            out("nothing dropped")
            return []
    for name in candidates:
        drop_collection(client, name)
    return candidates
```

- [ ] **Step 4: Run the tests and the suite**

Run: `.venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -q -m "Index lifecycle: per-branch state, full re-index rule, staleness, index lock, run_index and gc"
```

---

### Task 10: Governance and curation

**Files:**
- Create: `src/reasonhold/governance.py`, `src/reasonhold/curation.py`, `tests/test_governance.py`, `tests/test_curation.py`
- Modify: `src/reasonhold/lifecycle.py` (`run_index` curates first)

**Interfaces:**
- Consumes: `classify`, `level_weights`, `path_matches` (Task 2); `identity.git` (Task 4); `DecisionLog` (Task 6); `PendingLog`, `follow_alias`, `make_record`, `resolve` (Task 7); `append_jsonl` (Task 6); `index_state` (Task 9).
- Produces:

```python
# governance.py
SOURCE_SUFFIXES: tuple[str, ...]
def covers(pattern: str, path: str) -> bool        # "dir/" prefix, glob, exact file, or directory prefix
def normalize_path(path: str) -> str               # ValueError on absolute or escaping paths
def retractions_for(project, path: str) -> list[dict]
# each: {"path", "section", "retraction_summary", "decision_id", "topic", "date", "via_alias": bool}
def governing_docs(project, path: str) -> dict
# {"path", "area", "documents": [doc...], "overlap_hints": [...], "open_candidates": [...]}
# doc: {"path", "exists", "binding": {"kind": "check"|"area"|"global", "name"}, "authority_level",
#       "weight", "retractions": [...], "open_conflicts": [...], "open_candidates": [...]}
def decision(project, id: str) -> dict             # {"record", "status", "superseded_by"}; UnknownRecord
def conflicts(project, path: str | None = None, open_only: bool = True) -> list[dict]   # record plus "open", "resolution"
def coverage(project) -> dict
# {"uncovered_sources", "unplaced_docs", "unbound_sources", "missing_references", "holes": int}

# curation.py
@dataclass
class CurationEdit:
    cause: str                 # "rename" | "deletion"
    old_path: str
    new_path: str | None
    locations: list[str]       # manifest lists that were edited
    kept: list[str]            # lists where a deletion would have emptied the list (coverage reports the hole)
    def as_dict(self) -> dict
def detect_changes(root: Path, since: str) -> tuple[dict[str, str], list[str]]   # renames old->new, deletions
def curate(project, *, since: str | None, dry_run: bool = True) -> list[CurationEdit]
def promote(project, pending_id: str, *, provenance: dict) -> dict
def reject(project, pending_id: str, *, note: str | None = None, provenance: dict) -> dict
CURATION_PROVENANCE = {"kind": "agent", "actor": "reasonhold-curate"}
```

Governing-document rule (R-02, spec section 5), computed from the manifest only:
1. Every check whose `validates_against` covers the path contributes its `reads` (binding `check`).
2. The area the path belongs to (first matching area, the seed's `infer_area`) contributes its `docs` (binding `area`).
3. `global.docs` contribute with binding `global`.
4. A document reached twice keeps its strongest binding (check, then area, then global). Archival documents never govern.
5. Order: authority weight (highest first), then ladder position, then binding strength, then path. Weight comes first because the default ladder is ordered for classification (first match wins), not by authority: `project-guidance` precedes `architecture` there but weighs less.

Overlap hints: two or more governing documents at the same authority level with no whole-document retraction. A hint is not stored.

Coverage (R-03): files come from `git ls-files --cached --others --exclude-standard` (or a filesystem walk without git, skipping the indexer's excluded parts). A source file has a suffix in `SOURCE_SUFFIXES`. `uncovered_sources`: sources no area claims. `unbound_sources`: sources an area claims but no check's `validates_against` covers. A document is a `.md` file the ladder classifies at a level other than `tooling` or `test`; `unplaced_docs` are documents not named in any area's `docs`, any check's `reads`, `global.docs`, `global.archival`, or a literal (non-glob) `global.index` entry. `missing_references`: literal manifest entries naming files that do not exist. `holes` counts `uncovered_sources`, `unplaced_docs` and `missing_references`; `unbound_sources` is reported but is not a hole, because not every module needs a check.

Mechanical curation (spec 6.1) edits only these lists: `global.docs`, `global.archival`, `global.index`, `areas.*.docs`, `areas.*.index`, `checks.*.reads`, and only entries exactly equal to the old path. A rename also appends a `path_alias` record when the old path appears in the manifest or in an active retraction and no identical alias exists yet. A deletion removes the entry unless the list would become empty. Every applied edit appends a `curation` record. A plain `mv` of an untracked destination shows up as a deletion; `git mv` shows up as a rename. Edits are left uncommitted in the working tree.

- [ ] **Step 1: Write the failing tests**

`tests/test_governance.py`:

```python
import pytest

from helpers import MINIMAL_MANIFEST, git, make_repo, write
from reasonhold.errors import UnknownRecord
from reasonhold.governance import conflicts, coverage, decision, governing_docs, retractions_for
from reasonhold.jsonl import append_jsonl
from reasonhold.pending import make_record
from reasonhold.project import Project
from reasonhold.writes import propose_binding, report_conflict, store_decision

HUMAN, AGENT = {"kind": "human"}, {"kind": "agent"}


class NoEmbed:
    model_id, dims = "x", 1

    def embed(self, texts):
        return [[0.0] for _ in texts]


def decide(project, **kw):
    args = dict(topic="t", decision="d", rationale="r", provenance=HUMAN)
    args.update(kw)
    return store_decision(project, None, NoEmbed(), **args)["record"]


@pytest.fixture
def project(tmp_path):
    return Project.load(make_repo(tmp_path))


def test_governing_docs_orders_by_authority_then_binding(project):
    out = governing_docs(project, "src/worker/main.py")
    assert out["area"] == "worker"
    assert [(d["path"], d["binding"]["kind"]) for d in out["documents"]] == [
        ("docs/architecture/overview.md", "global"),
        ("docs/specs/worker.md", "check"),
    ]
    assert out["documents"][0]["authority_level"] == "architecture"


def test_retractions_conflicts_and_candidates_attach(project):
    decide(project, supersedes=[{"path": "docs/specs/worker.md#Retries", "retraction_summary": "no retries"}])
    c = report_conflict(project, doc_a="docs/architecture/overview.md", doc_b="docs/specs/worker.md#Retries",
                        paths=["src/worker/"], claim="retry count", evidence_a="a", evidence_b="b", provenance=AGENT)
    cand = propose_binding(project, target="worker-contract", reads=["docs/specs/retry.md"],
                           validates_against=["src/worker/"], reason="r", provenance=AGENT)
    out = governing_docs(project, "src/worker/main.py")
    spec = out["documents"][1]
    assert spec["retractions"][0]["retraction_summary"] == "no retries"
    assert [x["id"] for x in spec["open_conflicts"]] == [c["id"]]
    assert [x["id"] for x in out["open_candidates"]] == [cand["id"]]
    assert [x["id"] for x in conflicts(project, path="docs/specs/worker.md")] == [c["id"]]


def test_overlap_hint_for_same_level_docs(tmp_path):
    manifest = MINIMAL_MANIFEST.replace("docs: [docs/architecture/overview.md]",
                                        "docs: [docs/architecture/overview.md, docs/architecture/queue.md]")
    root = make_repo(tmp_path, manifest)
    write(root, "docs/architecture/queue.md", "# Queue\n")
    project = Project.load(root)
    (hint,) = governing_docs(project, "src/worker/main.py")["overlap_hints"]
    assert hint["level"] == "architecture" and len(hint["documents"]) == 2
    decide(project, supersedes=[{"path": "docs/architecture/queue.md", "retraction_summary": "gone"}])
    assert governing_docs(project, "src/worker/main.py")["overlap_hints"] == []


def test_archival_documents_never_govern(tmp_path):
    manifest = MINIMAL_MANIFEST.replace("  index: [AGENTS.md]", "  archival: [docs/architecture/overview.md]\n  index: [AGENTS.md]")
    project = Project.load(make_repo(tmp_path, manifest))
    assert "docs/architecture/overview.md" not in [d["path"] for d in governing_docs(project, "src/worker/main.py")["documents"]]


def test_governing_docs_rejects_escaping_paths(project):
    with pytest.raises(ValueError):
        governing_docs(project, "../etc/passwd")


def test_retractions_follow_path_aliases(project):
    decide(project, supersedes=[{"path": "docs/old.md", "retraction_summary": "wrong"}])
    append_jsonl(project.pending_path, make_record("path_alias", {"old_path": "docs/old.md", "new_path": "docs/new.md"}, AGENT))
    (r,) = retractions_for(project, "docs/new.md")
    assert r["via_alias"] is True and r["retraction_summary"] == "wrong"


def test_decision_lookup(project):
    a = decide(project, topic="a", datetime_="t1")
    b = decide(project, topic="b", datetime_="t2", supersedes_records=[a["id"]])
    got = decision(project, a["id"])
    assert got["status"] == "superseded" and got["superseded_by"] == [b["id"]]
    with pytest.raises(UnknownRecord):
        decision(project, "dec-000000000000")


def test_coverage_reports_holes(project):
    write(project.root, "src/other/x.py", "x = 1\n")
    write(project.root, "docs/specs/orphan.md", "# Orphan\n")
    out = coverage(project)
    assert out["uncovered_sources"] == ["src/other/x.py"]
    assert out["unplaced_docs"] == ["docs/specs/orphan.md"]
    assert out["unbound_sources"] == [] and out["missing_references"] == []
    assert out["holes"] == 2


def test_coverage_without_git(tmp_path):
    project = Project.load(make_repo(tmp_path, commit=False))
    assert coverage(project)["holes"] == 0
```

`tests/test_curation.py`:

```python
import pytest

from helpers import FakeClient, FakeProvider, MINIMAL_MANIFEST, git, make_repo, write
from reasonhold.curation import curate, promote, reject
from reasonhold.errors import UnknownRecord
from reasonhold.lifecycle import run_index
from reasonhold.pending import PendingLog
from reasonhold.project import Project
from reasonhold.writes import propose_binding

AGENT, HUMAN = {"kind": "agent"}, {"kind": "human"}
COMMENTED = "# Placement is declared, never inferred.\n" + MINIMAL_MANIFEST.replace(
    "docs: [docs/specs/worker.md]", "docs: [docs/specs/worker.md, docs/specs/extra.md]")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    root = tmp_path / "repo"
    root.mkdir()
    write(root, "docs/specs/extra.md", "# Extra\n")
    return make_repo(root, COMMENTED)


def test_rename_updates_every_reference_keeps_comments_and_records_an_alias(repo):
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "mv", "docs/specs/worker.md", "docs/specs/worker-v2.md")
    (edit,) = curate(Project.load(repo), since=base, dry_run=False)
    assert edit.cause == "rename" and sorted(edit.locations) == ["areas.worker.docs", "checks.worker-contract.reads"]
    text = (repo / "sync-doc.yaml").read_text()
    assert "docs/specs/worker.md" not in text and text.count("docs/specs/worker-v2.md") == 2
    assert text.startswith("# Placement is declared, never inferred.")
    log = PendingLog.load(Project.load(repo).pending_path)
    assert log.aliases() == {"docs/specs/worker.md": "docs/specs/worker-v2.md"}
    assert [r["kind"] for r in log.records] == ["path_alias", "curation"]
    assert curate(Project.load(repo), since=base, dry_run=False) == []
    assert len(PendingLog.load(Project.load(repo).pending_path).records) == 2


def test_dry_run_changes_nothing(repo):
    base = git(repo, "rev-parse", "HEAD")
    before = (repo / "sync-doc.yaml").read_text()
    git(repo, "mv", "docs/specs/worker.md", "docs/specs/worker-v2.md")
    assert len(curate(Project.load(repo), since=base, dry_run=True)) == 1
    assert (repo / "sync-doc.yaml").read_text() == before and not Project.load(repo).pending_path.exists()


def test_deletion_removes_entries_but_never_empties_a_list(repo):
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "rm", "-q", "docs/specs/extra.md", "docs/specs/worker.md")
    edits = {e.old_path: e for e in curate(Project.load(repo), since=base, dry_run=False)}
    assert edits["docs/specs/extra.md"].locations == ["areas.worker.docs"]
    assert edits["docs/specs/worker.md"].kept == ["areas.worker.docs", "checks.worker-contract.reads"]
    Project.load(repo)  # the manifest still loads: no list became empty


def test_curate_needs_a_base_commit(repo):
    assert curate(Project.load(repo), since=None, dry_run=False) == []


def test_promote_into_an_existing_check_and_into_a_new_check(repo):
    project = Project.load(repo)
    a = propose_binding(project, target="worker-contract", reads=["docs/specs/extra.md"],
                        validates_against=["src/worker/"], reason="r", provenance=AGENT)
    b = propose_binding(project, target="queue-contract", reads=["docs/architecture/overview.md"],
                        validates_against=["src/queue/"], reason="queue spec", provenance=AGENT)
    assert promote(project, a["id"], provenance=HUMAN)["created"] is False
    assert promote(project, b["id"], provenance=HUMAN)["created"] is True
    project = Project.load(repo)
    assert "docs/specs/extra.md" in project.manifest.check("worker-contract").reads
    assert project.manifest.check("queue-contract").validates_against == ("src/queue/",)
    assert PendingLog.load(project.pending_path).open() == []
    with pytest.raises(UnknownRecord):
        promote(project, a["id"], provenance=HUMAN)


def test_promote_into_an_area_and_reject(repo):
    project = Project.load(repo)
    a = propose_binding(project, target="worker", reads=["docs/architecture/overview.md"],
                        validates_against=["src/worker/"], reason="r", provenance=AGENT)
    b = propose_binding(project, target="worker", reads=["docs/specs/extra.md"],
                        validates_against=["src/worker/"], reason="r2", provenance=AGENT)
    promote(project, a["id"], provenance=HUMAN)
    reject(project, b["id"], note="duplicate", provenance=HUMAN)
    project = Project.load(repo)
    assert "docs/architecture/overview.md" in [d for a_ in project.manifest.areas if a_.name == "worker" for d in a_.docs]
    assert PendingLog.load(project.pending_path).resolution_for(b["id"])["outcome"] == "rejected"


def test_run_index_curates_first(repo):
    client = FakeClient()
    run_index(Project.load(repo), client, FakeProvider(), out=lambda *a: None)
    git(repo, "mv", "docs/specs/worker.md", "docs/specs/worker-v2.md")
    git(repo, "commit", "-qm", "rename")
    report = run_index(Project.load(repo), client, FakeProvider(), out=lambda *a: None)
    assert [c["old_path"] for c in report.curation] == ["docs/specs/worker.md"]
    assert "docs/specs/worker-v2.md" in (repo / "sync-doc.yaml").read_text()
```

Deletions are processed in sorted path order, so `extra.md` (one of two entries in `areas.worker.docs`) is removed and `worker.md` is then the last entry in both of its lists and is kept.

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_governance.py tests/test_curation.py -q`
Expected: collection errors, modules not found.

- [ ] **Step 3: Implement `governance.py`**

```python
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
```

Note that `infer_area` uses the seed's single-level matching, which is the attribution engine the spec keeps; `MINIMAL_MANIFEST` uses single-level globs (`src/worker/*.py`) for that reason.

- [ ] **Step 4: Implement `curation.py`**

```python
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
```

- [ ] **Step 5: Curate at the start of `run_index`**

In `lifecycle.run_index`, directly after the single-collection early return, add:

```python
    curation = []
    meta0 = state.meta
    if meta0 and meta0.indexed_commit and state.head:
        from reasonhold.curation import curate
        from reasonhold.project import Project

        edits = curate(project, since=meta0.indexed_commit, dry_run=dry_run)
        curation = [e.as_dict() for e in edits]
        if edits and not dry_run:
            project = Project.load(project.root)
            for e in edits:
                out(f"  curated: {e.describe()}")
```

and set `report.curation = curation` right after `report` is created. The imports are local to keep `lifecycle` importable without `ruamel.yaml` during preamble rendering.

- [ ] **Step 6: Run the tests and the suite**

Run: `.venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -q -m "Governance (governing_docs, retractions, conflicts, coverage) and mechanical curation with human-only promotion"
```

---

### Task 11: Search and the code-index seam

**Files:**
- Create: `src/reasonhold/search.py`, `tests/test_search.py`, `tests/test_codeindex.py`
- Move: `src/reasonhold/symbols.py` to `src/reasonhold/codeindex.py` (`git mv`, then edit)
- Modify: `src/reasonhold/server.py` (imports only)
- Modify tests: `tests/test_rerank.py`, `tests/test_symbols.py`

**Interfaces:**
- Consumes: `level_weights`, `DEFAULT_LADDER` (Task 2); `EmbeddingProvider` (Task 5); `get_indexed_mtimes` (Task 8); `corpus_files`, `IndexState` (Task 9); `IndexMissing`, `IndexStale` (Task 2).
- Produces:

```python
# search.py (reranker moved verbatim from seed server.py)
QUERY_INTENT_PATTERNS, DOCUMENT_KIND_WEIGHTS, DECISION_INTENT_WEIGHTS, CONCEPTUAL_INTENT_WEIGHTS,
SYMBOL_INTENT_WEIGHTS, EXACT_MATCH_WEIGHTS                  # seed constants, unchanged
DECISION_STATUSES = ("active", "superseded", "all")
def _detect_query_intents(query: str) -> dict[str, float]  # seed
def _rerank_docs(query: str, results: list[dict], authority_weights: dict[str, float] | None = None) -> list[dict]
def _rerank_score(query: str, query_intents: dict, result: dict, authority_weights: dict[str, float]) -> float
def search_docs(collection, provider, query: str, top_k: int = 5, *, authority_weights: dict[str, float]) -> list[dict]
def search_decisions(collection, provider, query: str, top_k: int = 5, status: str = "active") -> list[dict]

# codeindex.py (seed symbols.py minus its CLI): the one module that reads code chunks
CODE_FILE_TYPES = ("python", "csharp", "sql")
# kept from the seed: QUERY_PROPERTIES, PAGE_SIZE, FreshnessReport, coerce_mtime, compare_freshness,
#   select_by_prefix, symbol_names, build_filter, query_chunks, chunk_type_inventory
def is_code(result: dict) -> bool                       # file_type in CODE_FILE_TYPES
def scan_working_tree(project) -> tuple[dict[str, datetime], set[str]]
def freshness(project, collection) -> FreshnessReport
def symbols(collection, chunk_type: str, file_prefix: str | None = None, names_only: bool = False) -> list
def inventory(collection) -> dict[str, int]
def list_indexed_files(collection) -> list[dict]        # seed server.list_indexed_files body
def absence_guard(state, report: FreshnessReport | None) -> None   # IndexMissing / IndexStale
```

Ruling on spec section 5 ("each hit carries any retraction: summary, decision id, date"): chunks keep the seed's `retraction_decision` = decision topic (the schema documents it so, and seed tests pin it); the decision id is available from `retractions_for(path)` and `governing_docs(path)`, which agents call before trusting a document. Each `search_docs` hit is the seed's dict plus `record_id`, `kind` (`"code"` when `is_code`, `"decision"`, `"pending"`, else `"document"`) and the retraction fields when present. Each `search_decisions` hit is the seed's parsed dict plus `"id"` (the chunk's `record_id`) and `"status"` (the chunk's `decision_status` property, not text parsed from the content). The status filter is `decision_status == status` on the stored property (R-12); `"all"` applies no status filter; anything else raises `ValueError`.

Absence rule (spec section 5, Exact): an exact query that finds nothing, against a missing or stale index, raises instead of returning an empty list. `absence_guard` raises `IndexMissing` when `state.exists` is false, and `IndexStale` naming every cause when `state.stale` is non-empty or the freshness report is not clean. A non-empty result is returned with the staleness in the result's index block.

- [ ] **Step 1: Write the failing tests**

`tests/test_search.py`:

```python
from types import SimpleNamespace

import pytest

from helpers import FakeProvider
from reasonhold.search import search_decisions, search_docs


class VectorCollection:
    def __init__(self, hits):
        self.hits, self.calls = hits, []
        self.query = SimpleNamespace(near_vector=self.near_vector)

    def near_vector(self, near_vector, limit, filters=None, return_metadata=None):
        self.calls.append({"limit": limit, "filters": filters})
        objs = [SimpleNamespace(properties=p, metadata=SimpleNamespace(distance=d)) for p, d in self.hits]
        return SimpleNamespace(objects=objs[:limit])


def hit(path, level, **extra):
    return {"file_path": path, "authority_level": level, "document_kind": "", "chunk_type": "markdown_section",
            "file_type": "markdown", "section_heading": "", "type_name": "", "member_name": "", "content": "c", **extra}


def test_search_docs_reranks_with_ladder_weights():
    col = VectorCollection([(hit("a.md", "low"), 0.30), (hit("b.md", "high"), 0.31)])
    out = search_docs(col, FakeProvider(), "anything", authority_weights={"high": 0.1, "low": 0.0})
    assert [r["file_path"] for r in out] == ["b.md", "a.md"]
    out = search_docs(col, FakeProvider(), "anything", authority_weights={"high": 0.0, "low": 0.1})
    assert [r["file_path"] for r in out] == ["a.md", "b.md"]


def test_search_docs_carries_retraction_kind_and_record_id():
    col = VectorCollection([
        (hit("docs/x.md", "architecture", retraction_summary="now LIFO", retraction_decision="q", retraction_date="d"), 0.1),
        (hit("src/a.py", "implementation", file_type="python", chunk_type="python_function"), 0.2),
        (hit("decisions.jsonl", "decision", file_type="decisions", chunk_type="decision", record_id="dec-1"), 0.3),
    ])
    out = {r["file_path"]: r for r in search_docs(col, FakeProvider(), "q", authority_weights={})}
    assert out["docs/x.md"]["retraction_summary"] == "now LIFO" and out["docs/x.md"]["kind"] == "document"
    assert out["src/a.py"]["kind"] == "code"
    assert out["decisions.jsonl"]["kind"] == "decision" and out["decisions.jsonl"]["record_id"] == "dec-1"


def test_search_decisions_filters_on_the_status_property():
    props = {"content": "Decision: d\nRationale: r\nStatus: active", "section_heading": "t",
             "record_id": "dec-1", "decision_status": "superseded"}
    col = VectorCollection([(props, 0.2)])
    (r,) = search_decisions(col, FakeProvider(), "q", status="superseded")
    assert r["id"] == "dec-1" and r["status"] == "superseded"     # the property wins over the text
    assert [f.target for f in col.calls[0]["filters"].filters] == ["chunk_type", "decision_status"]
    search_decisions(col, FakeProvider(), "q", status="all")
    assert col.calls[1]["filters"].target == "chunk_type"
    with pytest.raises(ValueError):
        search_decisions(col, FakeProvider(), "q", status="retired")
```

`tests/test_codeindex.py`:

```python
import os
from datetime import UTC, datetime

import pytest

from helpers import FakeCollection, make_repo
from reasonhold.codeindex import absence_guard, freshness, is_code
from reasonhold.errors import IndexMissing, IndexStale
from reasonhold.lifecycle import IndexState
from reasonhold.project import Project


def state(exists=True, stale=()):
    return IndexState("p", "main", "main", "RH_P__main", exists, None, None, list(stale), [], [])


def test_freshness_compares_the_corpus_with_the_index(tmp_path):
    project = Project.load(make_repo(tmp_path, commit=False))
    col = FakeCollection()
    old = datetime(2020, 1, 1, tzinfo=UTC).isoformat()
    col.add("1", file_path="AGENTS.md", last_modified=old)
    col.add("2", file_path="gone.md", last_modified=old)
    report = freshness(project, col)
    assert "AGENTS.md" in report.stale and "gone.md" in report.orphaned
    assert "docs/specs/worker.md" in report.missing and "decisions.jsonl" in report.empty


def test_absence_guard():
    absence_guard(state(), None)
    with pytest.raises(IndexMissing):
        absence_guard(state(exists=False), None)
    with pytest.raises(IndexStale, match="HEAD moved"):
        absence_guard(state(stale=["HEAD moved"]), None)


def test_is_code():
    assert is_code({"file_type": "python"}) and not is_code({"file_type": "markdown"})
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_search.py tests/test_codeindex.py -q`
Expected: collection errors, modules not found.

- [ ] **Step 3: Create `search.py`**

Move from `server.py` into `search.py`, verbatim: `QUERY_INTENT_PATTERNS`, `DOCUMENT_KIND_WEIGHTS`, `DECISION_INTENT_WEIGHTS`, `CONCEPTUAL_INTENT_WEIGHTS`, `SYMBOL_INTENT_WEIGHTS`, `EXACT_MATCH_WEIGHTS`, `_detect_query_intents`, and the comment block above the weights. Delete `AUTHORITY_WEIGHTS`; authority weights now come from the ladder. Then:

```python
import weaviate.classes.query as wvq

from reasonhold.authority import DEFAULT_LADDER, level_weights
from reasonhold.codeindex import is_code

DECISION_STATUSES = ("active", "superseded", "all")


def _rerank_docs(query, results, authority_weights=None):
    weights = level_weights(DEFAULT_LADDER) if authority_weights is None else authority_weights
    query_intents = _detect_query_intents(query)
    for result in results:
        result["rerank_score"] = round(_rerank_score(query, query_intents, result, weights), 4)
    results.sort(key=lambda item: item["rerank_score"], reverse=True)
    return results
```

`_rerank_score(query, query_intents, result, authority_weights)` is the seed body with `AUTHORITY_WEIGHTS.get(authority, 0.0)` replaced by `authority_weights.get(authority, 0.0)`.

```python
def _kind(props: dict) -> str:
    if props.get("chunk_type") == "decision":
        return "decision"
    if props.get("chunk_type") == "pending":
        return "pending"
    return "code" if is_code(props) else "document"


def search_docs(collection, provider, query, top_k=5, *, authority_weights):
    vector = provider.embed([query])[0]
    results = collection.query.near_vector(
        near_vector=vector, limit=top_k, return_metadata=wvq.MetadataQuery(distance=True)
    )
    output = []
    for obj in results.objects:
        p = obj.properties
        result = {
            "score": round(1.0 - (obj.metadata.distance or 0.0), 4),
            "file_path": p.get("file_path", ""),
            "chunk_type": p.get("chunk_type", ""),
            "file_type": p.get("file_type", ""),
            "kind": _kind(p),
            "authority_level": p.get("authority_level", ""),
            "document_kind": p.get("document_kind", ""),
            "area": p.get("area", ""),
            "section_heading": p.get("section_heading", ""),
            "type_name": p.get("type_name", ""),
            "member_name": p.get("member_name", ""),
            "record_id": p.get("record_id") or "",
            "content": p.get("content", ""),
        }
        if p.get("retraction_summary"):
            result["retraction_summary"] = p["retraction_summary"]
            result["retraction_decision"] = p.get("retraction_decision", "")
            result["retraction_date"] = p.get("retraction_date", "")
        output.append(result)
    return _rerank_docs(query, output, authority_weights)


def search_decisions(collection, provider, query, top_k=5, status="active"):
    if status not in DECISION_STATUSES:
        raise ValueError(f"status must be one of {', '.join(DECISION_STATUSES)}")
    filters = wvq.Filter.by_property("chunk_type").equal("decision")
    if status != "all":
        filters = filters & wvq.Filter.by_property("decision_status").equal(status)
    vector = provider.embed([query])[0]
    results = collection.query.near_vector(
        near_vector=vector, filters=filters, limit=top_k, return_metadata=wvq.MetadataQuery(distance=True)
    )
    output = []
    for obj in results.objects:
        content = obj.properties.get("content", "")
        parsed = {}
        for line in content.split("\n"):
            if ": " in line:
                key, _, value = line.partition(": ")
                parsed[key.lower()] = value
        output.append({
            "score": round(1.0 - (obj.metadata.distance or 0.0), 4),
            "id": obj.properties.get("record_id") or "",
            "topic": obj.properties.get("section_heading", ""),
            "decision": parsed.get("decision", ""),
            "rationale": parsed.get("rationale", ""),
            "alternatives": parsed.get("alternatives considered", ""),
            "context": parsed.get("context", ""),
            "date": parsed.get("date", ""),
            "status": obj.properties.get("decision_status") or parsed.get("status", "active"),
        })
    return output
```

In `server.py`, replace the moved definitions with `from reasonhold.search import _detect_query_intents, _rerank_docs` (its tools keep working until Task 14).

- [ ] **Step 4: Create `codeindex.py` from `symbols.py`**

`git mv src/reasonhold/symbols.py src/reasonhold/codeindex.py`. Keep the module docstring (retitled "the code-index seam: exact queries and freshness; the only module that reads code chunks, replaceable by a Serena adapter"), every pure helper and `query_chunks`, `build_filter`, `chunk_type_inventory` verbatim. Delete `_open_collection`, `_emit`, `_run_freshness`, `main`, the `__main__` block, `argparse`, and the `config` and `manifest` imports. Replace `scan_working_tree` and `indexed_mtimes` and add the new functions:

```python
from reasonhold.errors import IndexMissing, IndexStale

CODE_FILE_TYPES = ("python", "csharp", "sql")


def is_code(result: dict) -> bool:
    return result.get("file_type") in CODE_FILE_TYPES


def scan_working_tree(project) -> tuple[dict[str, datetime], set[str]]:
    from reasonhold.lifecycle import corpus_files

    mtimes: dict[str, datetime] = {}
    empty: set[str] = set()
    for _file_type, path in corpus_files(project):
        rel = path.relative_to(project.root).as_posix()
        stat = path.stat()
        mtimes[rel] = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        if stat.st_size == 0:
            empty.add(rel)
    return mtimes, empty


def freshness(project, collection) -> FreshnessReport:
    from reasonhold.indexer import get_indexed_mtimes

    working, empty = scan_working_tree(project)
    return compare_freshness(get_indexed_mtimes(collection), working, empty=empty)


def symbols(collection, chunk_type, file_prefix=None, names_only=False):
    rows = select_by_prefix(query_chunks(collection, chunk_type=chunk_type), [file_prefix] if file_prefix else None)
    return symbol_names(rows) if names_only else rows


def inventory(collection) -> dict[str, int]:
    return chunk_type_inventory(collection)


def list_indexed_files(collection) -> list[dict]:
    file_info: dict[str, dict] = {}
    for obj in collection.iterator(include_vector=False):
        fp = obj.properties.get("file_path", "")
        lm = obj.properties.get("last_modified")
        if fp not in file_info:
            file_info[fp] = {"file_path": fp, "chunk_count": 0, "last_indexed": None}
        file_info[fp]["chunk_count"] += 1
        if lm:
            ts = lm if isinstance(lm, str) else lm.isoformat()
            if file_info[fp]["last_indexed"] is None or ts > file_info[fp]["last_indexed"]:
                file_info[fp]["last_indexed"] = ts
    return sorted(file_info.values(), key=lambda x: x["file_path"])


def absence_guard(state, report=None) -> None:
    if not state.exists:
        raise IndexMissing(f"no index for {state.indexed_branch}: run `reasonhold index`")
    reasons = list(state.stale)
    if report is not None and not report.is_clean:
        reasons.append(report.summary())
    if reasons:
        raise IndexStale("an empty answer from a stale index proves nothing: " + "; ".join(reasons))
```

(`list_indexed_files` is the seed `server.list_indexed_files` body, operating on the `collection` argument instead of opening a client.) `FreshnessReport.summary()` keeps its seed text except for the em dash after `FRESH` and after `STALE`, which become `FRESH: ` and `STALE: ` (user-facing text). If a seed test asserts the old text, update that literal only.

- [ ] **Step 5: Port the seed tests**

- `tests/test_rerank.py`: `from reasonhold.search import _detect_query_intents, _rerank_docs`. Calls without weights use the default ladder's weights, which Task 2 proved equal to the seed's.
- `tests/test_enrichment.py`: `TestAuthorityWeightsCoverTheLadder` imports `AUTHORITY_WEIGHTS` from `reasonhold.server`; replace that import with `from reasonhold.authority import DEFAULT_LADDER, level_weights` and `AUTHORITY_WEIGHTS = level_weights(DEFAULT_LADDER)`.
- `tests/test_symbols.py`: import from `reasonhold.codeindex`; the two source-reading tests read `Path(reasonhold.codeindex.__file__).read_text()` instead of `symbols.py`.

- [ ] **Step 6: Run the tests and the suite**

Run: `.venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -q -m "Search with ladder weights and status-property filter; code-index seam with the absence guard"
```

---

### Task 12: The session preamble

**Files:**
- Move: `src/reasonhold/bootstrap.py` to `src/reasonhold/preamble.py` (`git mv`, then edit)
- Move: `tests/test_bootstrap.py` to `tests/test_preamble.py` (`git mv`, then edit)

**Interfaces:**
- Consumes: `Project` (Task 3); `iter_supersedes_rows` (Task 6); `PendingLog` (Task 7); `index_state` (Task 9); `connect` (Task 5).
- Produces:

```python
MAX_PREAMBLE_LINES = 60
MAX_PREAMBLE_BYTES = 4096
ROLE_A_MAX_ROWS = 25
TIMEOUT_INDEX = 6.0                          # seconds allowed for the index-state probe
# kept from the seed: SupersedesRow, _cell, load_active_supersedes(decisions_file), render_role_a, _role_a_table
@dataclass
class Section:
    title: str
    rows: list[str]                          # whole rows, newest first; dropped from the end, never cut
    empty: str | None                        # line shown when there were never any rows; None: omit the section
    more: str                                # footer command hint, e.g. "`reasonhold conflicts` for the rest"
    header: list[str] = field(default_factory=list)   # lines printed above the rows (table head)
def fit(sections: list[Section], max_lines: int, max_bytes: int) -> str
def index_lines(project, *, connect=None, timeout: float = TIMEOUT_INDEX) -> list[str]   # never raises
def render_preamble(root: Path | str | None = None, *, max_lines: int = MAX_PREAMBLE_LINES,
                    max_bytes: int = MAX_PREAMBLE_BYTES, index_probe=None) -> str     # never raises
def claude_hook_json(text: str) -> str
```

Sections, in priority order (R-08): **Index** (branch, collection, fresh or the stale causes, notes), **Superseded content** (the seed's table), **Open conflicts**, **Open candidates**. `fit` renders all rows, then, while the text is over either limit, drops the last row of the lowest-priority section that still has rows; a section that lost rows ends with `*N most recent of M. <more>*`. The Index section is never trimmed (its rows are few and it is the one that says whether anything else can be trusted). Without a manifest, the preamble is one line saying ReasonHold is not configured here. Every failure inside rendering becomes a line of output; nothing raises.

- [ ] **Step 1: Write the failing tests**

In `tests/test_preamble.py` (the moved seed file):

- Import from `reasonhold.preamble`; keep `TestLoadActiveSupersedes`, `TestRenderRoleA` and `TestSharedParsing` (point their source reads at `Path(reasonhold.preamble.__file__)`, and their overlay import at `reasonhold.overlay`). `TestSharedParsing` asserts the source contains no `open(`; that is why `render_preamble` filters `pending.records` with `is_open` instead of calling `PendingLog.open`. Replace the em dash in `render_role_a`'s overflow line (after `active supersessions`) with a colon.
- Delete `TestRoleCFreshness` (the commit and PR lines are gone: the spec's preamble is index state, retractions, conflicts and candidates). If a kept seed test depends on a removed seed internal (a `config` default argument, `_run`), delete that one test and name it in the task report. Replace `TestPreambleBudget` and `TestTimeoutBudget` with:

```python
import json

from helpers import make_repo
from reasonhold.errors import StoreUnavailable
from reasonhold.jsonl import append_jsonl
from reasonhold.pending import make_record
from reasonhold.preamble import (
    MAX_PREAMBLE_BYTES,
    MAX_PREAMBLE_LINES,
    TIMEOUT_INDEX,
    claude_hook_json,
    render_preamble,
)

AGENT = {"kind": "agent"}
LONG = "A retraction summary of the length these actually run to in practice, a sentence or two of prose."


def crowded_repo(tmp_path):
    root = make_repo(tmp_path, commit=False)
    with open(root / "decisions.jsonl", "w") as fh:
        for i in range(40):
            fh.write(json.dumps({"topic": f"topic-{i:02d}", "decision": "d", "rationale": "r",
                                 "datetime": f"2026-09-{1 + i % 28:02d}T00:00:{i:02d}+00:00",
                                 "supersedes": [{"path": f"docs/architecture/long-document-name-{i}.md",
                                                 "retraction_summary": LONG}]}) + "\n")
    for i in range(20):
        append_jsonl(root / "reasonhold.pending.jsonl", make_record("conflict", {
            "doc_a": f"docs/a{i}.md", "doc_b": f"docs/b{i}.md", "paths": [], "claim": "they disagree about retries",
            "evidence_a": "a", "evidence_b": "b"}, AGENT, datetime_=f"t{i:02d}"))
        append_jsonl(root / "reasonhold.pending.jsonl", make_record("candidate_binding", {
            "target": "worker-contract", "reads": [f"docs/c{i}.md"], "validates_against": ["src/worker/"],
            "reason": "new spec"}, AGENT, datetime_=f"u{i:02d}"))
    return root


def fresh_probe(project):
    return ["- Branch `main`, collection `RH_X__main`: fresh"]


def within_budget(text):
    return len(text.splitlines()) <= MAX_PREAMBLE_LINES and len(text.encode()) <= MAX_PREAMBLE_BYTES


def test_preamble_fails_open_without_store(tmp_path):
    root = make_repo(tmp_path, commit=False)

    def down(project):
        raise StoreUnavailable("cannot reach Weaviate at localhost:8081")

    out = render_preamble(root, index_probe=down)
    assert "unavailable" in out and "localhost:8081" in out and within_budget(out)


def test_preamble_without_a_manifest_is_one_line(tmp_path):
    out = render_preamble(tmp_path)
    assert "not configured" in out and len(out.splitlines()) == 1


def test_budget_drops_whole_rows_lowest_priority_first(tmp_path):
    out = render_preamble(crowded_repo(tmp_path), index_probe=fresh_probe)
    assert within_budget(out)
    assert "fresh" in out                                    # the index section is never trimmed
    assert "most recent of 20" in out                        # candidates (and maybe conflicts) were trimmed
    table_rows = [ln for ln in out.splitlines() if ln.startswith("| `docs/")]
    assert table_rows and all(ln.endswith("|") for ln in table_rows)   # rows dropped whole, never cut
    assert out.index("Superseded content") < out.index("Open conflicts") < out.index("Open candidates")


def test_retractions_outrank_conflicts_and_candidates(tmp_path):
    out = render_preamble(crowded_repo(tmp_path), index_probe=fresh_probe, max_bytes=2048)
    assert len(out.encode()) <= 2048 and "| `docs/" in out
    assert "0 most recent of 20. `reasonhold candidates list`" in out
    assert "0 most recent of 20. `reasonhold conflicts`" in out


def test_claude_hook_format():
    payload = json.loads(claude_hook_json("hello"))
    assert payload == {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "hello"}}


def test_probe_timeout_is_under_the_hook_timeout():
    assert TIMEOUT_INDEX < 20
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_preamble.py -q`
Expected: ImportError on `reasonhold.preamble` names (`fit`, `claude_hook_json`, `TIMEOUT_INDEX`) until Step 3.

- [ ] **Step 3: Implement `preamble.py`**

Keep from the seed, unchanged: the module docstring (updated to describe the four sections), `SupersedesRow`, `_cell`, `render_role_a`, `_role_a_table`, `ROLE_A_MAX_ROWS`, `MAX_PREAMBLE_LINES`, `MAX_PREAMBLE_BYTES`. `load_active_supersedes(decisions_file: Path)` takes the path as a required argument (body unchanged; it reads through `iter_supersedes_rows`, so computed status applies). Delete `_run`, `render_role_c`, the seed `render_preamble`, `main`, `LAST_N_*`, `TIMEOUT_FRESHNESS`, `TIMEOUT_GIT`, `TIMEOUT_GH`, `TIMEOUT_TOTAL_BUDGET`, and the `config` import. Add:

```python
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

TIMEOUT_INDEX = 6.0


@dataclass
class Section:
    title: str
    rows: list[str]
    empty: str | None
    more: str
    header: list[str] = field(default_factory=list)


def _render(sections: list[Section], shown: list[int]) -> str:
    parts = []
    for section, n in zip(sections, shown):
        if not section.rows:
            if section.empty is not None:
                parts.append(f"## {section.title}\n\n{section.empty}\n")
            continue
        lines = [f"## {section.title}", ""] + section.header + section.rows[:n]
        if n < len(section.rows):
            lines.append(f"\n*{n} most recent of {len(section.rows)}. {section.more}*")
        parts.append("\n".join(lines) + "\n")
    return "\n".join(parts)


def fit(sections: list[Section], max_lines: int, max_bytes: int) -> str:
    shown = [len(s.rows) for s in sections]

    def over(text: str) -> bool:
        return len(text.splitlines()) > max_lines or len(text.encode()) > max_bytes

    text = _render(sections, shown)
    while over(text):
        trimmable = [i for i in range(1, len(sections)) if shown[i] > 0]   # section 0 (Index) is never trimmed
        if not trimmable:
            break
        shown[trimmable[-1]] -= 1
        text = _render(sections, shown)
    return text


def index_lines(project, *, connect=None, timeout: float = TIMEOUT_INDEX) -> list[str]:
    """One probe of the index, bounded by a daemon thread so a hung store cannot hold the session."""
    result: list[str] = []

    def probe() -> None:
        try:
            from reasonhold.lifecycle import index_state
            from reasonhold.store import connect as default_connect

            client = (connect or default_connect)()
            try:
                state = index_state(project, client)
            finally:
                client.close()
            where = f"- Branch `{state.branch}`, collection `{state.collection}`"
            if not state.exists:
                result.append(f"{where}: index missing, run `reasonhold index`")
            elif state.fresh:
                result.append(f"{where}: fresh")
            else:
                result.append(f"{where}: stale")
                result.extend(f"  - {cause}" for cause in state.stale)
            result.extend(f"- Note: {note}" for note in state.notes)
        except Exception as exc:  # fail open: any failure is a line, never an exception
            result[:] = [f"- Index: unavailable ({type(exc).__name__}: {exc})"]

    worker = threading.Thread(target=probe, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        return [f"- Index: unavailable (no answer within {timeout:.0f}s)"]
    return result or ["- Index: unavailable"]


def _retraction_rows(project) -> list[str]:
    return [
        f"| `{_cell(r.path)}` | {_cell(r.retraction_summary)} | `{_cell(r.topic)}` | {r.date.split('T')[0]} |"
        for r in load_active_supersedes(project.decisions_path)
    ]


def render_preamble(root=None, *, max_lines=MAX_PREAMBLE_LINES, max_bytes=MAX_PREAMBLE_BYTES, index_probe=None) -> str:
    try:
        from reasonhold.errors import ManifestInvalid
        from reasonhold.pending import PendingLog
        from reasonhold.project import Project

        try:
            project = Project.load(root)
        except ManifestInvalid as exc:
            return f"ReasonHold is not configured here ({exc}).\n"
        try:
            index = (index_probe or index_lines)(project)
        except Exception as exc:
            index = [f"- Index: unavailable ({type(exc).__name__}: {exc})"]
        pending = PendingLog.load(project.pending_path)
        conflicts = [
            f"- `{c['id']}` {_cell(c['doc_a'])} vs {_cell(c['doc_b'])}: {_cell(c['claim'])}"
            for c in reversed([r for r in pending.records if r["kind"] == "conflict" and pending.is_open(r["id"])])
        ]
        candidates = [
            f"- `{c['id']}` {_cell(c['target'])} <- {_cell(', '.join(c['reads']))} ({_cell(c['reason'])})"
            for c in reversed([r for r in pending.records if r["kind"] == "candidate_binding" and pending.is_open(r["id"])])
        ]
        sections = [
            Section(f"ReasonHold: {project.id}", index, None, ""),
            Section("Superseded content", _retraction_rows(project), "No active supersessions recorded.",
                    "`reasonhold decisions search` for the rest.",
                    header=["An active decision retracts each path below. Treat the summary as current truth "
                            "and the document as stale where they disagree.", "",
                            "| Path | Now holds | Decision | Date |", "|---|---|---|---|"]),
            Section("Open conflicts", conflicts, None, "`reasonhold conflicts` for the rest."),
            Section("Open candidates", candidates, None, "`reasonhold candidates list` for the rest."),
        ]
        return fit(sections, max_lines, max_bytes)
    except Exception as exc:  # the preamble always prints something and always exits 0
        return f"ReasonHold preamble unavailable ({type(exc).__name__}: {exc}).\n"


def claude_hook_json(text: str) -> str:
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}})
```

`load_active_supersedes` already sorts newest first, so the retraction rows that survive trimming are the most recent.

- [ ] **Step 4: Run the tests and the suite**

Run: `.venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -q -m "Session preamble: index state, retractions, open conflicts and candidates within a whole-row budget; fails open"
```

---

### Task 13: The `ReasonHold` facade and the CLI

**Files:**
- Create: `src/reasonhold/api.py`, `src/reasonhold/cli.py`, `tests/test_api.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: everything from Tasks 3 to 12.
- Produces:

```python
# api.py
class ReasonHold:
    project: Project
    provider: EmbeddingProvider
    def __init__(self, root: Path | str | None = None, *, settings: WeaviateSettings | None = None,
                 connect: Callable[[], object] | None = None, provider: EmbeddingProvider | None = None)
    client                                     # property, connects lazily
    def close(self) -> None                    # also __enter__ / __exit__
    def reload(self) -> None
    def state(self) -> IndexState
    # Belief: every result carrying index answers is {"index": state.as_dict(), "results": [...]}
    def search_docs(self, query: str, top_k: int = 5) -> dict
    def search_decisions(self, query: str, top_k: int = 5, status: str = "active") -> dict
    def governing_docs(self, path: str) -> dict
    def retractions_for(self, path: str) -> list[dict]
    def decision(self, id: str) -> dict
    def conflicts(self, path: str | None = None, open_only: bool = True) -> list[dict]
    # Exact
    def symbols(self, chunk_type: str, file_prefix: str | None = None, names_only: bool = False) -> dict
    def inventory(self) -> dict
    def freshness(self) -> dict
    def list_indexed_files(self) -> dict
    # Writes
    def store_decision(self, **kwargs) -> dict
    def propose_binding(self, **kwargs) -> dict
    def report_conflict(self, **kwargs) -> dict
    def resolve(self, **kwargs) -> dict
    # Governance
    def coverage(self) -> dict
    def check(self) -> list[dict]
    def curate(self, dry_run: bool = True) -> dict
    def preamble(self, max_lines: int = 60, max_bytes: int = 4096) -> str
    # Administration (CLI only; never exposed to agents)
    def index(self, full: bool = False, dry_run: bool = False, areas: list[str] | None = None, out=print) -> dict
    def gc(self, yes: bool = False, confirm=None, out=print) -> list[str]
    def candidates(self) -> list[dict]
    def promote(self, pending_id: str, provenance: dict) -> dict
    def reject(self, pending_id: str, note: str | None, provenance: dict) -> dict

# cli.py
def scaffold_manifest(root: Path) -> str
def main(argv: list[str] | None = None, *, factory: Callable[[Path | None], ReasonHold] | None = None) -> int
```

Behavior that lives in the facade, not in the modules below it:
- Queries raise `IndexMissing` when the branch has no collection and `ModelMismatch` when the configured provider differs from the index's. They never index.
- `symbols` with an empty answer calls `absence_guard` with a freshness report, so an empty answer from a stale or missing index raises.
- `store_decision` indexes into the branch's collection only when the checkout is on the indexed branch (in single-collection mode a feature branch must not write into the default branch's collection). If Weaviate is unreachable it still appends, with a warning, provided embedding succeeded. After a successful, annotated write into a collection with no pending rebuild reasons, it stores the decision log's new `retraction_sha256` in the collection metadata so the next `reasonhold index` does not rebuild for a retraction already applied.
- `curate` uses the collection's `indexed_commit` as its base; without git or without an index it returns no edits and a warning.

CLI exit codes: `0` success; `1` for findings (`check` errors, `coverage` holes, a `freshness` that is not clean); `2` for `ReasonHoldError` or `ValueError`, printed as `reasonhold: <message>` on stderr. `preamble` always exits 0. `--json` prints the facade's dict as JSON.

- [ ] **Step 1: Write the failing tests**

`tests/test_api.py`:

```python
import pytest

from helpers import FakeClient, FakeProvider, MINIMAL_MANIFEST, git, make_repo, write
from reasonhold.api import ReasonHold
from reasonhold.errors import IndexMissing, IndexStale, ModelMismatch, StoreUnavailable

QUIET = lambda *a: None  # noqa: E731
HUMAN = {"kind": "human"}


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


def rh_for(root, client=None, provider=None):
    client = client or FakeClient()
    return ReasonHold(root, connect=lambda: client, provider=provider or FakeProvider()), client


def test_queries_never_index_and_name_the_fix(tmp_path):
    rh, client = rh_for(make_repo(tmp_path / "r"))
    with pytest.raises(IndexMissing, match="reasonhold index"):
        rh.search_docs("anything")
    assert client.created == []


def test_index_then_freshness_is_clean(tmp_path):
    rh, _ = rh_for(make_repo(tmp_path / "r"))
    assert rh.index(out=QUIET)["full"] is True
    fresh = rh.freshness()
    assert fresh["clean"] is True and fresh["index"]["fresh"] is True


def test_model_guard_applies_to_queries(tmp_path):
    root = make_repo(tmp_path / "r")
    rh, client = rh_for(root)
    rh.index(out=QUIET)
    other, _ = rh_for(root, client, FakeProvider(dims=8))
    with pytest.raises(ModelMismatch):
        other.search_docs("q")


def test_empty_symbol_answer_on_stale_index_is_refused(tmp_path, monkeypatch):
    root = make_repo(tmp_path / "r")
    rh, _ = rh_for(root)
    rh.index(out=QUIET)
    monkeypatch.setattr("reasonhold.codeindex.query_chunks", lambda *a, **k: [])
    assert rh.symbols("python_function")["results"] == []
    write(root, "AGENTS.md", "# changed\n")
    git(root, "commit", "-qam", "change")
    with pytest.raises(IndexStale):
        rh.symbols("python_function")


def test_store_decision_keeps_the_retraction_hash_in_step(tmp_path):
    rh, _ = rh_for(make_repo(tmp_path / "r"))
    rh.index(out=QUIET)
    out = rh.store_decision(topic="t", decision="d", rationale="r", provenance=HUMAN,
                            supersedes=[{"path": "docs/specs/worker.md", "retraction_summary": "no"}])
    assert out["indexed"] and rh.state().rebuild == []


def test_store_decision_with_weaviate_down_still_appends(tmp_path):
    root = make_repo(tmp_path / "r")

    def down():
        raise StoreUnavailable("cannot reach Weaviate at localhost:8081")

    rh = ReasonHold(root, connect=down, provider=FakeProvider())
    out = rh.store_decision(topic="t", decision="d", rationale="r", provenance=HUMAN)
    assert out["indexed"] is False and any("localhost:8081" in w for w in out["warnings"])
    assert (root / "decisions.jsonl").read_text().count("\n") == 1


def test_single_collection_feature_branch_does_not_write_to_the_default_index(tmp_path):
    root = make_repo(tmp_path / "r", MINIMAL_MANIFEST + "project:\n  index: {branch_isolation: false}\n")
    rh, client = rh_for(root)
    rh.index(out=QUIET)
    before = len(client.store["RH_R__main"].objects)
    git(root, "checkout", "-q", "-b", "feat")
    out = rh.store_decision(topic="t", decision="d", rationale="r", provenance=HUMAN)
    assert out["indexed"] is False and len(client.store["RH_R__main"].objects) == before


def test_curate_and_preamble_through_the_facade(tmp_path):
    root = make_repo(tmp_path / "r")
    rh, _ = rh_for(root)
    assert rh.curate()["edits"] == [] and rh.curate()["warnings"]
    rh.index(out=QUIET)
    git(root, "mv", "docs/specs/worker.md", "docs/specs/w2.md")
    assert [e["old_path"] for e in rh.curate(dry_run=True)["edits"]] == ["docs/specs/worker.md"]
    assert "fresh" in rh.preamble() or "stale" in rh.preamble()
```

`tests/test_cli.py`:

```python
import io
import json

import pytest

from helpers import FakeClient, FakeProvider, make_repo, write
from reasonhold.api import ReasonHold
from reasonhold.cli import main
from reasonhold.project import Project


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


@pytest.fixture
def cli(tmp_path, capsys):
    client = FakeClient()

    def factory(root):
        return ReasonHold(root, connect=lambda: client, provider=FakeProvider())

    def run(*argv):
        code = main(list(argv), factory=factory)
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return run


def test_init_scaffolds_a_loadable_manifest(tmp_path, cli):
    write(tmp_path, "README.md", "# R\n")
    write(tmp_path, "docs/specs/a.md", "# A\n")
    write(tmp_path, "pkg/x.py", "x = 1\n")
    code, out, _ = cli("--root", str(tmp_path), "init")
    assert code == 0 and (tmp_path / "reasonhold.yaml").exists()
    project = Project.load(tmp_path)
    assert [a.name for a in project.manifest.areas] == ["pkg"]
    assert (tmp_path / "decisions.jsonl").exists()
    assert cli("--root", str(tmp_path), "init")[0] == 2


def test_check_and_coverage_exit_codes(tmp_path, cli):
    root = make_repo(tmp_path / "r")
    assert cli("--root", str(root), "check")[0] == 0
    assert cli("--root", str(root), "coverage")[0] == 0
    write(root, "src/other/x.py", "x = 1\n")
    code, out, _ = cli("--root", str(root), "coverage")
    assert code == 1 and "src/other/x.py" in out


def test_errors_exit_2_with_the_fix_on_stderr(tmp_path, cli):
    root = make_repo(tmp_path / "r")
    code, _, err = cli("--root", str(root), "search", "anything")
    assert code == 2 and "reasonhold index" in err


def test_index_decide_show_and_govern(tmp_path, cli):
    root = make_repo(tmp_path / "r")
    assert cli("--root", str(root), "index")[0] == 0
    code, out, _ = cli("--root", str(root), "--json", "decide", "--topic", "queue", "--decision", "FIFO",
                       "--rationale", "r", "--supersede", "docs/specs/worker.md#Retries=no retries")
    record = json.loads(out)["record"]
    assert code == 0 and record["supersedes"][0]["path"] == "docs/specs/worker.md#Retries"
    code, out, _ = cli("--root", str(root), "--json", "decisions", "show", record["id"])
    assert json.loads(out)["status"] == "active"
    code, out, _ = cli("--root", str(root), "govern", "src/worker/main.py")
    assert code == 0 and "docs/specs/worker.md" in out and "no retries" in out


def test_decide_from_stdin(tmp_path, cli, monkeypatch):
    root = make_repo(tmp_path / "r")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"topic": "t", "decision": "d", "rationale": "r"})))
    code, out, _ = cli("--root", str(root), "--json", "decide", "--stdin")
    assert code == 0 and json.loads(out)["record"]["provenance"]["kind"] == "human"


def test_candidates_list_promote_reject(tmp_path, cli):
    from reasonhold.writes import propose_binding

    root = make_repo(tmp_path / "r")
    project = Project.load(root)
    a = propose_binding(project, target="worker-contract", reads=["AGENTS.md"], validates_against=["src/worker/"],
                        reason="r", provenance={"kind": "agent"})
    b = propose_binding(project, target="worker-contract", reads=["README.md"], validates_against=["src/worker/"],
                        reason="r", provenance={"kind": "agent"})
    code, out, _ = cli("--root", str(root), "candidates")
    assert code == 0 and a["id"] in out and b["id"] in out
    assert cli("--root", str(root), "candidates", "promote", a["id"])[0] == 0
    assert cli("--root", str(root), "candidates", "reject", b["id"], "--note", "no")[0] == 0
    assert cli("--root", str(root), "candidates", "promote", a["id"])[0] == 2


def test_preamble_always_exits_zero(tmp_path, cli):
    code, out, _ = cli("--root", str(tmp_path), "preamble", "--format", "claude-hook")
    assert code == 0 and json.loads(out)["hookSpecificOutput"]["hookEventName"] == "SessionStart"
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_api.py tests/test_cli.py -q`
Expected: collection errors, modules not found.

- [ ] **Step 3: Implement `api.py`**

```python
"""The single library surface. The CLI, the MCP server and the Agno toolkit wrap this class."""

from __future__ import annotations

from dataclasses import asdict

from reasonhold import codeindex, curation, governance, lifecycle, search, validation, writes
from reasonhold import preamble as preamble_mod
from reasonhold.authority import level_weights
from reasonhold.decisions import DecisionLog
from reasonhold.embedding import check_model, make_provider
from reasonhold.errors import IndexMissing, StoreUnavailable
from reasonhold.pending import PendingLog
from reasonhold.project import Project
from reasonhold.store import connect as store_connect
from reasonhold.store import read_meta, write_meta


class ReasonHold:
    def __init__(self, root=None, *, settings=None, connect=None, provider=None):
        self.project = Project.load(root)
        self._connect = connect or (lambda: store_connect(settings))
        self.provider = provider or make_provider(self.project.embedding)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = self._connect()
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def reload(self) -> None:
        self.project = Project.load(self.project.root)

    def state(self):
        return lifecycle.index_state(self.project, self.client)

    def _target(self):
        state = self.state()
        if not state.exists:
            raise IndexMissing(f"no index for branch {state.indexed_branch}: run `reasonhold index`")
        check_model(state.meta, self.provider)
        return self.client.collections.get(state.collection), state

    @staticmethod
    def _wrap(state, results, **extra) -> dict:
        return {"index": state.as_dict(), "results": results, **extra}

    # Belief
    def search_docs(self, query, top_k=5):
        col, state = self._target()
        weights = level_weights(self.project.ladder)
        return self._wrap(state, search.search_docs(col, self.provider, query, top_k, authority_weights=weights))

    def search_decisions(self, query, top_k=5, status="active"):
        col, state = self._target()
        return self._wrap(state, search.search_decisions(col, self.provider, query, top_k, status))

    def governing_docs(self, path):
        return governance.governing_docs(self.project, path)

    def retractions_for(self, path):
        return governance.retractions_for(self.project, path)

    def decision(self, id):
        return governance.decision(self.project, id)

    def conflicts(self, path=None, open_only=True):
        return governance.conflicts(self.project, path, open_only)

    # Exact
    def symbols(self, chunk_type, file_prefix=None, names_only=False):
        col, state = self._target()
        rows = codeindex.symbols(col, chunk_type, file_prefix, names_only)
        if not rows:
            codeindex.absence_guard(state, codeindex.freshness(self.project, col))
        return self._wrap(state, rows)

    def inventory(self):
        col, state = self._target()
        return self._wrap(state, codeindex.inventory(col))

    def freshness(self):
        col, state = self._target()
        report = codeindex.freshness(self.project, col)
        return {
            "index": state.as_dict(),
            "summary": report.summary(),
            "clean": report.is_clean and state.fresh,
            "stale": list(report.stale),
            "missing": list(report.missing),
            "orphaned": list(report.orphaned),
            "empty": list(report.empty),
        }

    def list_indexed_files(self):
        col, state = self._target()
        return self._wrap(state, codeindex.list_indexed_files(col))

    # Writes
    def store_decision(self, **kwargs):
        collection, state, warnings = None, None, []
        try:
            state = self.state()
            if state.exists and state.branch == state.indexed_branch:
                check_model(state.meta, self.provider)
                collection = self.client.collections.get(state.collection)
        except StoreUnavailable as exc:
            warnings.append(f"index not updated: {exc}")
        out = writes.store_decision(self.project, collection, self.provider, **kwargs)
        out["warnings"] = warnings + out["warnings"]
        if out["indexed"] and state is not None and state.meta is not None and not state.rebuild:
            meta = read_meta(self.client, state.collection)
            meta.retraction_sha256 = DecisionLog.load(self.project.decisions_path).retraction_sha256()
            write_meta(self.client, state.collection, meta)
        return out

    def propose_binding(self, **kwargs):
        return writes.propose_binding(self.project, **kwargs)

    def report_conflict(self, **kwargs):
        return writes.report_conflict(self.project, **kwargs)

    def resolve(self, **kwargs):
        return writes.resolve(self.project, **kwargs)

    # Governance
    def coverage(self):
        return governance.coverage(self.project)

    def check(self):
        return [asdict(p) for p in validation.check(self.project)]

    def curate(self, dry_run=True):
        try:
            state = self.state()
        except StoreUnavailable as exc:
            return {"edits": [], "warnings": [f"curation skipped: {exc}"]}
        since = state.meta.indexed_commit if state.meta else None
        if not since or state.head is None:
            return {"edits": [], "warnings": ["curation skipped: needs git and an existing index to compare against"]}
        edits = curation.curate(self.project, since=since, dry_run=dry_run)
        if edits and not dry_run:
            self.reload()
        return {"edits": [e.as_dict() for e in edits], "warnings": []}

    def preamble(self, max_lines=60, max_bytes=4096):
        return preamble_mod.render_preamble(
            self.project.root, max_lines=max_lines, max_bytes=max_bytes,
            index_probe=lambda p: preamble_mod.index_lines(p, connect=self._connect),
        )

    # Administration
    def index(self, full=False, dry_run=False, areas=None, out=print):
        report = lifecycle.run_index(self.project, self.client, self.provider, full=full, dry_run=dry_run,
                                     area_names=set(areas) if areas else None, out=out)
        self.reload()
        return report.as_dict()

    def gc(self, yes=False, confirm=None, out=print):
        return lifecycle.gc(self.project, self.client, yes=yes, confirm=confirm, out=out)

    def candidates(self):
        return PendingLog.load(self.project.pending_path).open("candidate_binding")

    def promote(self, pending_id, provenance):
        result = curation.promote(self.project, pending_id, provenance=provenance)
        self.reload()
        return result

    def reject(self, pending_id, note, provenance):
        return curation.reject(self.project, pending_id, note=note, provenance=provenance)
```

- [ ] **Step 4: Implement `cli.py`**

```python
"""`reasonhold`: the command-line wrapper over the ReasonHold facade."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from reasonhold.errors import ReasonHoldError
from reasonhold.governance import SOURCE_SUFFIXES
from reasonhold.indexer import EXCLUDED_PATH_PARTS
from reasonhold.project import MANIFEST_NAMES, slug

HUMAN = {"kind": "human"}


def scaffold_manifest(root: Path) -> str:
    project_id = slug(root.name)
    docs = sorted(p.relative_to(root).as_posix() for d in ("docs/architecture", "docs/specs")
                  for p in (root / d).rglob("*.md")) if (root / "docs").is_dir() else []
    guidance = [n for n in ("AGENTS.md", "CLAUDE.md", "README.md") if (root / n).is_file()]
    anchor = (docs or guidance or ["README.md"])[0]
    areas = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        if d.name.startswith(".") or d.name in EXCLUDED_PATH_PARTS or d.name in ("docs", "tests"):
            continue
        suffixes = sorted({f.suffix for f in d.rglob("*") if f.is_file() and f.suffix in SOURCE_SUFFIXES
                           and not any(part in EXCLUDED_PATH_PARTS for part in f.relative_to(root).parts)})
        if suffixes:
            globs = ", ".join(f'"{d.name}/**/*{s}"' for s in suffixes)
            areas.append(f"  {d.name}:\n    description: {d.name}\n    projects: [{d.name}]\n"
                         f"    docs: [{anchor}]\n    index: [{globs}]\n")
    if not areas:
        areas.append(f"  {project_id}:\n    description: {project_id}\n    projects: [{project_id}]\n"
                     f"    docs: [{anchor}]\n    index: [\"*.md\"]\n")
    global_docs = ", ".join(docs) if docs else ""
    index = ", ".join(guidance + (['"docs/**/*.md"'] if (root / "docs").is_dir() else []))
    return (
        "# Generated by `reasonhold init`. Placement is declared, never inferred:\n"
        "# review every list, then run `reasonhold check` and `reasonhold coverage`.\n"
        f"project:\n  id: {project_id}\n  decisions: decisions.jsonl\n"
        f"global:\n  docs: [{global_docs}]\n  index: [{index}]\n"
        "areas:\n" + "".join(areas)
    )


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="reasonhold", description="What a coding agent should believe about this repository.")
    p.add_argument("--root", type=Path, default=None, help="repository root (default: current directory)")
    p.add_argument("--json", action="store_true", help="print JSON")
    sub = p.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="scaffold reasonhold.yaml from the detected layout")
    init.add_argument("--force", action="store_true")
    sub.add_parser("check", help="validate the manifest, decision log and pending sidecar")
    idx = sub.add_parser("index", help="index this branch (incremental; full when the rules require it)")
    idx.add_argument("--full", action="store_true")
    idx.add_argument("--dry-run", action="store_true")
    idx.add_argument("--area", action="append", default=[])
    cur = sub.add_parser("curate", help="mechanical manifest curation from git renames and deletions")
    cur.add_argument("--dry-run", action="store_true")
    sub.add_parser("freshness")
    sub.add_parser("inventory")
    gc = sub.add_parser("gc", help="drop this project's collections for deleted branches")
    gc.add_argument("--yes", action="store_true")
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--top-k", type=int, default=5)
    g = sub.add_parser("govern", help="documents governing a path")
    g.add_argument("path")
    d = sub.add_parser("decisions")
    dsub = d.add_subparsers(dest="action", required=True)
    ds = dsub.add_parser("search")
    ds.add_argument("query")
    ds.add_argument("--top-k", type=int, default=5)
    ds.add_argument("--status", default="active", choices=["active", "superseded", "all"])
    dshow = dsub.add_parser("show")
    dshow.add_argument("id")
    dsub.add_parser("audit", help="decisions that read like retractions but record none")
    c = sub.add_parser("conflicts")
    c.add_argument("--path")
    c.add_argument("--all", action="store_true")
    sy = sub.add_parser("symbols")
    sy.add_argument("chunk_type")
    sy.add_argument("--prefix")
    sy.add_argument("--names", action="store_true")
    sub.add_parser("coverage")
    dec = sub.add_parser("decide", help="record a decision")
    dec.add_argument("--stdin", action="store_true", help="read the decision as a JSON object on stdin")
    dec.add_argument("--topic")
    dec.add_argument("--decision")
    dec.add_argument("--rationale")
    dec.add_argument("--alternative", action="append", default=[])
    dec.add_argument("--context", default="")
    dec.add_argument("--tag", action="append", default=[])
    dec.add_argument("--supersede", action="append", default=[], metavar="PATH[#SECTION]=SUMMARY")
    dec.add_argument("--supersedes-record", action="append", default=[], metavar="DEC_ID")
    dec.add_argument("--resolves", action="append", default=[], metavar="PEN_ID")
    dec.add_argument("--actor")
    cand = sub.add_parser("candidates")
    csub = cand.add_subparsers(dest="action")
    csub.add_parser("list")
    cp = csub.add_parser("promote")
    cp.add_argument("id")
    cr = csub.add_parser("reject")
    cr.add_argument("id")
    cr.add_argument("--note")
    pre = sub.add_parser("preamble")
    pre.add_argument("--format", choices=["text", "claude-hook"], default="text")
    sub.add_parser("mcp", help="run the stdio MCP server")
    return p


def _decide_kwargs(args) -> dict:
    if args.stdin:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("--stdin expects one JSON object")
        data.setdefault("provenance", dict(HUMAN))
        return data
    supersedes = []
    for item in args.supersede:
        path, sep, summary = item.partition("=")
        if not sep:
            raise ValueError(f"--supersede {item!r}: expected PATH[#SECTION]=SUMMARY")
        supersedes.append({"path": path, "retraction_summary": summary})
    provenance = dict(HUMAN, **({"actor": args.actor} if args.actor else {}))
    return {
        "topic": args.topic, "decision": args.decision, "rationale": args.rationale,
        "alternatives_considered": args.alternative, "session_context": args.context, "tags": args.tag,
        "supersedes": supersedes, "supersedes_records": args.supersedes_record,
        "resolves": args.resolves or None, "provenance": provenance,
    }


def _print(value, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True, default=str))
    elif isinstance(value, str):
        print(value, end="" if value.endswith("\n") else "\n")
    else:
        print(json.dumps(value, indent=2, sort_keys=True, default=str))


def main(argv=None, *, factory=None) -> int:
    args = _parser().parse_args(argv)
    root = (args.root or Path.cwd()).resolve()

    if args.command == "preamble":
        from reasonhold.preamble import claude_hook_json, render_preamble

        text = render_preamble(root)
        print(claude_hook_json(text) if args.format == "claude-hook" else text, end="" if args.format == "text" else "\n")
        return 0
    if args.command == "init":
        if any((root / n).exists() for n in MANIFEST_NAMES) and not args.force:
            print("reasonhold: a manifest already exists here (use --force to overwrite)", file=sys.stderr)
            return 2
        (root / "reasonhold.yaml").write_text(scaffold_manifest(root))
        (root / "decisions.jsonl").touch()
        print("wrote reasonhold.yaml and decisions.jsonl; review the manifest, then run `reasonhold check`")
        return 0
    if args.command == "mcp":
        from reasonhold.mcp_server import serve

        serve(root)
        return 0

    try:
        from reasonhold.api import ReasonHold

        rh = (factory or ReasonHold)(root)
        try:
            return _dispatch(rh, args)
        finally:
            rh.close()
    except (ReasonHoldError, ValueError) as exc:
        print(f"reasonhold: {exc}", file=sys.stderr)
        return 2


def _dispatch(rh, args) -> int:
    j = args.json
    cmd = args.command
    if cmd == "check":
        problems = rh.check()
        _print(problems if j else "\n".join(
            f"{p['severity']}: {p['file']}{':' + str(p['line']) if p['line'] else ''}: {p['message']}" for p in problems
        ) or "ok", j)
        return 1 if any(p["severity"] == "error" for p in problems) else 0
    if cmd == "index":
        _print(rh.index(full=args.full, dry_run=args.dry_run, areas=args.area), j)
        return 0
    if cmd == "curate":
        _print(rh.curate(dry_run=args.dry_run), j)
        return 0
    if cmd == "freshness":
        result = rh.freshness()
        _print(result if j else result["summary"], j)
        return 0 if result["clean"] else 1
    if cmd == "inventory":
        _print(rh.inventory(), j)
        return 0
    if cmd == "gc":
        _print(rh.gc(yes=args.yes), j)
        return 0
    if cmd == "search":
        _print(rh.search_docs(args.query, args.top_k), j)
        return 0
    if cmd == "govern":
        _print(rh.governing_docs(args.path), j)
        return 0
    if cmd == "decisions":
        if args.action == "search":
            _print(rh.search_decisions(args.query, args.top_k, args.status), j)
        elif args.action == "show":
            _print(rh.decision(args.id), j)
        else:
            from reasonhold.audit import find_candidates, render_report

            print(render_report(find_candidates(rh.project.decisions_path)))
        return 0
    if cmd == "conflicts":
        _print(rh.conflicts(args.path, open_only=not args.all), j)
        return 0
    if cmd == "symbols":
        _print(rh.symbols(args.chunk_type, args.prefix, args.names), j)
        return 0
    if cmd == "coverage":
        result = rh.coverage()
        _print(result, j)
        return 1 if result["holes"] else 0
    if cmd == "decide":
        _print(rh.store_decision(**_decide_kwargs(args)), j)
        return 0
    if cmd == "candidates":
        if args.action == "promote":
            _print(rh.promote(args.id, dict(HUMAN)), j)
        elif args.action == "reject":
            _print(rh.reject(args.id, args.note, dict(HUMAN)), j)
        else:
            rows = rh.candidates()
            _print(rows if j else "\n".join(
                f"{r['id']}  {r['target']} <- {', '.join(r['reads'])}  ({r['reason']})" for r in rows
            ) or "no open candidates", j)
        return 0
    raise ValueError(f"unknown command {cmd}")


if __name__ == "__main__":
    sys.exit(main())
```

`project.py`'s `_slug` (Task 3) becomes public: rename it to `slug` there and at its one call site.

- [ ] **Step 5: Run the tests and the suite**

Run: `.venv/bin/pytest -q`
Expected: all pass. Then smoke the console script: `.venv/bin/reasonhold --help` lists every command in the spec's CLI table plus `decisions audit`.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -q -m "ReasonHold facade and the reasonhold CLI"
```

---

### Task 14: The stdio MCP server, and the seed server's removal

**Files:**
- Create: `src/reasonhold/mcp_server.py`, `tests/test_mcp_server.py`
- Modify: `src/reasonhold/api.py` (agent tool set and agent provenance), `pyproject.toml` (drop `ollama` from `dev`)
- Delete: `src/reasonhold/server.py`, `src/reasonhold/config.py`

**Interfaces:**
- Consumes: `ReasonHold` (Task 13).
- Produces:

```python
# api.py (added)
AGENT_TOOLS = ("search_docs", "search_decisions", "store_decision", "list_indexed_files", "governing_docs",
               "retractions_for", "decision", "conflicts", "propose_binding", "report_conflict",
               "symbols", "freshness", "coverage")
def agent_provenance(provenance: dict | None, actor: str) -> dict
# kind defaults to "agent"; "sendesis_run" is allowed; "human" raises ValueError (an agent cannot sign as a human)

# mcp_server.py
def instructions(project) -> str
def build_server(rh) -> FastMCP            # registers exactly AGENT_TOOLS
def serve(root: Path | str | None = None) -> None   # stdio
```

`AGENT_TOOLS` is the spec's MCP list (section 7). Not exposed, by design: `promote` and `reject` (human only, so an agent cannot confirm its own proposal), `index`, `curate`, `gc` (administrative and slow). The Agno toolkit (Task 15) uses the same tuple. Server instructions are generated from the project id (R-18) and say what the tools are for, that retraction summaries are current truth, and that reading a file directly bypasses the retraction overlay.

- [ ] **Step 1: Write the failing tests**

`tests/test_mcp_server.py`:

```python
import asyncio
import json

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from helpers import FakeClient, FakeProvider, make_repo
from reasonhold.api import AGENT_TOOLS, ReasonHold
from reasonhold.mcp_server import build_server, instructions


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


@pytest.fixture
def server(tmp_path):
    client = FakeClient()
    rh = ReasonHold(make_repo(tmp_path / "r"), connect=lambda: client, provider=FakeProvider())
    return build_server(rh), rh


def run(coro):
    return asyncio.run(coro)


async def _names(server):
    async with Client(server) as c:
        return {t.name for t in await c.list_tools()}


async def _call(server, name, args):
    async with Client(server) as c:
        result = await c.call_tool(name, args)
    data = getattr(result, "data", None)
    return data if data is not None else json.loads(result.content[0].text)


def test_tool_set_matches_the_spec(server):
    names = run(_names(server[0]))
    assert names == set(AGENT_TOOLS)
    assert not names & {"promote", "reject", "index", "curate", "gc", "resolve"}


def test_instructions_name_the_project(server):
    text = instructions(server[1].project)
    assert "r" in text and "retraction" in text and "bypasses" in text


def test_governing_docs_over_mcp(server):
    out = run(_call(server[0], "governing_docs", {"path": "src/worker/main.py"}))
    assert [d["path"] for d in out["documents"]][-1] == "docs/specs/worker.md"


def test_store_decision_over_mcp_records_agent_provenance(server):
    srv, rh = server
    out = run(_call(srv, "store_decision", {"topic": "t", "decision": "d", "rationale": "r"}))
    assert out["record"]["provenance"] == {"kind": "agent", "actor": "mcp"}
    with pytest.raises(ToolError):
        run(_call(srv, "store_decision", {"topic": "t2", "decision": "d", "rationale": "r",
                                          "provenance": {"kind": "human"}}))
    assert rh.project.decisions_path.read_text().count("\n") == 1


def test_errors_reach_the_agent_with_the_fix(server):
    with pytest.raises(ToolError, match="reasonhold index"):
        run(_call(server[0], "search_docs", {"query": "anything"}))
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_mcp_server.py -q`
Expected: collection error, `No module named 'reasonhold.mcp_server'` (or `ImportError: AGENT_TOOLS`).

- [ ] **Step 3: Add the agent surface to `api.py`**

```python
AGENT_TOOLS = (
    "search_docs", "search_decisions", "store_decision", "list_indexed_files", "governing_docs",
    "retractions_for", "decision", "conflicts", "propose_binding", "report_conflict",
    "symbols", "freshness", "coverage",
)


def agent_provenance(provenance: dict | None, actor: str) -> dict:
    merged = {"kind": "agent", "actor": actor, **(provenance or {})}
    if merged["kind"] == "human":
        raise ValueError("an agent tool cannot record human provenance; humans use the reasonhold CLI")
    return merged
```

- [ ] **Step 4: Implement `mcp_server.py`**

```python
"""The stdio MCP server (R-20). It wraps the facade and exposes AGENT_TOOLS only."""

from __future__ import annotations

from fastmcp import FastMCP

from reasonhold.api import AGENT_TOOLS, ReasonHold, agent_provenance


def instructions(project) -> str:
    return (
        f"ReasonHold for project '{project.id}': what to believe about this repository. "
        "Before designing or changing code, call governing_docs(path) and search_decisions(query). "
        "A result's retraction_summary is current truth; the retracted document is stale where they disagree. "
        "Reading a file directly bypasses the retraction overlay, so check retractions_for(path) before trusting it. "
        "Record decisions with store_decision (use supersedes to retract a document, supersedes_records to retire a "
        "decision). Propose document bindings with propose_binding and report contradictions with report_conflict; "
        "a human promotes or resolves them. Exact questions (symbols, freshness, coverage) never use vector search "
        "and refuse to answer 'nothing' from a stale index."
    )


def build_server(rh) -> FastMCP:
    mcp = FastMCP(f"reasonhold-{rh.project.id}", instructions=instructions(rh.project))

    @mcp.tool
    def search_docs(query: str, top_k: int = 5) -> dict:
        """Semantic search over documents, code and decisions, reranked by authority. Hits carry retractions."""
        return rh.search_docs(query, top_k)

    @mcp.tool
    def search_decisions(query: str, top_k: int = 5, status: str = "active") -> dict:
        """Search decision records. status: "active" (default), "superseded" or "all"."""
        return rh.search_decisions(query, top_k, status)

    @mcp.tool
    def store_decision(
        topic: str,
        decision: str,
        rationale: str,
        alternatives_considered: list[str] | None = None,
        session_context: str = "",
        tags: list[str] | None = None,
        supersedes: list[dict] | None = None,
        supersedes_records: list[str] | None = None,
        resolves: list[str] | None = None,
        provenance: dict | None = None,
    ) -> dict:
        """Append a decision. supersedes: [{"path": "docs/x.md#Section", "retraction_summary": "what now holds"}]
        retracts documents (never src/ or tests/); supersedes_records retires earlier decision ids;
        resolves closes open conflict ids."""
        return rh.store_decision(
            topic=topic, decision=decision, rationale=rationale, alternatives_considered=alternatives_considered,
            session_context=session_context, tags=tags, supersedes=supersedes,
            supersedes_records=supersedes_records, resolves=resolves,
            provenance=agent_provenance(provenance, "mcp"),
        )

    @mcp.tool
    def list_indexed_files() -> dict:
        """Every indexed file with its chunk count and last indexed time."""
        return rh.list_indexed_files()

    @mcp.tool
    def governing_docs(path: str) -> dict:
        """Documents governing a path, by authority, with retractions, open conflicts and candidates. No vector search."""
        return rh.governing_docs(path)

    @mcp.tool
    def retractions_for(path: str) -> list[dict]:
        """Active retractions affecting a document or "document#section", following moved paths."""
        return rh.retractions_for(path)

    @mcp.tool
    def decision(id: str) -> dict:
        """One decision record with its computed status and what superseded it."""
        return rh.decision(id)

    @mcp.tool
    def conflicts(path: str | None = None, open_only: bool = True) -> list[dict]:
        """Reported conflicts between documents, optionally for one path."""
        return rh.conflicts(path, open_only)

    @mcp.tool
    def propose_binding(target: str, reads: list[str], validates_against: list[str], reason: str,
                        provenance: dict | None = None) -> dict:
        """Propose that documents (reads) govern code (validates_against) under a check or area. A human promotes it."""
        return rh.propose_binding(target=target, reads=reads, validates_against=validates_against, reason=reason,
                                  provenance=agent_provenance(provenance, "mcp"))

    @mcp.tool
    def report_conflict(doc_a: str, doc_b: str, paths: list[str], claim: str, evidence_a: str, evidence_b: str,
                        provenance: dict | None = None) -> dict:
        """Report two documents that disagree, with the disputed claim and a quote from each."""
        return rh.report_conflict(doc_a=doc_a, doc_b=doc_b, paths=paths, claim=claim, evidence_a=evidence_a,
                                  evidence_b=evidence_b, provenance=agent_provenance(provenance, "mcp"))

    @mcp.tool
    def symbols(chunk_type: str, file_prefix: str | None = None, names_only: bool = False) -> dict:
        """Exact, complete symbol listing (e.g. python_function, sql_function). Never vector search."""
        return rh.symbols(chunk_type, file_prefix, names_only)

    @mcp.tool
    def freshness() -> dict:
        """Whether the index matches the working tree and the branch history."""
        return rh.freshness()

    @mcp.tool
    def coverage() -> dict:
        """Source files no area covers, documents nothing places, and sources no check binds."""
        return rh.coverage()

    return mcp


def serve(root=None) -> None:
    rh = ReasonHold(root)
    try:
        build_server(rh).run()
    finally:
        rh.close()
```

- [ ] **Step 5: Remove the seed server and configuration**

```bash
git rm -q src/reasonhold/server.py src/reasonhold/config.py
grep -rn "reasonhold.config\|reasonhold.server\|import ollama" src tests && echo "STILL REFERENCED" || echo "clean"
```

Expected: `clean`. Then drop `"ollama>=0.4"` (and its comment) from the `dev` extra in `pyproject.toml`, and run `.venv/bin/pip uninstall -y ollama` so the suite proves nothing still needs it. Update the Global Constraints' dev-dependency line only if the plan is being edited anyway; the code is the authority here.

- [ ] **Step 6: Run the tests and the suite**

Run: `.venv/bin/pytest -q`
Expected: all pass with `ollama` uninstalled.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -q -m "stdio MCP server over the facade; remove the seed server, config and the ollama client"
```

---

### Task 15: The `reasonhold[agno]` extra

**Files:**
- Create: `src/reasonhold/agno.py`, `tests/test_agno.py`

**Interfaces:**
- Consumes: `ReasonHold`, `AGENT_TOOLS`, `agent_provenance` (Tasks 13 and 14); `preamble.render_preamble` (Task 12). Agno 3.0.11 APIs verified in `/mnt/ml_storage/dev/projects/agno`: `agno.tools.Toolkit(name=..., tools=[...])` with `get_functions()`; `agno.knowledge.protocol.KnowledgeProtocol` (`build_context`, `get_tools`, `aget_tools`, optional `retrieve`, `aretrieve`), `agno.knowledge.document.Document(content, name, meta_data)`; agent `pre_hooks` receive keyword arguments filtered by signature, including `run_input` (`RunInput.input_content`), and mutations to `run_input` reach the model.
- Produces:

```python
class ReasonHoldTools(Toolkit):                # exactly AGENT_TOOLS, each returning a JSON string
    def __init__(self, rh: ReasonHold | None = None, *, root=None, **kwargs)
class ReasonHoldKnowledge:                     # satisfies KnowledgeProtocol
    def __init__(self, rh: ReasonHold | None = None, *, root=None, top_k: int = 5)
    def build_context(self, **kwargs) -> str
    def get_tools(self, **kwargs) -> list[Callable]
    async def aget_tools(self, **kwargs) -> list[Callable]
    def search_docs(self, query: str) -> str
    def retrieve(self, query: str, **kwargs) -> list[Document]
    async def aretrieve(self, query: str, **kwargs) -> list[Document]
def render_context(rh: ReasonHold, paths: Sequence[str]) -> str     # preamble plus governing docs per path; fails open
def reasonhold_context(paths: Sequence[str], *, rh: ReasonHold | None = None, root=None) -> Callable
# returns a pre-hook `hook(run_input, **kwargs)` that prepends render_context(...) to a string input
```

- [ ] **Step 1: Install the extra**

```bash
.venv/bin/pip install -q -e '.[agno,dev]'
```

- [ ] **Step 2: Write the failing tests**

`tests/test_agno.py`:

```python
import json
from types import SimpleNamespace

import pytest

pytest.importorskip("agno")

from agno.knowledge.protocol import KnowledgeProtocol  # noqa: E402

from helpers import FakeClient, FakeProvider, make_repo  # noqa: E402
from reasonhold.agno import ReasonHoldKnowledge, ReasonHoldTools, reasonhold_context, render_context  # noqa: E402
from reasonhold.api import AGENT_TOOLS, ReasonHold  # noqa: E402


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


@pytest.fixture
def rh(tmp_path):
    client = FakeClient()
    return ReasonHold(make_repo(tmp_path / "r"), connect=lambda: client, provider=FakeProvider())


def test_toolkit_exposes_exactly_the_agent_tools(rh):
    tools = ReasonHoldTools(rh)
    assert set(tools.get_functions()) == set(AGENT_TOOLS)


def test_toolkit_store_decision_signs_as_an_agent(rh):
    out = json.loads(ReasonHoldTools(rh).store_decision(topic="t", decision="d", rationale="r"))
    assert out["record"]["provenance"] == {"kind": "agent", "actor": "agno"}


def test_toolkit_errors_are_returned_not_raised(rh):
    out = json.loads(ReasonHoldTools(rh).search_docs("anything"))
    assert "reasonhold index" in out["error"]


def test_knowledge_satisfies_the_protocol_and_carries_retractions(rh, monkeypatch):
    knowledge = ReasonHoldKnowledge(rh)
    assert isinstance(knowledge, KnowledgeProtocol)
    hits = [{"content": "c", "file_path": "docs/x.md", "authority_level": "architecture",
             "retraction_summary": "now LIFO", "kind": "document"}]
    monkeypatch.setattr(rh, "search_docs", lambda q, k: {"index": {}, "results": hits})
    (doc,) = knowledge.retrieve("queue")
    assert doc.name == "docs/x.md" and doc.meta_data["retraction_summary"] == "now LIFO"
    assert "retraction_summary" in knowledge.build_context()


def test_context_hook_prepends_preamble_and_governing_docs(rh):
    hook = reasonhold_context(["src/worker/main.py"], rh=rh)
    run_input = SimpleNamespace(input_content="Fix the retry bug.")
    hook(run_input=run_input, agent=None)
    assert run_input.input_content.endswith("Fix the retry bug.")
    assert "docs/specs/worker.md" in run_input.input_content


def test_render_context_fails_open(rh, monkeypatch):
    def boom(path):
        raise RuntimeError("no")

    monkeypatch.setattr(rh, "governing_docs", boom)
    assert "unavailable" in render_context(rh, ["src/worker/main.py"])
```

- [ ] **Step 3: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_agno.py -q`
Expected: `ModuleNotFoundError: No module named 'reasonhold.agno'`.

- [ ] **Step 4: Implement `agno.py`**

```python
"""Agno integration: a toolkit (the MCP tool set), a knowledge source over
search_docs, and a pre-run hook that injects the preamble and governing documents."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence

try:
    from agno.knowledge.document import Document
    from agno.tools import Toolkit
except ImportError as exc:  # pragma: no cover
    raise ImportError("reasonhold.agno needs the agno extra: pip install 'reasonhold[agno]'") from exc

from reasonhold.api import AGENT_TOOLS, ReasonHold, agent_provenance
from reasonhold.preamble import render_preamble

_META_FIELDS = ("file_path", "section_heading", "authority_level", "document_kind", "area", "kind",
                "record_id", "retraction_summary", "retraction_decision", "retraction_date", "rerank_score")


def _json(fn: Callable[[], object]) -> str:
    try:
        return json.dumps(fn(), default=str)
    except Exception as exc:  # a tool error is an answer the model can act on
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})


class ReasonHoldTools(Toolkit):
    def __init__(self, rh: ReasonHold | None = None, *, root=None, **kwargs):
        self.rh = rh or ReasonHold(root)
        super().__init__(name="reasonhold", tools=[getattr(self, name) for name in AGENT_TOOLS], **kwargs)

    def search_docs(self, query: str, top_k: int = 5) -> str:
        """Semantic search over documents, code and decisions, reranked by authority. Hits carry retractions."""
        return _json(lambda: self.rh.search_docs(query, top_k))

    def search_decisions(self, query: str, top_k: int = 5, status: str = "active") -> str:
        """Search decision records. status: active, superseded or all."""
        return _json(lambda: self.rh.search_decisions(query, top_k, status))

    def store_decision(self, topic: str, decision: str, rationale: str, alternatives_considered: list[str] | None = None,
                       session_context: str = "", tags: list[str] | None = None, supersedes: list[dict] | None = None,
                       supersedes_records: list[str] | None = None, resolves: list[str] | None = None,
                       provenance: dict | None = None) -> str:
        """Append a decision; supersedes retracts documents, supersedes_records retires decisions, resolves closes conflicts."""
        return _json(lambda: self.rh.store_decision(
            topic=topic, decision=decision, rationale=rationale, alternatives_considered=alternatives_considered,
            session_context=session_context, tags=tags, supersedes=supersedes,
            supersedes_records=supersedes_records, resolves=resolves, provenance=agent_provenance(provenance, "agno")))

    def list_indexed_files(self) -> str:
        """Every indexed file with chunk count and last indexed time."""
        return _json(self.rh.list_indexed_files)

    def governing_docs(self, path: str) -> str:
        """Documents governing a path, by authority, with retractions, conflicts and candidates."""
        return _json(lambda: self.rh.governing_docs(path))

    def retractions_for(self, path: str) -> str:
        """Active retractions affecting a document or document#section."""
        return _json(lambda: self.rh.retractions_for(path))

    def decision(self, id: str) -> str:
        """One decision record with computed status and what superseded it."""
        return _json(lambda: self.rh.decision(id))

    def conflicts(self, path: str | None = None, open_only: bool = True) -> str:
        """Reported conflicts between documents."""
        return _json(lambda: self.rh.conflicts(path, open_only))

    def propose_binding(self, target: str, reads: list[str], validates_against: list[str], reason: str,
                        provenance: dict | None = None) -> str:
        """Propose that documents govern code under a check or area. A human promotes it."""
        return _json(lambda: self.rh.propose_binding(target=target, reads=reads, validates_against=validates_against,
                                                     reason=reason, provenance=agent_provenance(provenance, "agno")))

    def report_conflict(self, doc_a: str, doc_b: str, paths: list[str], claim: str, evidence_a: str, evidence_b: str,
                        provenance: dict | None = None) -> str:
        """Report two documents that disagree, with the claim and a quote from each."""
        return _json(lambda: self.rh.report_conflict(doc_a=doc_a, doc_b=doc_b, paths=paths, claim=claim,
                                                     evidence_a=evidence_a, evidence_b=evidence_b,
                                                     provenance=agent_provenance(provenance, "agno")))

    def symbols(self, chunk_type: str, file_prefix: str | None = None, names_only: bool = False) -> str:
        """Exact, complete symbol listing. Never vector search."""
        return _json(lambda: self.rh.symbols(chunk_type, file_prefix, names_only))

    def freshness(self) -> str:
        """Whether the index matches the working tree and branch history."""
        return _json(self.rh.freshness)

    def coverage(self) -> str:
        """Sources no area covers, documents nothing places, sources no check binds."""
        return _json(self.rh.coverage)


class ReasonHoldKnowledge:
    def __init__(self, rh: ReasonHold | None = None, *, root=None, top_k: int = 5):
        self.rh = rh or ReasonHold(root)
        self.top_k = top_k

    def build_context(self, **kwargs) -> str:
        return (
            f"Project knowledge for '{self.rh.project.id}' comes from ReasonHold. Use search_docs to find it. "
            "A hit's retraction_summary is current truth; the document is stale where they disagree. "
            "Prefer higher authority_level documents when sources conflict."
        )

    def get_tools(self, **kwargs) -> list[Callable]:
        return [self.search_docs]

    async def aget_tools(self, **kwargs) -> list[Callable]:
        return self.get_tools()

    def search_docs(self, query: str) -> str:
        """Search this project's documents, code and decisions."""
        return _json(lambda: self.rh.search_docs(query, self.top_k))

    def retrieve(self, query: str, **kwargs) -> list[Document]:
        hits = self.rh.search_docs(query, kwargs.get("max_results") or self.top_k)["results"]
        return [
            Document(content=h.get("content", ""), name=h.get("file_path"),
                     meta_data={k: h[k] for k in _META_FIELDS if h.get(k) not in (None, "")})
            for h in hits
        ]

    async def aretrieve(self, query: str, **kwargs) -> list[Document]:
        return self.retrieve(query, **kwargs)


def render_context(rh: ReasonHold, paths: Sequence[str]) -> str:
    parts = [rh.preamble()]
    for path in paths:
        try:
            gov = rh.governing_docs(path)
            lines = [f"## Governing documents for `{gov['path']}`"]
            for d in gov["documents"]:
                lines.append(f"- `{d['path']}` ({d['authority_level']}, {d['binding']['kind']} {d['binding']['name']})")
                lines.extend(f"  - retracted: {r['retraction_summary']} ({r['topic']})" for r in d["retractions"])
            for hint in gov["overlap_hints"]:
                lines.append(f"- overlap: {', '.join(hint['documents'])} ({hint['level']})")
            parts.append("\n".join(lines) + "\n")
        except Exception as exc:
            parts.append(f"## Governing documents for `{path}`\n\nunavailable ({type(exc).__name__}: {exc})\n")
    return "\n".join(parts)


def reasonhold_context(paths: Sequence[str], *, rh: ReasonHold | None = None, root=None) -> Callable:
    holder = {"rh": rh}

    def hook(run_input, **kwargs) -> None:
        try:
            instance = holder["rh"] or ReasonHold(root)
            holder["rh"] = instance
            text = render_context(instance, paths)
        except Exception as exc:  # a pre-hook must never stop the run
            text = f"ReasonHold context unavailable ({type(exc).__name__}: {exc})."
        if isinstance(run_input.input_content, str):
            run_input.input_content = f"{text}\n\n{run_input.input_content}"

    return hook
```

- [ ] **Step 5: Run the tests and the suite**

Run: `.venv/bin/pytest -q`
Expected: all pass (the Agno tests run because the extra is installed in this venv; without it they skip).

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -q -m "reasonhold[agno]: toolkit, knowledge source and context pre-hook"
```

---

### Task 16: Skill pack, hook recipes and README

**Files:**
- Create: `src/reasonhold/resources/skills/{session-bootstrap,record-decision,consult-before-design,propose-and-report,reindex}/SKILL.md`
- Create: `src/reasonhold/resources/agents-snippet.md`, `src/reasonhold/resources/hooks/claude-settings.json`, `src/reasonhold/resources/hooks/post-merge`, `src/reasonhold/resources/mcp.json`
- Create: `README.md` (replace the repository's current one if present), `tests/test_resources.py`

**Interfaces:**
- Consumes: the CLI command names (Task 13) and the MCP tool names (Task 14).
- Produces: package data under `reasonhold/resources/`, shipped by the `package-data` entry from Task 1.

- [ ] **Step 1: Write the failing tests**

`tests/test_resources.py`:

```python
import json
import re
from importlib import resources
from pathlib import Path

import pytest

RES = resources.files("reasonhold").joinpath("resources")
SKILLS = ["session-bootstrap", "record-decision", "consult-before-design", "propose-and-report", "reindex"]
README = Path(__file__).resolve().parents[1] / "README.md"


@pytest.mark.parametrize("name", SKILLS)
def test_skill_has_frontmatter_and_stays_short(name):
    text = RES.joinpath(f"skills/{name}/SKILL.md").read_text()
    match = re.match(r"^---\nname: (.+)\ndescription: (.+)\n---\n", text)
    assert match and match.group(1) == name and len(match.group(2)) > 20
    assert len(text.splitlines()) <= 60


def test_only_the_proposal_skill_mentions_promotion_and_only_as_a_human_step():
    for name in SKILLS:
        text = RES.joinpath(f"skills/{name}/SKILL.md").read_text()
        if name == "propose-and-report":
            assert "Agents cannot promote" in text
        else:
            assert "promote" not in text


def test_claude_hook_recipe():
    data = json.loads(RES.joinpath("hooks/claude-settings.json").read_text())
    (entry,) = data["hooks"]["SessionStart"]
    (hook,) = entry["hooks"]
    assert hook["command"].startswith("reasonhold preamble --format claude-hook") and hook["timeout"] == 20
    assert "jq" not in hook["command"]


def test_post_merge_hook_runs_in_the_background_and_fails_open():
    text = RES.joinpath("hooks/post-merge").read_text()
    assert text.startswith("#!/bin/sh") and "reasonhold index" in text and "&" in text and text.rstrip().endswith("exit 0")


def test_mcp_entry():
    data = json.loads(RES.joinpath("mcp.json").read_text())
    assert data["mcpServers"]["reasonhold"] == {"command": "reasonhold", "args": ["mcp"]}


def test_readme_states_the_limits():
    text = README.read_text()
    assert "bypasses the retraction overlay" in text
    assert "unverified" in text  # Codex and other CLIs until verified (R-20)


def test_no_em_dashes_in_user_facing_text():
    texts = [README.read_text(), RES.joinpath("agents-snippet.md").read_text()]
    texts += [RES.joinpath(f"skills/{n}/SKILL.md").read_text() for n in SKILLS]
    assert all("\u2014" not in t for t in texts)
```

- [ ] **Step 2: Run and watch them fail**

Run: `.venv/bin/pytest tests/test_resources.py -q`
Expected: failures, files not found.

- [ ] **Step 3: Write the skills**

`resources/skills/session-bootstrap/SKILL.md`:

```markdown
---
name: session-bootstrap
description: Start every session from what this repository currently believes, and keep retractions straight while you work.
---

# Session bootstrap

1. Read the ReasonHold preamble at the top of the session (the SessionStart hook prints it; otherwise run `reasonhold preamble`).
2. If the preamble says the index is missing or stale, say so before relying on search results, and suggest `reasonhold index`.
3. Treat every "Superseded content" row as current truth. Where the retracted document disagrees with the summary, the document is stale.
4. Reading a file directly bypasses the retraction overlay. Before trusting a design document you opened yourself, call `retractions_for` on it.
5. Open conflicts and open candidates in the preamble are unresolved. Do not resolve them yourself; mention them when they touch your task.

## Retraction discipline

- Retract only documents that assert the thing that changed (architecture, specs, plans, guidance). Never retract `src/` or `tests/`: code is changed, not retracted.
- A retraction is not a delete. The document stays; the decision log says which part no longer holds.
- Retract the narrowest scope that is wrong: `docs/x.md#Section` rather than the whole file when only a section is stale.
```

`resources/skills/record-decision/SKILL.md`:

```markdown
---
name: record-decision
description: Record the decisions a design or change makes, at approval time, with the retractions they imply.
---

# Record a decision

Record a decision when a design is approved, a trade-off is settled, an approach is rejected with reasons, or work is deferred for a reason.

Use the `store_decision` tool (or `reasonhold decide` from a shell):

- `topic`: kebab-case, specific (`queue-ordering-lifo`), not a sentence.
- `decision`: one sentence stating what now holds.
- `rationale`: the evidence and the trade-off, including numbers when there are any.
- `alternatives_considered`: what was rejected, so it is not proposed again.
- `supersedes`: for each document this decision makes wrong, `{"path": "docs/...#Section", "retraction_summary": "what now holds"}`.
- `supersedes_records`: ids of earlier decisions this one replaces (find them with `search_decisions`).
- `resolves`: ids of open conflicts this decision settles.

Check first with `search_decisions` that the decision is new. If an earlier decision said the opposite, retire it with `supersedes_records` rather than leaving two active answers.

The log is append-only. Never edit `decisions.jsonl` by hand; a correction is a new decision.
```

`resources/skills/consult-before-design/SKILL.md`:

```markdown
---
name: consult-before-design
description: Before designing or changing a module, find the documents that govern it and the decisions already made about it.
---

# Consult before design

Before writing a design or changing behavior in a path:

1. `governing_docs(path)`: the documents that govern the path, highest authority first, with retractions, open conflicts and overlap hints.
2. `search_decisions(query)`: decisions about the topic. Superseded decisions are hidden by default; pass `status: "all"` to see history.
3. `search_docs(query)`: anything else relevant. Prefer higher `authority_level` hits, and treat any `retraction_summary` as current truth.

If two governing documents disagree, do not pick one silently: report it (see the propose-and-report skill) and say which one you followed and why.

If `governing_docs` returns nothing for a path you are about to change, the manifest does not place it yet. Say so, and propose a binding when you write the design.
```

`resources/skills/propose-and-report/SKILL.md`:

```markdown
---
name: propose-and-report
description: Propose which documents govern new code, and report contradictions between documents, without deciding either yourself.
---

# Propose and report

## Propose a binding

When you write a design for a module, or find a document that clearly governs code but is not placed in the manifest, call `propose_binding`:

- `target`: an existing check or area name, or a new check name.
- `reads`: the governing documents.
- `validates_against`: the code paths they govern (`src/module/`).
- `reason`: one sentence.

A human promotes or rejects it with `reasonhold candidates promote <id>` or `reasonhold candidates reject <id>`. Agents cannot promote; do not ask for a tool that would.

## Report a conflict

When two documents contradict each other about the same code, call `report_conflict` with both documents (and sections), the governed paths, the disputed claim in one sentence, and a short quote from each side as evidence.

Do not resolve it yourself. A decision resolves it later, recorded with `store_decision(..., resolves=[conflict id])`.
```

`resources/skills/reindex/SKILL.md`:

```markdown
---
name: reindex
description: When to run reasonhold index, what a full re-index means, and what to do when answers are stale.
---

# Re-index

- `reasonhold index` updates this branch's index incrementally. It switches to a full re-index by itself after a merge, a rebase or reset, a new retraction or retired decision, or a change to the manifest's authority ladder.
- `reasonhold index --full` drops and rebuilds this branch's collection. Use it after changing the embedding model (`ModelMismatch` says so) or when an index looks wrong.
- Queries never index. A stale answer carries a warning naming the cause; an exact "nothing found" from a stale index is refused (`IndexStale`). Run `reasonhold index`, then ask again.
- Each branch has its own collection. A new branch starts with a full index (about 90 seconds for a repository of Ariadne's size).
- `reasonhold gc` lists collections for branches that no longer exist and drops them after confirmation.
- `reasonhold index` also applies mechanical manifest curation (renames and deletions) first; review those edits with `git diff` before committing.
```

`resources/agents-snippet.md`:

```markdown
## ReasonHold

This repository uses ReasonHold to say which documents govern which code, which documents are retracted, and which decisions are active.

- At the start of a session, run `reasonhold preamble` and read it. Treat its "Superseded content" rows as current truth.
- Before designing or changing code, run `reasonhold govern <path>` and `reasonhold decisions search "<topic>"`.
- Reading a file directly bypasses the retraction overlay: check `reasonhold govern <path>` before trusting a design document.
- Record decisions with `reasonhold decide` (see `reasonhold decide --help`); never edit `decisions.jsonl` by hand.
- Do not promote candidates or resolve conflicts; those are human steps.

This snippet is unverified for CLIs other than Claude Code: it relies on the agent following AGENTS.md, not on a hook.
```

- [ ] **Step 4: Write the hook recipes and MCP entry**

`resources/hooks/claude-settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {"type": "command", "command": "reasonhold preamble --format claude-hook || true", "timeout": 20}
        ]
      }
    ]
  }
}
```

`resources/hooks/post-merge`:

```sh
#!/bin/sh
# ReasonHold: re-index after a merge. The full re-index rule applies, so a
# merge always rebuilds this branch's collection. Runs in the background and
# never blocks or fails the merge.
command -v reasonhold >/dev/null 2>&1 || exit 0
( reasonhold index >/dev/null 2>&1 & )
exit 0
```

`resources/mcp.json`:

```json
{"mcpServers": {"reasonhold": {"command": "reasonhold", "args": ["mcp"]}}}
```

- [ ] **Step 5: Write `README.md`**

```markdown
# ReasonHold

ReasonHold tells coding agents what to believe about a repository: which documents govern which code, which documents (or sections) a later decision has retracted, which decisions are active, and where documents conflict. It never generates text; it indexes, ranks and refuses.

## What it keeps

Three committed files, read the same way on every branch:

- `reasonhold.yaml` (or a legacy `sync-doc.yaml`): placement. Areas, checks binding documents to code, global documents, an optional authority ladder.
- `decisions.jsonl`: an append-only decision log. A decision can retract documents (`supersedes`) and retire earlier decisions (`supersedes_records`).
- `reasonhold.pending.jsonl`: an append-only sidecar of agents' proposed bindings, reported conflicts, their resolutions, and mechanical-curation history.

A Weaviate collection per (project, branch) is derived from them and can always be rebuilt.

## Install

    pip install reasonhold            # or: pip install 'reasonhold[agno]'

Requirements: Python 3.11+, a Weaviate instance (local on port 8081 by default, or Weaviate Cloud via `REASONHOLD_WEAVIATE_CLOUD_URL` and an API key in the variable named by `REASONHOLD_WEAVIATE_API_KEY_ENV`), and an embedding service (Ollama with `qwen3-embedding:0.6b` by default, or any OpenAI-compatible endpoint).

## Start

    reasonhold init        # scaffold reasonhold.yaml; review every list
    reasonhold check       # validate the manifest and both logs
    reasonhold index       # build this branch's index
    reasonhold coverage    # what the manifest fails to place (non-zero exit on holes)

## Use

| Need | Command | MCP tool |
|---|---|---|
| What governs this path | `reasonhold govern <path>` | `governing_docs` |
| Search documents and code | `reasonhold search "<query>"` | `search_docs` |
| Search decisions | `reasonhold decisions search "<query>"` | `search_decisions` |
| Record a decision | `reasonhold decide ...` | `store_decision` |
| Retractions for a document | `reasonhold govern <path>` | `retractions_for` |
| Exact symbols | `reasonhold symbols <chunk_type>` | `symbols` |
| Index freshness | `reasonhold freshness` | `freshness` |
| Open conflicts | `reasonhold conflicts` | `conflicts` |
| Promote or reject a proposal | `reasonhold candidates promote <id>`, `reasonhold candidates reject <id>` | none: human only |

Answers say which branch's index they came from and whether it is fresh. Queries never index; a stale index produces a warning, and an exact "nothing found" from a stale index is refused.

## Wire it into agents

- **MCP (stdio):** add `src/reasonhold/resources/mcp.json` to your client's MCP configuration (`reasonhold mcp`).
- **Claude Code session start:** merge `resources/hooks/claude-settings.json` into `.claude/settings.json`. The preamble fails open and fits in 60 lines and 4096 bytes.
- **Re-index after merges:** copy `resources/hooks/post-merge` to `.git/hooks/post-merge` and make it executable.
- **Skills:** copy `resources/skills/*` into `.claude/skills/`. For other CLIs, append `resources/agents-snippet.md` to `AGENTS.md`; that path is unverified until tested per CLI.
- **Agno:** `from reasonhold.agno import ReasonHoldTools, ReasonHoldKnowledge, reasonhold_context`.

Find the resources directory with `python -c "import reasonhold, pathlib; print(pathlib.Path(reasonhold.__file__).parent / 'resources')"`.

## Limits

- Reading a file directly bypasses the retraction overlay. The preamble, `governing_docs` and `retractions_for` are how an agent learns a document is stale.
- Codex and other CLIs are unverified: only Claude Code's SessionStart hook is tested.
- One embedding model per collection; changing it needs `reasonhold index --full`.
- Each branch has its own collection; a new branch starts with a full index.
```

The README's resource paths name the installed package's `resources` directory; keep the wording as above.

- [ ] **Step 6: Run the tests and the suite**

Run: `.venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -q -m "Skill pack, Claude Code and git hook recipes, MCP entry and README"
```

---

### Task 17: Integration tests and the retrieval benchmark

**Files:**
- Create: `tests/integration/conftest.py`, `tests/integration/test_live_index.py`, `tests/integration/test_live_mcp.py`, `tests/integration/test_retrieval_benchmark.py`

**Interfaces:**
- Consumes: `ReasonHold` (Task 13), `build_server` and the `reasonhold mcp` command (Tasks 13 and 14), the spike report's question table (`docs/reviews/2026-10-01-embedding-spike.md`, section "Questions and target ranks").
- Produces: tests marked `@pytest.mark.integration`, deselected by the default `addopts`, run on purpose with `.venv/bin/pytest -m integration`. They use only collections whose names start with `RH_Test` and always delete them.

- [ ] **Step 1: Write the integration fixtures**

`tests/integration/conftest.py`:

```python
import socket
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tests/helpers.py

from helpers import MINIMAL_MANIFEST, make_repo  # noqa: E402
from reasonhold.store import connect, drop_collection, list_collections  # noqa: E402

pytestmark = pytest.mark.integration


def _up(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session", autouse=True)
def services():
    missing = [name for name, port in (("Weaviate", 8081), ("Ollama", 11434)) if not _up("localhost", port)]
    if missing:
        pytest.skip(f"integration services not reachable: {', '.join(missing)}")


@pytest.fixture(autouse=True)
def cleanup(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    yield
    client = connect()
    try:
        for name in list_collections(client, "RH_Test"):
            drop_collection(client, name)
    finally:
        client.close()


@pytest.fixture
def live_repo(tmp_path):
    project_id = f"test-{uuid.uuid4().hex[:8]}"
    return make_repo(tmp_path / "repo", MINIMAL_MANIFEST + f"project:\n  id: {project_id}\n")
```

The `cleanup` fixture never touches a collection outside the `RH_Test` prefix.

- [ ] **Step 2: Write the live index tests**

`tests/integration/test_live_index.py`:

```python
import pytest

from helpers import FakeProvider, git, write
from reasonhold.api import ReasonHold
from reasonhold.errors import ModelMismatch

pytestmark = pytest.mark.integration
QUIET = lambda *a: None  # noqa: E731


def test_index_search_retract_and_guard(live_repo):
    with ReasonHold(live_repo) as rh:
        report = rh.index(out=QUIET)
        assert report["full"] and report["chunks"] > 0 and not report["warnings"]
        assert rh.state().collection.startswith("RH_Test_")
        hits = rh.search_docs("how many times does the worker retry")["results"]
        assert hits[0]["file_path"] == "docs/specs/worker.md"
        rh.store_decision(topic="no-retries", decision="The worker does not retry.", rationale="idempotency",
                          supersedes=[{"path": "docs/specs/worker.md#Retries", "retraction_summary": "no retries"}],
                          provenance={"kind": "human"})
        hits = rh.search_docs("how many times does the worker retry")["results"]
        assert any(h.get("retraction_summary") == "no retries" for h in hits)
        decisions = rh.search_decisions("worker retries")["results"]
        assert decisions[0]["status"] == "active" and decisions[0]["id"].startswith("dec-")
        assert rh.state().rebuild == []
    with ReasonHold(live_repo, provider=FakeProvider(dims=8)) as other:
        with pytest.raises(ModelMismatch):
            other.search_docs("anything")


def test_merge_triggers_full_reindex(live_repo):
    with ReasonHold(live_repo) as rh:
        rh.index(out=QUIET)
        git(live_repo, "checkout", "-q", "-b", "feat")
        write(live_repo, "docs/specs/extra.md", "# Extra\n")
        git(live_repo, "add", "-A"); git(live_repo, "commit", "-qm", "feat")
        git(live_repo, "checkout", "-q", "main")
        write(live_repo, "AGENTS.md", "# Agents v2\n")
        git(live_repo, "commit", "-qam", "main")
        git(live_repo, "merge", "-q", "--no-ff", "feat", "-m", "merge")
        report = rh.index(out=QUIET)
        assert report["full"] and any("merge" in r for r in report["reasons"])


def test_gc_drops_a_deleted_branch(live_repo):
    with ReasonHold(live_repo) as rh:
        rh.index(out=QUIET)
        git(live_repo, "checkout", "-q", "-b", "temp")
        rh.index(out=QUIET)
        temp = rh.state().collection
        git(live_repo, "checkout", "-q", "main")
        git(live_repo, "branch", "-q", "-D", "temp")
        assert rh.gc(yes=True, out=QUIET) == [temp]
        assert not rh.client.collections.exists(temp)
```

- [ ] **Step 3: Write the live MCP test**

`tests/integration/test_live_mcp.py`:

```python
import asyncio
import json
import sys
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from reasonhold.api import AGENT_TOOLS

pytestmark = pytest.mark.integration
REASONHOLD = str(Path(sys.executable).with_name("reasonhold"))


async def _session(root: Path):
    transport = StdioTransport(command=REASONHOLD, args=["--root", str(root), "mcp"])
    async with Client(transport) as c:
        names = {t.name for t in await c.list_tools()}
        result = await c.call_tool("governing_docs", {"path": "src/worker/main.py"})
    data = getattr(result, "data", None)
    return names, data if data is not None else json.loads(result.content[0].text)


def test_mcp_over_stdio(live_repo):
    names, governing = asyncio.run(_session(live_repo))
    assert names == set(AGENT_TOOLS)
    assert "docs/specs/worker.md" in [d["path"] for d in governing["documents"]]
```

- [ ] **Step 4: Write the retrieval benchmark**

`tests/integration/test_retrieval_benchmark.py`:

```python
"""The embedding spike's 40 questions as a benchmark (spec section 8). It informs; it does not gate."""

import re
import subprocess
from pathlib import Path

import pytest

from reasonhold.api import ReasonHold

pytestmark = pytest.mark.integration
SPIKE = Path(__file__).resolve().parents[2] / "docs/reviews/2026-10-01-embedding-spike.md"
ROW = re.compile(r"^\| (\d+) \| (.+?) \| `([^`]+)` \S+ \|")


def questions() -> list[tuple[str, str]]:
    rows = [ROW.match(line) for line in SPIKE.read_text().splitlines()]
    return [(m.group(2), m.group(3)) for m in rows if m]


def test_question_table_parses():
    assert len(questions()) == 40


def test_retrieval_benchmark(tmp_path, capsys):
    root = tmp_path / "test-ariadne"
    root.mkdir()
    archive = subprocess.run(["git", "-C", "/mnt/ml_storage/dev/projects/Ariadne", "archive", "8c5c451"],
                             check=True, capture_output=True, stdin=subprocess.DEVNULL).stdout
    subprocess.run(["tar", "-x", "-C", str(root)], input=archive, check=True)
    with ReasonHold(root) as rh:
        rh.index(out=lambda *a: None)
        ranks = []
        for question, target in questions():
            hits = rh.search_docs(question, top_k=10)["results"]
            paths = [h["file_path"] for h in hits]
            ranks.append(paths.index(target) + 1 if target in paths else None)
    hit5 = sum(1 for r in ranks if r and r <= 5) / len(ranks)
    mrr = sum(1 / r for r in ranks if r) / len(ranks)
    with capsys.disabled():
        print(f"\nretrieval benchmark: hit@5 {hit5:.1%}, MRR@10 {mrr:.2f} over {len(ranks)} questions "
              f"(spike, qwen3-embedding:0.6b: hit@5 75.0%, MRR 0.64)")
    assert len(ranks) == 40
```

The extracted Ariadne tree is not a git repository, so its collection uses branch `no-git`, and its project id is `test-ariadne`, which keeps the collection under the `RH_Test` prefix. The spike measured ranks over the top 10 with file-level targets as well, but through the seed's reranker and collection; differences of a few points are expected and are information, not failure.

- [ ] **Step 5: Run the integration tests**

Run: `.venv/bin/pytest -m integration -q -s`
Expected: all pass (about two minutes, most of it indexing Ariadne), the benchmark line printed, and afterwards `curl -s localhost:8081/v1/schema | python3 -c "import json,sys; print([c['class'] for c in json.load(sys.stdin)['classes'] if c['class'].startswith('RH_Test')])"` prints `[]`.

Then run the unit suite once more: `.venv/bin/pytest -q`. Expected: all pass, integration tests deselected.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -q -m "Integration tests (live index, merge rebuild, gc, MCP over stdio) and the 40-question retrieval benchmark"
```

---

## Exit criterion for this plan

On branch `m2-package`:

1. `.venv/bin/pytest -q` passes, with the seed's ported tests among them.
2. `.venv/bin/pytest -m integration -q -s` passes against the local Weaviate and Ollama, leaves no `RH_Test` collection behind, and prints the benchmark line.
3. `reasonhold --help` lists the spec's CLI commands; `reasonhold check` passes on this repository.
4. No module in `src/reasonhold/` imports `config`, `server`, `symbols`, `bootstrap`, `index` or `ollama`.

The executor stops there, reports the evidence, and opens a pull request only when the operator asks. Plan 2 (migrating Sendesis and Ariadne) starts after the operator merges.
