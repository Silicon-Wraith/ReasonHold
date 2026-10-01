#!/usr/bin/env python3
"""Index project docs and source code into Weaviate for docs-rag."""

from __future__ import annotations

import argparse
import socket
import time
from datetime import UTC, datetime
from pathlib import Path

import ollama as ollama_client
import weaviate
import weaviate.classes.data as wvd
import weaviate.classes.query as wvq
from reasonhold.chunkers import CHUNKER_MAP

# Re-exported for callers that still import them from here. iter_decision_records
# is unused in this module by design — it is part of the public surface, not dead.
from reasonhold.decisions import iter_decision_records, iter_supersedes_rows  # noqa: F401
from reasonhold.enrichment import enrich_chunk, render_embedding_text
from reasonhold.manifest import Manifest, load_manifest
from reasonhold.store import CollectionMeta, ensure_collection, connect as get_client

from reasonhold.config import (
    COLLECTION_NAME,
    DECISIONS_FILE,
    EMBEDDING_DIMS,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_CHAR_BUDGET,
    EMBEDDING_MODEL,
    EXCLUDED_PATH_PARTS,
    OLLAMA_HOST,
    OLLAMA_PORT,
    PROJECT_ROOT,
    SYNC_DOC_PATH,
    WEAVIATE_HOST,
    WEAVIATE_PORT,
)


def load_retraction_overlay(decisions_path: Path) -> dict[str, dict]:
    """Build a retraction-overlay map from the decision log.

    Returns dict keyed by superseded path (optionally with #section).
    Values carry retraction_summary, retraction_decision, retraction_date.
    Only active decisions contribute; later decisions win on path collisions.
    """
    overlay: dict[str, dict] = {}
    for date, topic, path, summary in iter_supersedes_rows(decisions_path):
        overlay[path] = {
            "retraction_summary": summary,
            "retraction_decision": topic,
            "retraction_date": date,
        }
    return overlay


def retraction_for_chunk(chunk: dict, overlay: dict[str, dict]) -> dict | None:
    """Return the retraction metadata for a chunk if its path (optionally
    with #section) is superseded. Path-only entries match any chunk from
    that file; path#section entries match only chunks whose section_heading
    contains the anchor as a case-insensitive substring after stripping
    surrounding whitespace. No punctuation normalization is performed."""
    file_path = chunk.get("file_path", "")
    if not file_path:
        return None

    # Exact path match first (doc-wide retraction)
    if file_path in overlay:
        return overlay[file_path]

    # Section-level match
    section_heading = (chunk.get("section_heading") or "").strip().lower()
    prefix = file_path + "#"
    for key, value in overlay.items():
        if not key.startswith(prefix):
            continue
        anchor = key[len(prefix) :].strip().lower()
        # Case-insensitive substring match. Tighten with punctuation
        # normalization when a real false positive appears (see plan note).
        if anchor and (anchor == section_heading or anchor in section_heading):
            return value

    return None


def gather_files(manifest: Manifest, area_names: set[str] | None = None) -> list[tuple[str, Path]]:
    """Resolve manifest corpus globs into unique (file_type, path) pairs."""
    files: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    extra = [str(DECISIONS_FILE.relative_to(PROJECT_ROOT))] if DECISIONS_FILE.exists() else []
    for pattern in manifest.iter_corpus_globs(area_names, extra=extra):
        for path in sorted(PROJECT_ROOT.glob(pattern)):
            if path.is_file() and not is_excluded_path(path) and path not in seen:
                seen.add(path)
                files.append((detect_file_type(path), path))
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


def detect_file_type(path: Path) -> str:
    """Map a path to a chunker key.

    Extensionless files (Dockerfile, justfile) legitimately fall through to the
    markdown chunker — they are text. Known-binary suffixes must not: see
    _BINARY_SUFFIXES.
    """
    if path == DECISIONS_FILE:
        return "decisions"
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


def is_excluded_path(path: Path) -> bool:
    return any(part in EXCLUDED_PATH_PARTS for part in path.parts)


def get_indexed_mtimes(collection) -> dict[str, datetime]:
    """Fetch file_path -> max last_modified from Weaviate for incremental checks."""
    mtimes: dict[str, datetime] = {}
    for obj in collection.iterator(include_vector=False):
        file_path = obj.properties.get("file_path", "")
        last_modified = obj.properties.get("last_modified")
        if file_path and last_modified and (file_path not in mtimes or last_modified > mtimes[file_path]):
            mtimes[file_path] = last_modified
    return mtimes


