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

from reasonhold.decisions import format_decision_content as _format_decision_content
from reasonhold.decisions import validate_supersedes as _validate_supersedes
from reasonhold.authority import DEFAULT_LADDER, level_weights
from reasonhold.search import _detect_query_intents, _rerank_docs  # noqa: F401
from reasonhold.writes import apply_retraction_to_chunks
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


_ollama = ollama_client.Client(host=f"http://{OLLAMA_HOST}:{OLLAMA_PORT}")

AUTHORITY_WEIGHTS = level_weights(DEFAULT_LADDER)

def _embed_query(query: str) -> list[float]:
    response = _ollama.embed(model=EMBEDDING_MODEL, input=[query])
    return response["embeddings"][0]


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
                    collection,
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

        return _rerank_docs(query, output, AUTHORITY_WEIGHTS)
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
