"""The code-index seam: exact queries and freshness; the only module that reads code chunks,
replaceable by a Serena adapter.

Ariadne indexes source as well as documentation, and the chunkers emit
structurally-typed chunks whose symbol names land in `section_heading`, a
filterable property. The index is therefore already a symbol table, and this
module is how a skill reads it.

Every query here is an exact property filter. That is a correctness
requirement, not a performance preference: an index-backed check reports a
defect when a symbol is ABSENT, so its recall must be total. Ranked
approximate retrieval offers no completeness guarantee — a wrapper whose chunk
scores below the cut would surface as a false "missing wrapper" finding.
Weaviate is used here as a symbol database, not as a search engine. Decision
`substrate-checks-use-property-filters`; enforced by
tests/test_symbols.py::TestQueryPathIsExact.

Freshness lives here too, because an index-backed check reading a stale index
reports on a snapshot — precisely the failure it exists to detect. Decision
`substrate-checks-use-property-filters` makes it a precondition of the audit
rather than a postscript to it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from reasonhold.errors import IndexMissing, IndexStale

CODE_FILE_TYPES = ("python", "csharp", "sql")

# Properties a check ever needs. Narrowing the projection keeps whole-corpus
# passes cheap; content is deliberately absent, since a symbol query wants
# names, and the skill reads the file itself when it needs the body.
QUERY_PROPERTIES = (
    "file_path",
    "chunk_type",
    "file_type",
    "area",
    "section_heading",
    "section_path",
    "type_name",
    "member_name",
    "member_kind",
)

# Page size for paginated exact fetches. The whole corpus is ~4.7k chunks, so
# this is one round trip in practice; the loop exists so completeness does not
# depend on that staying true.
PAGE_SIZE = 1000


@dataclass(frozen=True)
class FreshnessReport:
    """Three distinct ways an index can disagree with the working tree."""

    stale: tuple[str, ...]
    missing: tuple[str, ...]
    orphaned: tuple[str, ...]
    fresh: int
    # 0-byte corpus files. They chunk to nothing (index.py:294), so absence from
    # the index is correct and reindexing cannot change it. Reported so an empty
    # file the manifest claims as a document is still visible to the audit, but
    # excluded from the verdict so it never forces a no-op reindex.
    empty: tuple[str, ...] = ()

    @property
    def is_clean(self) -> bool:
        return not (self.stale or self.missing or self.orphaned)

    def summary(self) -> str:
        note = f", {len(self.empty)} empty" if self.empty else ""
        if self.is_clean:
            return f"FRESH: {self.fresh} files indexed and current{note}"
        parts = []
        if self.stale:
            parts.append(f"{len(self.stale)} stale")
        if self.missing:
            parts.append(f"{len(self.missing)} not indexed")
        if self.orphaned:
            parts.append(f"{len(self.orphaned)} orphaned")
        return f"STALE: {', '.join(parts)} ({self.fresh} current{note})"


def coerce_mtime(value: object) -> datetime | None:
    """Normalise a stored timestamp to an aware UTC datetime.

    Weaviate hands back a datetime on some client paths and an ISO string on
    others — index.py:501 already guards the string case. A naive value means a
    lossy round trip of something index.py wrote as aware UTC, so it is read
    back as UTC rather than rejected. Comparing naive against aware raises
    TypeError, which would crash an audit instead of reporting a wrong answer.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def compare_freshness(
    indexed: dict[str, object],
    working: dict[str, object],
    empty: Iterable[str] | None = None,
) -> FreshnessReport:
    """Compare indexed timestamps against working-tree mtimes.

    The fresh rule mirrors index.py's own incremental skip (`file_mtime <=
    stored_mtime`) so that this module and incremental indexing never disagree
    about whether a file needs reindexing. An indexed timestamp that will not
    parse is reported as not-indexed: reindexing one file is cheaper than
    trusting a timestamp we could not read.
    """
    unindexable = set(empty or ())
    stale: list[str] = []
    missing: list[str] = []
    fresh = 0

    for path, raw_working in working.items():
        stored = coerce_mtime(indexed.get(path)) if path in indexed else None
        if stored is None:
            if path not in unindexable:
                missing.append(path)
            continue
        current = coerce_mtime(raw_working)
        if current is not None and current > stored:
            stale.append(path)
        else:
            fresh += 1

    orphaned = [path for path in indexed if path not in working]

    return FreshnessReport(
        stale=tuple(sorted(stale)),
        missing=tuple(sorted(missing)),
        orphaned=tuple(sorted(orphaned)),
        fresh=fresh,
        empty=tuple(sorted(unindexable & set(working))),
    )


def select_by_prefix(rows: list[dict], prefixes: Sequence[str] | None) -> list[dict]:
    """Narrow rows to those whose file_path starts with one of `prefixes`.

    Applied in Python, after retrieval, so that the completeness of the query
    is a property of the filter alone and stays obvious. An empty result is a
    legitimate answer — "no symbols here" — not a failure.
    """
    if not prefixes:
        return rows
    return [row for row in rows if str(row.get("file_path", "")).startswith(tuple(prefixes))]


def symbol_names(rows: Iterable[dict]) -> list[str]:
    """Sorted, deduplicated symbol names from `section_heading`."""
    names = {str(row.get("section_heading") or "").strip() for row in rows}
    return sorted(name for name in names if name)


def build_filter(chunk_type: str | None = None, file_type: str | None = None, area: str | None = None):
    """Compose an exact-match filter. Returns None when nothing is constrained."""
    import weaviate.classes.query as wvq

    clauses = []
    if chunk_type:
        clauses.append(wvq.Filter.by_property("chunk_type").equal(chunk_type))
    if file_type:
        clauses.append(wvq.Filter.by_property("file_type").equal(file_type))
    if area:
        clauses.append(wvq.Filter.by_property("area").equal(area))

    if not clauses:
        return None
    combined = clauses[0]
    for clause in clauses[1:]:
        combined = combined & clause
    return combined


def query_chunks(
    collection,
    chunk_type: str | None = None,
    file_type: str | None = None,
    area: str | None = None,
) -> list[dict]:
    """Every chunk matching the filter, paginated to exhaustion."""
    filters = build_filter(chunk_type=chunk_type, file_type=file_type, area=area)
    rows: list[dict] = []
    offset = 0
    while True:
        page = collection.query.fetch_objects(
            filters=filters,
            limit=PAGE_SIZE,
            offset=offset,
            include_vector=False,
            return_properties=list(QUERY_PROPERTIES),
        )
        batch = [dict(obj.properties) for obj in page.objects]
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def chunk_type_inventory(collection) -> dict[str, int]:
    """Tally chunk_type across the whole corpus — the symbol table's shape."""
    counts: dict[str, int] = {}
    for obj in collection.iterator(include_vector=False, return_properties=["chunk_type"]):
        key = str(obj.properties.get("chunk_type") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


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
