"""Read the decision log. No heavy dependencies, by design.

Extracted from index.py so that reading decisions.jsonl does not drag in ollama,
weaviate and the chunkers. Two reasons, and the second matters more.

Cost: those imports were 0.49s of bootstrap.py's 0.54s import time, paid on every
session start for a module that only reads a text file.

Fragility: the SessionStart preamble must fail open. Depending on the whole
indexing stack to parse JSONL means a broken weaviate client kills the preamble —
which is precisely the section that warns a session it is about to read retracted
documentation. The part that must survive should depend on the least.

index.py re-exports both functions, so existing callers are unaffected.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path


def iter_decision_records(decisions_path: Path) -> Iterator[dict]:
    """Yield every well-formed record in the decision log, in file order.

    The single place decisions.jsonl is parsed. Two consumers need different
    questions answered — which retractions are active, and which decisions look
    like retractions but record none — and both read through here so there is one
    definition of a well-formed record.

    A malformed line is skipped, not fatal. A decision log that fails to parse
    must not take down indexing or a session start.
    """
    if not decisions_path.exists():
        return
    with open(decisions_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def iter_supersedes_rows(decisions_path: Path) -> Iterator[tuple[str, str, str, str]]:
    """Yield (date, topic, path, retraction_summary) for every active retraction.

    One tuple per (record, supersedes entry) pair — nothing is collapsed here.
    Two consumers need different shapes from the same scan, and the difference
    matters: load_retraction_overlay below keys by path so a chunk carries one
    retraction, while the session preamble must show every retraction including
    a second correction to the same document. Sharing the scan and diverging in
    the caller keeps one implementation of "what counts as an active retraction".

    Malformed lines and entries are skipped rather than fatal; a decision log
    that fails to parse must not take down indexing or session start.
    """
    for record in iter_decision_records(decisions_path):
        if record.get("status", "active") != "active":
            continue
        supersedes = record.get("supersedes")
        if not isinstance(supersedes, list):
            continue
        topic = record.get("topic", "")
        date = record.get("datetime", "")
        for entry in supersedes:
            if not isinstance(entry, dict):
                continue
            path = entry.get("path")
            summary = entry.get("retraction_summary")
            if not path or not summary:
                continue
            yield date, topic, path, summary