def embed_texts(
    oll_client: ollama_client.Client,
    texts: list[str],
    batch_size: int = EMBEDDING_BATCH_SIZE,
) -> list[list[float]]:
    """Embed texts via Ollama using the configured batch size."""
    all_embeddings: list[list[float]] = []
    for index in range(0, len(texts), batch_size):
        batch = [text[:EMBEDDING_CHAR_BUDGET] for text in texts[index : index + batch_size]]
        response = oll_client.embed(model=EMBEDDING_MODEL, input=batch)
        all_embeddings.extend(response["embeddings"])
    return all_embeddings


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
    oll_client: ollama_client.Client,
    manifest: Manifest,
    file_type: str,
    path: Path,
    dry_run: bool = False,
    retraction_overlay: dict[str, dict] | None = None,
) -> int:
    """Chunk, enrich, embed, and upsert a single file."""
    rel_path = str(path.relative_to(PROJECT_ROOT))

    if file_type == "binary" or is_binary_file(path):
        print(f"  {rel_path}: SKIPPED (binary content — not indexable as text)")
        return 0

    text = path.read_text(errors="replace")

    chunker = CHUNKER_MAP[file_type]
    chunks = chunker(text, rel_path, EMBEDDING_CHAR_BUDGET) if file_type == "csharp" else chunker(text, rel_path)
    enriched_chunks = [enrich_chunk(chunk, manifest) for chunk in chunks]

    if not enriched_chunks:
        return 0

    if dry_run:
        print(f"  {rel_path}: {len(enriched_chunks)} chunks (dry run)")
        return len(enriched_chunks)

    vectors = embed_texts(oll_client, [render_embedding_text(chunk) for chunk in enriched_chunks])
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
    print(f"  {rel_path}: {len(retry)} object(s) failed to insert, retrying — {first_error[:160]}")

    if not retry:
        return len(objects)

    retry_result = collection.data.insert_many(retry)
    if not retry_result.has_errors:
        return len(objects)

    still_failed = len(retry_result.errors)
    message = retry_result.errors[sorted(retry_result.errors.keys())[0]].message
    print(f"  {rel_path}: INSERT FAILED for {still_failed} object(s) after retry — {message[:160]}")
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


def verify_prerequisites() -> None:
    """Fail fast when Ollama or Weaviate are unavailable."""
    _assert_tcp_connectivity(OLLAMA_HOST, OLLAMA_PORT, "Ollama")
    _assert_tcp_connectivity(WEAVIATE_HOST, WEAVIATE_PORT, "docs-rag Weaviate")


def _assert_tcp_connectivity(host: str, port: int, name: str) -> None:
    try:
        with socket.create_connection((host, port), timeout=2):
            return
    except OSError as exc:
        raise RuntimeError(f"{name} is unavailable at {host}:{port}. Start the service and retry.") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Index project docs for docs-rag")
    parser.add_argument("--full", action="store_true", help="Force full re-index")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be indexed")
    parser.add_argument(
        "--area",
        action="append",
        default=[],
        help="Restrict indexing to one or more sync-doc manifest areas",
    )
    args = parser.parse_args()

    manifest = load_manifest(SYNC_DOC_PATH)
    area_names = set(args.area) if args.area else None
    files = gather_files(manifest, area_names)
    print(f"Found {len(files)} files to consider")

    if args.dry_run:
        # Route through index_file so the dry run exercises the same guards as
        # a real pass — notably the binary refusal, which a direct
        # CHUNKER_MAP lookup would bypass (and KeyError on).
        total = sum(index_file(None, None, manifest, file_type, path, dry_run=True) for file_type, path in files)
        print(f"\nTotal: {total} chunks (dry run)")
        return

    verify_prerequisites()
    oll = ollama_client.Client(host=f"http://{OLLAMA_HOST}:{OLLAMA_PORT}")
    client = get_client()
    try:
        ensure_collection(
            client,
            COLLECTION_NAME,
            CollectionMeta("seed", "seed", "ollama:" + EMBEDDING_MODEL, EMBEDDING_DIMS),
            recreate=args.full,
        )
        collection = client.collections.get(COLLECTION_NAME)
        indexed_mtimes = {} if args.full else get_indexed_mtimes(collection)

        retraction_overlay = load_retraction_overlay(DECISIONS_FILE)
        if retraction_overlay:
            print(f"  Retraction overlay: {len(retraction_overlay)} entries loaded")

        total_chunks = 0
        indexed_count = 0
        skipped_count = 0
        indexed_paths: set[str] = set()
        start = time.time()

        for file_type, path in files:
            rel_path = str(path.relative_to(PROJECT_ROOT))
            indexed_paths.add(rel_path)

            if not args.full and rel_path in indexed_mtimes:
                file_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
                stored_mtime = indexed_mtimes[rel_path]
                if isinstance(stored_mtime, datetime) and file_mtime <= stored_mtime:
                    skipped_count += 1
                    continue

            try:
                chunk_count = index_file(
                    collection,
                    oll,
                    manifest,
                    file_type,
                    path,
                    retraction_overlay=retraction_overlay,
                )
            except Exception as exc:
                print(f"  {rel_path}: SKIPPED ({type(exc).__name__}: {exc})")
                continue
            if chunk_count:
                print(f"  {rel_path}: {chunk_count} chunks")
                indexed_count += 1
                total_chunks += chunk_count

        orphaned = clean_orphans(collection, indexed_paths)
        elapsed = time.time() - start
        print(
            f"\nDone in {elapsed:.1f}s: {indexed_count} files indexed, "
            f"{skipped_count} skipped, {total_chunks} chunks, {orphaned} orphans removed"
        )

        # Reconcile what we claim against what the store holds. A full run
        # should match exactly; anything else means chunks were lost between
        # here and Weaviate, which is precisely the failure this run must not
        # report as success.
        if args.full:
            stored = collection.aggregate.over_all(total_count=True).total_count
            if stored != total_chunks:
                print(
                    f"WARNING: reported {total_chunks} chunks but the collection holds "
                    f"{stored} ({total_chunks - stored:+d}). The index is incomplete — "
                    f"re-run with --full."
                )
            else:
                print(f"Verified: collection holds {stored} chunks, matching the run.")
    finally:
        client.close()
        oll._client.close()


if __name__ == "__main__":
    main()
