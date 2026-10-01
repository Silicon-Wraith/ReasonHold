"""Index project docs and source code into Weaviate."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import weaviate
import weaviate.classes.data as wvd
import weaviate.classes.query as wvq

from reasonhold.chunkers import CHUNKER_MAP
from reasonhold.enrichment import enrich_chunk, render_embedding_text
from reasonhold.overlay import retraction_for_chunk

EXCLUDED_PATH_PARTS = frozenset(
    {".git", ".venv", "__pycache__", ".pytest_cache", "site-packages", "node_modules", ".ruff_cache", "htmlcov", ".worktrees"}
)


def is_excluded_path(path: Path, root: Path) -> bool:
    return any(part in EXCLUDED_PATH_PARTS for part in path.relative_to(root).parts)


def gather_files(
    root: Path,
    globs: Sequence[str],
    *,
    decisions_path: Path | None = None,
    pending_path: Path | None = None,
) -> list[tuple[str, Path]]:
    """Resolve corpus globs into unique (file_type, path) pairs. A literal entry
    naming a missing file yields nothing; `reasonhold check` reports it."""
    files: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for pattern in globs:
        for path in sorted(root.glob(pattern)):
            if path.is_file() and not is_excluded_path(path, root) and path not in seen:
                seen.add(path)
                files.append((detect_file_type(path, decisions_path=decisions_path, pending_path=pending_path), path))
    return files


# Suffixes that are never text. Labelling one of these "markdown" would be
# wrong metadata, not a harmless default — file_type is a filterable property.
_BINARY_SUFFIXES = frozenset(
    {
        ".pdf",
        ".zip",
        ".gz",
        ".tar",
        ".xz",
        ".7z",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".ico",
        ".webp",
        ".svgz",
        ".mp3",
        ".mp4",
        ".wav",
        ".avi",
        ".mov",
        ".docx",
        ".xlsx",
        ".pptx",
        ".doc",
        ".xls",
        ".ppt",
        ".bin",
        ".so",
        ".dylib",
        ".dll",
        ".exe",
        ".o",
        ".a",
        ".pyc",
        ".pyd",
        ".whl",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".eot",
        ".db",
        ".sqlite",
        ".parquet",
        ".onnx",
        ".safetensors",
        ".pt",
        ".pth",
    }
)

# Fraction of decoded characters that may be U+FFFD before a file is judged
# binary rather than lossy text. A PDF read as UTF-8 sits near 0.50; text with
# a handful of bad bytes stays well under 0.15.
_MAX_REPLACEMENT_RATIO = 0.30
_REPLACEMENT_CHAR = "\ufffd"

# Enough to catch a header without reading a large file into memory twice.
_BINARY_SNIFF_BYTES = 8192


def detect_file_type(path: Path, *, decisions_path: Path | None = None, pending_path: Path | None = None) -> str:
    """Map a path to a chunker key.

    Extensionless files (Dockerfile, justfile) legitimately fall through to the
    markdown chunker — they are text. Known-binary suffixes must not: see
    _BINARY_SUFFIXES.
    """
    if decisions_path is not None and path == decisions_path:
        return "decisions"
    if pending_path is not None and path == pending_path:
        return "pending"
    suffix = path.suffix.lower()
    if suffix in _BINARY_SUFFIXES:
        return "binary"
    return {
        ".md": "markdown",
        ".cs": "csharp",
        ".py": "python",
        ".sql": "sql",
        ".yaml": "yaml",
        ".yml": "yaml",
    }.get(suffix, "markdown")


def is_binary_file(path: Path) -> bool:
    """Return True when the file's bytes are not text.

    index_file() reads with errors="replace", which turns any binary input into
    non-empty replacement-character noise that chunks and embeds exactly like a
    real document. Nothing downstream can tell the difference, so the check has
    to happen here rather than being delegated to whoever writes the globs.
    """
    if path.suffix.lower() in _BINARY_SUFFIXES:
        return True
    try:
        head = path.read_bytes()[:_BINARY_SNIFF_BYTES]
    except OSError:
        return False
    if not head:
        return False
    if b"\x00" in head:
        return True
    decoded = head.decode("utf-8", errors="replace")
    return decoded.count(_REPLACEMENT_CHAR) / len(decoded) > _MAX_REPLACEMENT_RATIO


def get_indexed_mtimes(collection) -> dict[str, datetime]:
    """Fetch file_path -> max last_modified from Weaviate for incremental checks."""
    mtimes: dict[str, datetime] = {}
    for obj in collection.iterator(include_vector=False):
        file_path = obj.properties.get("file_path", "")
        last_modified = obj.properties.get("last_modified")
        if file_path and last_modified and (file_path not in mtimes or last_modified > mtimes[file_path]):
            mtimes[file_path] = last_modified
    return mtimes


def embed_texts(embedder, texts: list[str]) -> list[list[float]]:
    return embedder.embed(texts)


def delete_file_chunks(collection, file_path: str) -> int:
    """Delete all chunks for a given file path. Returns count deleted."""
    result = collection.query.fetch_objects(
        filters=wvq.Filter.by_property("file_path").equal(file_path),
        limit=10000,
        include_vector=False,
    )
    # Re-check the exact path. The filter is only as precise as the property's
    # tokenization, and a tokenization regression would not register as schema
    # drift — collection_matches_expected_schema compares property names only.
    uuids = [obj.uuid for obj in result.objects if obj.properties.get("file_path") == file_path]
    for uuid in uuids:
        collection.data.delete_by_id(uuid)
    return len(uuids)


def index_file(
    collection,
    embedder,
    manifest,
    file_type: str,
    path: Path,
    *,
    root: Path,
    dry_run: bool = False,
    retraction_overlay: dict[str, dict] | None = None,
    enrich: Callable[[dict], dict] | None = None,
    char_budget: int = 12000,
) -> int:
    """Chunk, enrich, embed, and upsert a single file."""
    rel_path = path.relative_to(root).as_posix()

    if file_type == "binary" or is_binary_file(path):
        print(f"  {rel_path}: SKIPPED (binary content: not indexable as text)")
        return 0

    text = path.read_text(errors="replace")

    chunker = CHUNKER_MAP[file_type]
    chunks = chunker(text, rel_path, char_budget) if file_type == "csharp" else chunker(text, rel_path)
    enrich = enrich or (lambda c: enrich_chunk(c, manifest))
    enriched_chunks = [enrich(chunk) for chunk in chunks]

    if not enriched_chunks:
        return 0

    if dry_run:
        print(f"  {rel_path}: {len(enriched_chunks)} chunks (dry run)")
        return len(enriched_chunks)

    vectors = embed_texts(embedder, [render_embedding_text(chunk) for chunk in enriched_chunks])
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)

    objects = []
    for chunk, vector in zip(enriched_chunks, vectors, strict=True):
        identity = stable_chunk_identity(rel_path, chunk)
        properties = {
            "content": chunk["content"],
            "file_path": rel_path,
            "chunk_type": chunk["chunk_type"],
            "file_type": chunk.get("file_type"),
            "authority_level": chunk.get("authority_level"),
            "document_kind": chunk.get("document_kind"),
            "area": chunk.get("area"),
            "project": chunk.get("project"),
            "section_heading": chunk.get("section_heading"),
            "section_path": chunk.get("section_path"),
            "semantic_label": chunk.get("semantic_label"),
            "namespace": chunk.get("namespace"),
            "type_name": chunk.get("type_name"),
            "member_name": chunk.get("member_name"),
            "member_kind": chunk.get("member_kind"),
            "decision_topic": chunk.get("decision_topic"),
            "decision_status": chunk.get("decision_status"),
            "record_id": chunk.get("record_id"),
            "chunk_index": chunk["chunk_index"],
            "last_modified": mtime.isoformat(),
        }
        if retraction_overlay and chunk.get("chunk_type") != "decision":
            retraction = retraction_for_chunk(chunk, retraction_overlay)
            if retraction:
                properties["retraction_summary"] = retraction["retraction_summary"]
                properties["retraction_decision"] = retraction["retraction_decision"]
                properties["retraction_date"] = retraction["retraction_date"]
        objects.append(
            wvd.DataObject(
                properties=properties,
                vector=vector,
                uuid=weaviate.util.generate_uuid5(identity),
            )
        )

    inserted = _insert_verified(collection, objects, rel_path)

    # Deterministic UUID5 keys make an insert an upsert, so the previous
    # generation of this file's chunks is already overwritten. Only keys the
    # file no longer produces are stale, and they are removed AFTER the insert
    # — deleting first would race the write of the very same key.
    _delete_stale_chunks(collection, rel_path, keep={str(obj.uuid) for obj in objects})

    return inserted


def _delete_stale_chunks(collection, file_path: str, keep: set[str]) -> int:
    """Remove chunks stored for this file that the current chunking no longer emits."""
    result = collection.query.fetch_objects(
        filters=wvq.Filter.by_property("file_path").equal(file_path),
        limit=10000,
        include_vector=False,
    )
    removed = 0
    for obj in result.objects:
        # Same exact-path re-check as delete_file_chunks: never delete a chunk
        # that belongs to a different file just because the filter matched it.
        if obj.properties.get("file_path") != file_path:
            continue
        if str(obj.uuid) not in keep:
            collection.data.delete_by_id(obj.uuid)
            removed += 1
    return removed


def _insert_verified(collection, objects: list, rel_path: str) -> int:
    """Insert objects and return how many actually landed.

    insert_many reports per-object failures in its result rather than raising.
    Discarding that result and returning len(objects) is how a --full run once
    claimed 4,652 chunks while Weaviate held 4,493, with twenty files missing
    outright and nothing in the log to say so. In a retrieval index that is the
    worst kind of failure: the corpus looks complete and the missing documents
    are simply never returned.

    Failures under load are usually transient, so retry once before giving up,
    and make a surviving failure loud rather than silent.
    """
    result = collection.data.insert_many(objects)
    if not result.has_errors:
        return len(objects)

    failed_indices = sorted(result.errors.keys())
    retry = [objects[i] for i in failed_indices if i < len(objects)]
    first_error = result.errors[failed_indices[0]].message
    print(f"  {rel_path}: {len(retry)} object(s) failed to insert, retrying: {first_error[:160]}")

    if not retry:
        return len(objects)

    retry_result = collection.data.insert_many(retry)
    if not retry_result.has_errors:
        return len(objects)

    still_failed = len(retry_result.errors)
    message = retry_result.errors[sorted(retry_result.errors.keys())[0]].message
    print(f"  {rel_path}: INSERT FAILED for {still_failed} object(s) after retry: {message[:160]}")
    return max(0, len(objects) - still_failed)


def stable_chunk_identity(file_path: str, chunk: dict[str, object]) -> str:
    """Build a deterministic chunk identity from semantic fields."""
    parts = [
        file_path,
        str(chunk.get("chunk_type", "")),
        str(chunk.get("section_path", "")),
        str(chunk.get("type_name", "")),
        str(chunk.get("member_name", "")),
        str(chunk.get("chunk_index", "")),
    ]
    return "|".join(parts)


def clean_orphans(collection, indexed_paths: set[str]) -> int:
    """Delete chunks for files that no longer exist on disk."""
    all_paths = set()
    for obj in collection.iterator(include_vector=False):
        file_path = obj.properties.get("file_path", "")
        if file_path:
            all_paths.add(file_path)

    deleted = 0
    for file_path in all_paths - indexed_paths:
        removed = delete_file_chunks(collection, file_path)
        if removed:
            print(f"  Removed {removed} orphaned chunks for {file_path}")
            deleted += removed
    return deleted
