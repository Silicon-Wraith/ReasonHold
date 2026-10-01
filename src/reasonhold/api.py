"""The single library surface. The CLI, the MCP server and the Agno toolkit wrap this class."""

from __future__ import annotations

from dataclasses import asdict

from reasonhold import codeindex, curation, governance, lifecycle, search, validation, writes
from reasonhold import preamble as preamble_mod
from reasonhold.authority import level_weights
from reasonhold.decisions import DecisionLog
from reasonhold.embedding import check_model, make_provider
from reasonhold.errors import IndexMissing, ModelMismatch, StoreUnavailable
from reasonhold.pending import PendingLog
from reasonhold.project import Project
from reasonhold.store import connect as store_connect
from reasonhold.store import read_meta, write_meta


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
        except ModelMismatch as exc:
            collection = None
            warnings.append(f"index not updated: {exc}; run `reasonhold index --full`")
        out = writes.store_decision(self.project, collection, self.provider, **kwargs)
        out["warnings"] = warnings + out["warnings"]
        if out["indexed"] and state is not None and state.meta is not None and not state.rebuild:
            try:
                meta = read_meta(self.client, state.collection)
                meta.retraction_sha256 = DecisionLog.load(self.project.decisions_path).retraction_sha256()
                write_meta(self.client, state.collection, meta)
            except Exception as exc:  # the decision is already recorded
                out["warnings"].append(f"index metadata not refreshed: {exc}")
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
