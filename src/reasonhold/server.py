#!/usr/bin/env python3
"""FastMCP server for Claude Code docs RAG.

Exposes tools for searching project documentation, source code, and
decision records. Backed by a Weaviate-Docs instance with pre-embedded
content.

Tools:
    search_docs      — Semantic search across all indexed content
    list_indexed_files — Show index status for debugging
    store_decision   — Record a structured decision with rationale
    search_decisions — Search past decisions with optional status filter

Registered in .claude/mcp.json — Claude Code starts this automatically.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

import ollama as ollama_client
import weaviate
import weaviate.classes.query as wvq
from fastmcp import FastMCP

from reasonhold.config import (
    COLLECTION_NAME,
    DECISIONS_FILE,
    EMBEDDING_MODEL,
    OLLAMA_HOST,
    OLLAMA_PORT,
    WEAVIATE_GRPC_PORT,
    WEAVIATE_HOST,
    WEAVIATE_PORT,
)

mcp = FastMCP(
    "docs-rag",
    instructions="Semantic search over Ariadne project documentation, design specs, plans, decisions, and source code.",
)


def _get_client() -> weaviate.WeaviateClient:
    return weaviate.connect_to_custom(
        http_host=WEAVIATE_HOST,
        http_port=WEAVIATE_PORT,
        http_secure=False,
        grpc_host=WEAVIATE_HOST,
        grpc_port=WEAVIATE_GRPC_PORT,
        grpc_secure=False,
    )


def apply_retraction_to_chunks(
    client: weaviate.WeaviateClient,
    path: str,
    retraction_summary: str,
    retraction_decision: str,
    retraction_date: str,
) -> int:
    """Update retraction_* properties on existing chunks matching `path`.

    If `path` contains '#', the suffix is treated as a section anchor; only
    chunks whose section_heading contains the anchor text (case-insensitive)
    are updated. Otherwise every chunk with file_path == path is updated.

    Decision chunks (chunk_type == "decision") are never annotated — a
    decision does not retract itself.

    Returns the number of chunks updated.

    Performance: iteration is full-collection for portability across Weaviate
    client versions. Switch to a server-side filtered query via
    weaviate.classes.query.Filter when collection size makes this measurable.
    """
    collection = client.collections.get(COLLECTION_NAME)

    if "#" in path:
        file_path, _, anchor = path.partition("#")
        anchor_lower = anchor.strip().lower()
    else:
        file_path = path
        anchor_lower = None

    updated = 0
    for obj in collection.iterator(include_vector=False):
        props = obj.properties or {}
        if props.get("file_path") != file_path:
            continue
        if props.get("chunk_type") == "decision":
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


_ollama = ollama_client.Client(host=f"http://{OLLAMA_HOST}:{OLLAMA_PORT}")

# Reranking is intentionally lightweight and additive. The base vector score
# remains primary, while these adjustments correct common systematic errors:
# authoritative specs should beat manifests for conceptual queries, source code
# should beat tests for exact symbols, and decision records should surface for
# rationale/history questions.
AUTHORITY_WEIGHTS = {
    # Ordered by the documentation precedence in AGENTS.md: architecture
    # governs specs, specs govern plans, plans describe how src was built.
    "architecture": 0.08,
    "implementation-spec": 0.06,
    "implementation-plan": 0.05,
    "design": 0.04,
    "project-guidance": 0.03,
    "deployment": 0.02,
    "implementation": 0.0,
    "decision": 0.0,
    "review": 0.0,
    "reference": -0.02,
    "tooling": -0.04,
    "project-manifest": -0.06,
    "test": -0.05,
}

DOCUMENT_KIND_WEIGHTS = {
    "sync_doc_manifest": -0.04,
    "architecture_doc": 0.03,
    "simulator_design_doc": 0.03,
    "implementation_spec": 0.03,
    "decision_log": 0.0,
    "source_code": 0.0,
    "test_code": 0.0,
}

QUERY_INTENT_PATTERNS = {
    "decision": [
        r"\bdecision\b",
        r"\bwhy did\b",
        r"\bwhy do\b",
        r"\bchosen\b",
        r"\bchoice\b",
        r"\brationale\b",
        r"\bsuperseded\b",
        r"\btradeoff\b",
        r"\btrade-off\b",
    ],
    "conceptual": [
        r"\bordering\b",
        r"\blifecycle\b",
        r"\barchitecture\b",
        r"\bdesign\b",
        r"\bspec\b",
        r"\bscope\b",
        r"\bpurpose\b",
        r"\bmust-do\b",
        r"\bmust not\b",
        r"\bcriteria\b",
        r"\bbehavior\b",
    ],
    "symbol": [
        r"\b[A-Z][A-Za-z0-9_]+\b",
        r"\binterface\b",
        r"\bclass\b",
        r"\bmethod\b",
        r"\bproperty\b",
        r"\bexception\b",
        r"\bdecorator\b",
        r"\bpolicy\b",
    ],
}

DECISION_INTENT_WEIGHTS = {
    "decision_log": 0.14,
}

CONCEPTUAL_INTENT_WEIGHTS = {
    "markdown_section": 0.05,
    "authoritative_docs": 0.04,
    "implementation_docs_penalty": -0.03,
}

SYMBOL_INTENT_WEIGHTS = {
    "csharp_chunk": 0.05,
    "test_code_penalty": -0.02,
    "decision_log_penalty": -0.03,
    "implementation_bonus": 0.01,
}

EXACT_MATCH_WEIGHTS = {
    "type_name": 0.10,
    "member_name": 0.08,
    "section_heading_contains": 0.03,
    "file_path_contains": 0.02,
}


def _embed_query(query: str) -> list[float]:
    response = _ollama.embed(model=EMBEDDING_MODEL, input=[query])
    return response["embeddings"][0]


def _detect_query_intents(query: str) -> dict[str, float]:
    normalized = query.strip().lower()
    intents = {"decision": 0.0, "conceptual": 0.0, "symbol": 0.0}
    for intent, patterns in QUERY_INTENT_PATTERNS.items():
        for pattern in patterns:
            haystack = query if intent == "symbol" and "[A-Z]" in pattern else normalized
            if re.search(pattern, haystack):
                intents[intent] = 1.0
                break
    return intents


def _rerank_docs(query: str, results: list[dict]) -> list[dict]:
    query_intents = _detect_query_intents(query)
    for result in results:
        result["rerank_score"] = round(_rerank_score(query, query_intents, result), 4)
    results.sort(key=lambda item: item["rerank_score"], reverse=True)
    return results


def _rerank_score(query: str, query_intents: dict[str, float], result: dict) -> float:
    score = float(result.get("score", 0.0))
    authority = str(result.get("authority_level", ""))
    document_kind = str(result.get("document_kind", ""))
    chunk_type = str(result.get("chunk_type", ""))
    file_path = str(result.get("file_path", ""))
    section_heading = str(result.get("section_heading", ""))
    type_name = str(result.get("type_name", ""))
    member_name = str(result.get("member_name", ""))

    score += AUTHORITY_WEIGHTS.get(authority, 0.0)
    score += DOCUMENT_KIND_WEIGHTS.get(document_kind, 0.0)

    if query_intents.get("decision") and document_kind == "decision_log":
        score += DECISION_INTENT_WEIGHTS["decision_log"]

    if query_intents.get("conceptual"):
        if chunk_type == "markdown_section":
            score += CONCEPTUAL_INTENT_WEIGHTS["markdown_section"]
        if document_kind in {"architecture_doc", "simulator_design_doc", "implementation_spec"}:
            score += CONCEPTUAL_INTENT_WEIGHTS["authoritative_docs"]
        if document_kind in {"source_code", "test_code", "sync_doc_manifest"}:
            score += CONCEPTUAL_INTENT_WEIGHTS["implementation_docs_penalty"]

    if query_intents.get("symbol"):
        if chunk_type.startswith("csharp"):
            score += SYMBOL_INTENT_WEIGHTS["csharp_chunk"]
        if document_kind == "test_code":
            score += SYMBOL_INTENT_WEIGHTS["test_code_penalty"]
        if document_kind == "decision_log":
            score += SYMBOL_INTENT_WEIGHTS["decision_log_penalty"]
        if authority == "implementation":
            score += SYMBOL_INTENT_WEIGHTS["implementation_bonus"]

    exact_query = query.strip()
    lowered_query = exact_query.lower()
    if type_name and type_name.lower() == lowered_query:
        score += EXACT_MATCH_WEIGHTS["type_name"]
    if member_name and member_name.lower() == lowered_query:
        score += EXACT_MATCH_WEIGHTS["member_name"]
    if section_heading and lowered_query in section_heading.lower():
        score += EXACT_MATCH_WEIGHTS["section_heading_contains"]
    if lowered_query in file_path.lower():
        score += EXACT_MATCH_WEIGHTS["file_path_contains"]

    return score


def _format_decision_content(record: dict) -> str:
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
        f"Status: {record.get('status', 'active')}",
    ]
    if supersedes:
        lines.append("Supersedes:")
        for entry in supersedes:
            lines.append(f"  - {entry.get('path', '')}: {entry.get('retraction_summary', '')}")
    return "\n".join(lines)


def _validate_supersedes(supersedes: list[dict] | None) -> list[dict]:
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


@mcp.tool()
def store_decision(
    topic: str,
    decision: str,
    rationale: str,
    alternatives_considered: list[str] | None = None,
    session_context: str = "",
    tags: list[str] | None = None,
    status: str = "active",
    supersedes: list[dict] | None = None,
) -> dict:
    """Store a structured decision record for future retrieval.

    Records significant decisions, their rationale, and alternatives
    considered. Writes to persistent JSONL storage and indexes into
    the vector store for immediate semantic search.

    Call this when:
    - A benchmark comparison leads to a technology choice
    - An architectural trade-off is resolved
    - Work is deferred with specific reasoning
    - An approach is rejected with rationale

    Args:
        topic: Kebab-case identifier (e.g., "spacy-model-selection").
        decision: One-sentence summary of what was decided.
        rationale: The reasoning — benchmarks, trade-offs, constraints.
        alternatives_considered: What else was evaluated (prevents re-proposing).
        session_context: Brief description of what the session was doing.
        tags: Free-form tags for filtering.
        status: "active" (default) or "superseded".
        supersedes: Optional list of retractions. Each entry is a dict with
            required keys "path" (repo-relative path, optionally with "#section"
            anchor) and "retraction_summary" (one-line correction stating what
            now holds). Only use when this decision retracts or replaces prior
            design documentation.

    Returns:
        The stored decision record with datetime.
    """
    supersedes_list = _validate_supersedes(supersedes)

    record = {
        "topic": topic,
        "decision": decision,
        "rationale": rationale,
        "alternatives_considered": alternatives_considered or [],
        "datetime": datetime.now(UTC).isoformat(),
        "session_context": session_context,
        "tags": tags or [],
        "status": status,
        "supersedes": supersedes_list,
    }

    # Append to JSONL file
    with open(DECISIONS_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")

    # Embed and upsert to Weaviate
    content = _format_decision_content(record)
    vector = _embed_query(content)

    client = _get_client()
    try:
        collection = client.collections.get(COLLECTION_NAME)
        uuid = weaviate.util.generate_uuid5(f"{record['topic']}|{record['datetime']}")
        collection.data.insert(
            properties={
                "content": content,
                "file_path": "docs-rag/decisions.jsonl",
                "chunk_type": "decision",
                "file_type": "decisions",
                "authority_level": "decision",
                "document_kind": "decision_log",
                "section_heading": record["topic"],
                "section_path": record["topic"],
                "semantic_label": "decision_record",
                "decision_topic": record["topic"],
                "decision_status": record["status"],
                "chunk_index": 0,
                "last_modified": record["datetime"],
            },
            vector=vector,
            uuid=uuid,
        )
        if record["status"] == "active":
            for entry in record["supersedes"]:
                apply_retraction_to_chunks(
                    client=client,
                    path=entry["path"],
                    retraction_summary=entry["retraction_summary"],
                    retraction_decision=record["topic"],
                    retraction_date=record["datetime"],
                )
    finally:
        client.close()

    return record


@mcp.tool()
def search_decisions(
    query: str,
    top_k: int = 5,
    status: str | None = None,
) -> list[dict]:
    """Search past decision records.

    Filtered semantic search over decision records only. Returns
    structured results with all decision fields.

    Use this to find past reasoning:
    - "Why did we choose spaCy lg over trf?"
    - "What decisions about GPU allocation?"
    - "Deferred work items"

    Args:
        query: Natural language search query.
        top_k: Number of results to return (default 5).
        status: Filter by status ("active" or "superseded"). None returns all.

    Returns:
        Ranked list of decision records with similarity score.
    """
    vector = _embed_query(query)

    # Build filters: always filter to decisions, optionally filter status
    type_filter = wvq.Filter.by_property("chunk_type").equal("decision")
    if status:
        combined_filter = type_filter & wvq.Filter.by_property("content").contains_any([f"Status: {status}"])
    else:
        combined_filter = type_filter

    client = _get_client()
    try:
        collection = client.collections.get(COLLECTION_NAME)
        results = collection.query.near_vector(
            near_vector=vector,
            filters=combined_filter,
            limit=top_k,
            return_metadata=wvq.MetadataQuery(distance=True),
        )

        output = []
        for obj in results.objects:
            score = 1.0 - (obj.metadata.distance or 0.0)
            content = obj.properties.get("content", "")

            # Parse structured fields back from content
            parsed = {}
            for line in content.split("\n"):
                if ": " in line:
                    key, _, value = line.partition(": ")
                    parsed[key.lower()] = value

            output.append(
                {
                    "score": round(score, 4),
                    "topic": obj.properties.get("section_heading", ""),
                    "decision": parsed.get("decision", ""),
                    "rationale": parsed.get("rationale", ""),
                    "alternatives": parsed.get("alternatives considered", ""),
                    "context": parsed.get("context", ""),
                    "date": parsed.get("date", ""),
                    "status": parsed.get("status", "active"),
                }
            )

        return output
    finally:
        client.close()


@mcp.tool()
def search_docs(query: str, top_k: int = 5) -> list[dict]:
    """Search project documentation and source code.

    Performs semantic search over indexed project files including
    design docs, implementation specs, plans, C# source code, tests,
    decisions, and project guidance files.

    Args:
        query: Natural language search query.
        top_k: Number of results to return (default 5).

    Returns:
        Ranked list of matching chunks with score, file_path, chunk_type,
        section_heading, and content.
    """
    vector = _embed_query(query)

    client = _get_client()
    try:
        collection = client.collections.get(COLLECTION_NAME)
        results = collection.query.near_vector(
            near_vector=vector,
            limit=top_k,
            return_metadata=wvq.MetadataQuery(distance=True),
        )

        output = []
        for obj in results.objects:
            score = 1.0 - (obj.metadata.distance or 0.0)
            result = {
                "score": round(score, 4),
                "file_path": obj.properties.get("file_path", ""),
                "chunk_type": obj.properties.get("chunk_type", ""),
                "authority_level": obj.properties.get("authority_level", ""),
                "document_kind": obj.properties.get("document_kind", ""),
                "area": obj.properties.get("area", ""),
                "section_heading": obj.properties.get("section_heading", ""),
                "type_name": obj.properties.get("type_name", ""),
                "member_name": obj.properties.get("member_name", ""),
                "content": obj.properties.get("content", ""),
            }
            retraction_summary = obj.properties.get("retraction_summary")
            if retraction_summary:
                result["retraction_summary"] = retraction_summary
                result["retraction_decision"] = obj.properties.get("retraction_decision", "")
                result["retraction_date"] = obj.properties.get("retraction_date", "")
            output.append(result)

        return _rerank_docs(query, output)
    finally:
        client.close()


@mcp.tool()
def list_indexed_files() -> list[dict]:
    """List all files currently in the docs RAG index.

    Returns file paths, chunk counts, and last indexed timestamps.
    Useful for verifying the index is current.
    """
    client = _get_client()
    try:
        collection = client.collections.get(COLLECTION_NAME)

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
    finally:
        client.close()


if __name__ == "__main__":
    mcp.run()
