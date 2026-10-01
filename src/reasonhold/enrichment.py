"""Deterministic enrichment and embedding-text rendering for docs-rag."""

from __future__ import annotations

from pathlib import PurePosixPath

from reasonhold.manifest import Manifest


def enrich_chunk(chunk: dict[str, object], manifest: Manifest) -> dict[str, object]:
    """Add normalized metadata used for retrieval and embedding."""
    enriched = dict(chunk)
    file_path = str(enriched["file_path"])

    enriched.setdefault("file_type", _file_type(file_path))
    enriched.setdefault("area", manifest.infer_area(file_path))
    enriched.setdefault("project", manifest.infer_project(file_path))

    authority_level, document_kind = _classify_authority(file_path)
    enriched.setdefault("authority_level", authority_level)
    enriched.setdefault("document_kind", document_kind)

    return enriched


def render_embedding_text(chunk: dict[str, object]) -> str:
    """Render normalized context and raw body as the embedding payload."""
    headers: list[str] = []
    _append_header(headers, "Document kind", chunk.get("document_kind"))
    _append_header(headers, "Authority", chunk.get("authority_level"))
    _append_header(headers, "Area", chunk.get("area"))
    _append_header(headers, "Project", chunk.get("project"))
    _append_header(headers, "File", chunk.get("file_path"))
    _append_header(headers, "Section path", chunk.get("section_path"))
    _append_header(headers, "Semantic label", chunk.get("semantic_label"))
    _append_header(headers, "Namespace", chunk.get("namespace"))
    _append_header(headers, "Type", chunk.get("type_name"))
    _append_header(headers, "Member", chunk.get("member_name"))
    _append_header(headers, "Member kind", chunk.get("member_kind"))
    _append_header(headers, "Decision topic", chunk.get("decision_topic"))
    _append_header(headers, "Decision status", chunk.get("decision_status"))
    return "\n".join(headers + ["", str(chunk["content"])])


# Files at the repo root that carry the container architecture rather than
# merely configuring a tool. Matched exactly; prefixes are handled below.
_DEPLOYMENT_ROOT_FILES = {"justfile", "compose.infra.yml", "compose.app.yml", "compose.dev.yml"}

# Directories holding tooling that operates ON the project rather than being
# the product. Kept distinct from src/ so retrieval can tell them apart.
_TOOLING_PREFIXES = ("docs-rag/", "devtools/", "scripts/", "benchmarks/")


def _classify_authority(file_path: str) -> tuple[str, str]:
    """Map a repo-relative path to (authority_level, document_kind).

    The ladder mirrors the documentation precedence in AGENTS.md:
    architecture > specs > plans > src. Reviews and bug investigations are
    records of what happened, not authority over what should happen, so they
    rank as "review" rather than sitting on the design ladder at all.

    Order matters — the most specific prefix must be tested first. A path that
    reaches the generic fallback contributes no ranking signal, so a governed
    directory arriving there is a bug in this function, not a neutral result.
    """
    if file_path == "docs-rag/decisions.jsonl":
        return "decision", "decision_log"
    if file_path == "sync-doc.yaml":
        return "project-manifest", "sync_doc_manifest"
    if file_path in {"AGENTS.md", "CLAUDE.md"}:
        return "project-guidance", "project_guidance"

    # Documentation ladder — see the artifact taxonomy in AGENTS.md.
    if file_path.startswith("docs/architecture/"):
        return "architecture", "architecture_doc"
    if file_path.startswith("docs/specs/"):
        return "implementation-spec", "implementation_spec"
    if file_path.startswith("docs/plans/"):
        return "implementation-plan", "implementation_plan"
    if file_path.startswith("docs/reviews/"):
        return "review", "review_finding"
    if file_path.startswith("docs/bugs/"):
        return "review", "bug_investigation"
    if file_path.startswith("docs/"):
        # docs/ root holds operational guides — setup, runbooks, standards.
        return "reference", "operational_guide"

    # Deployment substrate: the container rearchitecture lives in these files
    # as much as it does in its design doc.
    if file_path in _DEPLOYMENT_ROOT_FILES:
        return "deployment", "deployment_config"
    if file_path.startswith("Dockerfile") or file_path.startswith("compose."):
        return "deployment", "deployment_config"

    if file_path.startswith(".claude/skills/"):
        return "tooling", "skill_definition"
    if file_path.startswith(_TOOLING_PREFIXES):
        return "tooling", "tooling_code"

    if file_path.startswith("src/"):
        return "implementation", "source_code"
    if file_path.startswith("ui/src/"):
        return "implementation", "frontend_code"
    if file_path.startswith("tests/"):
        return "test", "test_code"
    if file_path.endswith(".py"):
        return "tooling", "tooling_code"
    return "reference", "reference"


def _file_type(file_path: str) -> str:
    if file_path == "docs-rag/decisions.jsonl":
        return "decisions"
    suffix = PurePosixPath(file_path).suffix.lower()
    return {
        ".md": "markdown",
        ".cs": "csharp",
        ".py": "python",
        ".sql": "sql",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".jsonl": "jsonl",
    }.get(suffix, "text")


def _append_header(headers: list[str], label: str, value: object) -> None:
    if value is None or value == "":
        return
    headers.append(f"{label}: {value}")
