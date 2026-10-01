"""The retraction overlay: which chunks an active decision retracts (R-07)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from reasonhold.decisions import DecisionLog
from reasonhold.pending import follow_alias


def load_retraction_overlay(decisions_path: Path, aliases: Mapping[str, str] | None = None) -> dict[str, dict]:
    """Keyed by retracted path (optionally with #section). Later decisions win on
    collisions. A retraction recorded against a path that has since moved
    (a path_alias record) also applies under the current path."""
    overlay: dict[str, dict] = {}
    for r in DecisionLog.load(decisions_path).retractions():
        value = {"retraction_summary": r.retraction_summary, "retraction_decision": r.topic, "retraction_date": r.date}
        overlay[r.path] = value
        if aliases:
            current = follow_alias(r.file_path, aliases)
            if current != r.file_path:
                overlay[current + (f"#{r.section}" if r.section else "")] = value
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
