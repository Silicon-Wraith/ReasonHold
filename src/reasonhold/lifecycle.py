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
        if meta.last_full_index is None:
            rebuild.append("no completed full index (a previous build failed or was interrupted)")
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
    # A new or recreated collection starts with blank hashes and no commit, so an interrupted
    # build is never reported fresh. The real meta is written only after the loop completes.
    blank = CollectionMeta(
        project=project.id,
        branch=state.indexed_branch,
        model_id=provider.model_id,
        dims=provider.dims,
        manifest_sha256="",
        authority_sha256="",
        retraction_sha256="",
        indexed_commit=None,
        last_full_index=None,
    )
    with index_lock(state.collection):
        ensure_collection(client, state.collection, blank, recreate=full)
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
    if not branches:
        return []  # git failed or timed out: never treat every branch as deleted
    here = current_branch(project.root)
    if not here.startswith("detached-") and here != "no-git" and here not in branches:
        return []
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
        try:
            answer = (confirm or input)(f"Drop {len(candidates)} collection(s)? [y/N] ")
        except EOFError:
            answer = "n"
        if answer.strip().lower() not in ("y", "yes"):
            out("nothing dropped")
            return []
    for name in candidates:
        drop_collection(client, name)
    return candidates
