#!/usr/bin/env python3
"""Find decisions that read like retractions but retract nothing on the record.

This is the detector for the ADR-016 class of failure. A decision superseded a
design document, the decision was recorded, and no document ever said so — leaving
docs/architecture/design-decisions.md asserting a design the code had already moved
away from, with nothing to flag it. `/sync-docs` could not catch it either: its
cross-doc checks compare documents to each other, not to the decision store.

Usage:
    python docs-rag/audit_supersedes.py           # human-readable report
    python docs-rag/audit_supersedes.py --json    # machine-readable
    python docs-rag/audit_supersedes.py --strict  # exit 1 if any candidates

Read-only. This never writes to the decision log; correcting a record is a
`store_decision` call a human makes deliberately, not something an audit does.

The hard part is not matching retraction language — it is not crying wolf. A check
that flags every decision containing "remove" gets ignored within a week, and an
ignored check is worse than none because it looks like coverage. Hence the
exculpatory patterns below: a decision that says in its own text that nothing was
previously documented is taken at its word.

**This is a triage aid, not a gate, and precision is deliberately capped.**
Measured on the 178-record store: 19 candidates, of which several are false
positives that prose analysis cannot cheaply remove. The clearest example is
`validate-skills-upgraded-not-replaced`, whose text reads "No existing Ariadne
check is removed" — a sentence that means the opposite of what the match implies.
A negation guard was added for the immediate forms ("not replaced", "rather than
replacing"), which fixed that decision's match on "replace" and promptly found
"removed" instead.

That is the signal to stop. Further tuning over-fits the heuristic to this store
and makes it fragile without making it trustworthy. The report therefore labels
every finding with the word that triggered it and says plainly that each may be
correct — a reviewable list of 19 out of 178 is useful; a confident list that is
quietly wrong is not. Do not wire --strict into CI expecting a clean run.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from decisions_io import iter_decision_records  # noqa: E402

from config import DECISIONS_FILE  # noqa: E402

# Language that suggests prior documentation stopped being true.
RETRACTION_WORDS = (
    "supersede",
    "supersedes",
    "superseded",
    "retract",
    "retracts",
    "retracted",
    "replace",
    "replaces",
    "replaced",
    "remove",
    "removes",
    "removed",
    "obsolete",
    "deprecate",
    "deprecates",
    "deprecated",
    "decommission",
    "rewrite",
    "rewrites",
)

# Phrases by which a decision states there was nothing to retract. Taking these at
# face value risks a missed finding; not taking them risks a report nobody reads.
# A missed finding a human can still catch; an ignored report catches nothing.
NOTHING_RETRACTED = (
    "nothing is retracted",
    "nothing to retract",
    "retracts nothing",
    "no prior claim",
    "nothing previously documented",
    "was never documented",
)


@dataclass(frozen=True)
class Candidate:
    topic: str
    date: str
    matched: str
    decision: str


def _all_occurrences_negated(text: str, word: str) -> bool:
    """True when every occurrence of `word` is preceded by a negation.

    `validate-skills-upgraded-not-replaced` matched "replace" in a topic stating
    the skills were explicitly NOT replaced. Flagging that trains the reader to
    skim the report, and a skimmed report catches nothing — which is the failure
    this tool's own docstring warns about.

    Deliberately narrow: only immediate negation, and only when NO occurrence is
    un-negated. A decision saying "not replaced ... but we removed X" still flags
    on the second clause.
    """
    idx, negated, total = 0, 0, 0
    while (found := text.find(word, idx)) != -1:
        total += 1
        before = text[max(0, found - 14) : found]
        if before.rstrip().endswith(("not", "not-", "rather than", "instead of")):
            negated += 1
        idx = found + len(word)
    return total > 0 and negated == total


def _text_of(record: dict) -> str:
    parts = [record.get("topic", ""), record.get("decision", ""), record.get("rationale", "")]
    return " ".join(str(p) for p in parts).lower()


def find_candidates(decisions_file: Path = DECISIONS_FILE) -> list[Candidate]:
    """Active decisions using retraction language while recording no supersedes."""
    found: list[Candidate] = []
    for record in iter_decision_records(decisions_file):
        if record.get("status", "active") != "active":
            continue
        if record.get("supersedes"):
            continue

        text = _text_of(record)
        if any(phrase in text for phrase in NOTHING_RETRACTED):
            continue

        matched = next(
            (w for w in RETRACTION_WORDS if w in text and not _all_occurrences_negated(text, w)),
            None,
        )
        if not matched:
            continue

        found.append(
            Candidate(
                topic=record.get("topic", ""),
                date=str(record.get("datetime", ""))[:10],
                matched=matched,
                decision=str(record.get("decision", ""))[:160],
            )
        )
    return found


def render_report(candidates: list[Candidate]) -> str:
    if not candidates:
        return "No decisions use retraction language without recording supersedes.\n"

    lines = [
        f"{len(candidates)} decision(s) use retraction language but record no supersedes.",
        "",
        "Each may be correct — a decision can change direction without any prior",
        "document having asserted otherwise. Review, and where a document IS stale,",
        "record a new decision carrying `supersedes` rather than editing this log.",
        "",
    ]
    for c in candidates:
        lines.append(f"  {c.date}  {c.topic}")
        lines.append(f"            matched {c.matched!r}: {c.decision}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    parser.add_argument("--strict", action="store_true", help="Exit 1 if any candidates")
    args = parser.parse_args()

    candidates = find_candidates()
    if args.json:
        print(json.dumps([asdict(c) for c in candidates], indent=2))
    else:
        sys.stdout.write(render_report(candidates))
    return 1 if (args.strict and candidates) else 0


if __name__ == "__main__":
    sys.exit(main())
