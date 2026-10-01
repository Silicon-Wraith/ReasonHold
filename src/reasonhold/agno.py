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
                       provenance: dict | None = None, datetime: str | None = None) -> str:
        """Append a decision; supersedes retracts documents, supersedes_records retires decisions, resolves closes
        conflicts. datetime (optional ISO timestamp) makes a retry idempotent: the same topic and datetime records once."""
        return _json(lambda: self.rh.store_decision(
            topic=topic, decision=decision, rationale=rationale, alternatives_considered=alternatives_considered,
            session_context=session_context, tags=tags, supersedes=supersedes,
            supersedes_records=supersedes_records, resolves=resolves, provenance=agent_provenance(provenance, "agno"),
            datetime_=datetime))

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
        try:
            hits = self.rh.search_docs(query, kwargs.get("max_results") or self.top_k)["results"]
        except Exception as exc:  # fail open: an unavailable index must not stop the agent run
            return [Document(content=f"ReasonHold search is unavailable ({type(exc).__name__}: {exc})",
                             meta_data={"error": True})]
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
