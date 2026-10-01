"""The stdio MCP server (R-20). It wraps the facade and exposes AGENT_TOOLS only,
or QUERY_TOOLS only when read-only."""

from __future__ import annotations

from fastmcp import FastMCP

from reasonhold.api import AGENT_TOOLS, ReasonHold, agent_provenance


def instructions(project, read_only: bool = False) -> str:
    if read_only:
        return (
            f"ReasonHold for project '{project.id}', read-only: what to believe about that repository. "
            "Use governing_docs(path) and search_decisions(query) to learn its documents and decisions. "
            "A result's retraction_summary is current truth; the retracted document is stale where they disagree. "
            "Reading a file directly bypasses the retraction overlay, so check retractions_for(path) before trusting it. "
            "This knowledge base cannot be written from here: record decisions, proposals and conflicts only in "
            "the project you are working in. Exact questions (symbols, freshness, coverage) never use vector search "
            "and refuse to answer 'nothing' from a stale index."
        )
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


def build_server(rh, read_only: bool = False) -> FastMCP:
    mcp = FastMCP(f"reasonhold-{rh.project.id}", instructions=instructions(rh.project, read_only))
    # Write tools are defined unconditionally and registered only when the server may write.
    write_tool = (lambda fn: fn) if read_only else mcp.tool

    @mcp.tool
    def search_docs(query: str, top_k: int = 5) -> dict:
        """Semantic search over documents, code and decisions, reranked by authority. Hits carry retractions."""
        return rh.search_docs(query, top_k)

    @mcp.tool
    def search_decisions(query: str, top_k: int = 5, status: str = "active") -> dict:
        """Search decision records. status: "active" (default), "superseded" or "all"."""
        return rh.search_decisions(query, top_k, status)

    @write_tool
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
        datetime: str | None = None,
    ) -> dict:
        """Append a decision. supersedes: [{"path": "docs/x.md#Section", "retraction_summary": "what now holds"}]
        retracts documents (never src/ or tests/); supersedes_records retires earlier decision ids;
        resolves closes open conflict ids.
        datetime (optional ISO timestamp) makes a retry idempotent: the same topic and datetime records once."""
        return rh.store_decision(
            topic=topic, decision=decision, rationale=rationale, alternatives_considered=alternatives_considered,
            session_context=session_context, tags=tags, supersedes=supersedes,
            supersedes_records=supersedes_records, resolves=resolves,
            provenance=agent_provenance(provenance, "mcp"), datetime_=datetime,
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

    @write_tool
    def propose_binding(target: str, reads: list[str], validates_against: list[str], reason: str,
                        provenance: dict | None = None) -> dict:
        """Propose that documents (reads) govern code (validates_against) under a check or area. A human promotes it."""
        return rh.propose_binding(target=target, reads=reads, validates_against=validates_against, reason=reason,
                                  provenance=agent_provenance(provenance, "mcp"))

    @write_tool
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


def serve(root=None, read_only: bool = False) -> None:
    rh = ReasonHold(root)
    try:
        build_server(rh, read_only).run()
    finally:
        rh.close()
