"""Deterministic enrichment and embedding-text rendering for docs-rag."""

from __future__ import annotations

from pathlib import PurePosixPath

from reasonhold.authority import DEFAULT_LADDER, classify
from reasonhold.manifest import Manifest


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


def file_type_for(file_path: str, decisions_rel: str | None) -> str:
    if decisions_rel and file_path == decisions_rel:
        return "decisions"
    suffix = PurePosixPath(file_path).suffix.lower()
    return {
        ".md": "markdown", ".cs": "csharp", ".py": "python", ".sql": "sql",
        ".yaml": "yaml", ".yml": "yaml", ".jsonl": "jsonl",
    }.get(suffix, "text")



def _append_header(headers: list[str], label: str, value: object) -> None:
    if value is None or value == "":
        return
    headers.append(f"{label}: {value}")
