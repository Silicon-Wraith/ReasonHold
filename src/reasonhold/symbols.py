#!/usr/bin/env python3
"""Exact symbol queries over the docs-rag index, for /sync-docs check procedures.

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

Usage:
    python docs-rag/symbols.py --freshness
    python docs-rag/symbols.py --chunk-type sql_function --names
    python docs-rag/symbols.py --chunk-type sql_function \
        --file-prefix src/database/postgres/triggers/ --names
    python docs-rag/symbols.py --chunk-type python_function \
        --file-prefix src/database/ --json
    python docs-rag/symbols.py --inventory

Exit codes: 0 clean, 1 the index is stale (--freshness only), 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from reasonhold.manifest import load_manifest

from reasonhold.config import COLLECTION_NAME, PROJECT_ROOT, SYNC_DOC_PATH

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
            return f"FRESH — {self.fresh} files indexed and current{note}"
        parts = []
        if self.stale:
            parts.append(f"{len(self.stale)} stale")
        if self.missing:
            parts.append(f"{len(self.missing)} not indexed")
        if self.orphaned:
            parts.append(f"{len(self.orphaned)} orphaned")
        return f"STALE — {', '.join(parts)} ({self.fresh} current{note})"


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


def scan_working_tree() -> tuple[dict[str, datetime], set[str]]:
    """Corpus mtimes and the set of 0-byte paths, from one pass over the tree.

    index.py is imported lazily: it pulls in Ollama, Weaviate, and the
    chunkers, none of which the pure helpers above need to be testable.
    """
    from reasonhold.index import gather_files

    mtimes: dict[str, datetime] = {}
    empty: set[str] = set()
    for _file_type, path in gather_files(load_manifest(SYNC_DOC_PATH)):
        rel = str(path.relative_to(PROJECT_ROOT))
        stat = path.stat()
        mtimes[rel] = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        if stat.st_size == 0:
            empty.add(rel)
    return mtimes, empty


def indexed_mtimes(collection) -> dict[str, object]:
    from reasonhold.index import get_indexed_mtimes

    return get_indexed_mtimes(collection)


def _open_collection():
    from reasonhold.store import connect as get_client

    client = get_client()
    return client, client.collections.get(COLLECTION_NAME)


def _emit(rows: list[dict], as_names: bool, as_json: bool, count_only: bool) -> None:
    if count_only:
        print(len(rows))
    elif as_json:
        print(json.dumps(rows, indent=2, sort_keys=True))
    elif as_names:
        for name in symbol_names(rows):
            print(name)
    else:
        for row in rows:
            print(f"{row.get('file_path', '')}\t{row.get('section_heading', '')}")


def _run_freshness(collection) -> int:
    working, empty = scan_working_tree()
    report = compare_freshness(indexed_mtimes(collection), working, empty=empty)
    print(report.summary())
    for label, paths in (
        ("stale", report.stale),
        ("not indexed", report.missing),
        ("orphaned", report.orphaned),
        ("empty (cannot be indexed)", report.empty),
    ):
        for path in paths:
            print(f"  {label}: {path}")
    return 0 if report.is_clean else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Exact symbol queries over the docs-rag index (no ranked retrieval).",
    )
    parser.add_argument("--chunk-type", help="Exact chunk_type, e.g. sql_function, python_function")
    parser.add_argument("--file-type", help="Exact file_type, e.g. python, sql, markdown")
    parser.add_argument("--area", help="Exact sync-doc.yaml area attribution")
    parser.add_argument(
        "--file-prefix",
        action="append",
        default=[],
        help="Keep only rows whose file_path starts with this prefix (repeatable)",
    )
    parser.add_argument("--names", action="store_true", help="Print symbol names only")
    parser.add_argument("--json", action="store_true", help="Print full rows as JSON")
    parser.add_argument("--count", action="store_true", help="Print the row count only")
    parser.add_argument("--inventory", action="store_true", help="Tally chunk_type across the corpus")
    parser.add_argument("--freshness", action="store_true", help="Compare the index against the working tree")
    args = parser.parse_args()

    modes = [args.freshness, args.inventory]
    if all(modes):
        parser.error("--freshness and --inventory are separate modes")
    if not any(modes) and not any([args.chunk_type, args.file_type, args.area, args.file_prefix]):
        parser.error("give a filter (--chunk-type/--file-type/--area/--file-prefix), --inventory, or --freshness")
    client, collection = _open_collection()
    try:
        if args.freshness:
            return _run_freshness(collection)
        if args.inventory:
            for chunk_type, count in chunk_type_inventory(collection).items():
                print(f"{count:>6}  {chunk_type}")
            return 0

        rows = query_chunks(
            collection,
            chunk_type=args.chunk_type,
            file_type=args.file_type,
            area=args.area,
        )
        _emit(select_by_prefix(rows, args.file_prefix), args.names, args.json, args.count)
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
