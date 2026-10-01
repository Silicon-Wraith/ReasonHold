"""Ranked retrieval over the index: the reranker and the two search entry points."""

from __future__ import annotations

import re

import weaviate.classes.query as wvq

from reasonhold.authority import DEFAULT_LADDER, level_weights
from reasonhold.codeindex import is_code

# Reranking is intentionally lightweight and additive. The base vector score
# remains primary, while these adjustments correct common systematic errors:
# authoritative specs should beat manifests for conceptual queries, source code
# should beat tests for exact symbols, and decision records should surface for
# rationale/history questions.
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


DECISION_STATUSES = ("active", "superseded", "all")


def _rerank_docs(query: str, results: list[dict], authority_weights: dict[str, float] | None = None) -> list[dict]:
    weights = level_weights(DEFAULT_LADDER) if authority_weights is None else authority_weights
    query_intents = _detect_query_intents(query)
    for result in results:
        result["rerank_score"] = round(_rerank_score(query, query_intents, result, weights), 4)
    results.sort(key=lambda item: item["rerank_score"], reverse=True)
    return results


def _rerank_score(query: str, query_intents: dict[str, float], result: dict, authority_weights: dict[str, float]) -> float:
    score = float(result.get("score", 0.0))
    authority = str(result.get("authority_level", ""))
    document_kind = str(result.get("document_kind", ""))
    chunk_type = str(result.get("chunk_type", ""))
    file_path = str(result.get("file_path", ""))
    section_heading = str(result.get("section_heading", ""))
    type_name = str(result.get("type_name", ""))
    member_name = str(result.get("member_name", ""))

    score += authority_weights.get(authority, 0.0)
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


def _kind(props: dict) -> str:
    if props.get("chunk_type") == "decision":
        return "decision"
    if props.get("chunk_type") == "pending":
        return "pending"
    return "code" if is_code(props) else "document"


def search_docs(collection, provider, query: str, top_k: int = 5, *, authority_weights: dict[str, float]) -> list[dict]:
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


def search_decisions(collection, provider, query: str, top_k: int = 5, status: str = "active") -> list[dict]:
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
