"""Render the session preamble.

Four sections in priority order: the index state (branch, collection, fresh or
the stale causes, notes), superseded content, open conflicts, open candidates.
The whole text stays within MAX_PREAMBLE_LINES and MAX_PREAMBLE_BYTES; when it
would not, whole rows are dropped from the lowest-priority section first and a
trimmed section says how many remain. The index section is never trimmed.

This runs from a SessionStart hook, so a failure here must not cost the operator
their session: every failure becomes a line of output and nothing raises.

Superseded content is the section that earns the preamble's cost. It names the
documents an active decision has retracted, so a session learns that before it
reads them rather than after acting on them.

The decisions.jsonl scan is imported from decisions.py rather than repeated here.
A second implementation of "what counts as an active retraction" is a drift
generator.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

from reasonhold.decisions import iter_supersedes_rows

# Display caps. The budget these serve is asserted in tests/test_preamble.py:
# the whole preamble stays within 60 lines and 4KB, because it is paid for on
# every session start and budgets expressed as intentions drift upward.
ROLE_A_MAX_ROWS = 25

# Hard budget for the whole preamble, asserted in tests. Calibrated against the
# reference implementation's render, measured at 3,390 bytes / 52 lines.
MAX_PREAMBLE_LINES = 60
MAX_PREAMBLE_BYTES = 4096

# Seconds allowed for the index-state probe; well under the SessionStart hook timeout.
TIMEOUT_INDEX = 6.0


@dataclass(frozen=True)
class SupersedesRow:
    date: str
    topic: str
    path: str
    retraction_summary: str


def _cell(text: str) -> str:
    """Make a string safe inside a markdown table cell."""
    return str(text).replace("|", r"\|").replace("\n", " ").replace("\r", " ")


def load_active_supersedes(decisions_file: Path) -> list[SupersedesRow]:
    """Every active retraction, newest first, nothing collapsed.

    Deliberately not the same shape as overlay.py's load_retraction_overlay, which
    keys by path so later decisions win. A chunk can only carry one retraction;
    the operator needs to see all of them, including two corrections to the same
    document.
    """
    rows = [
        SupersedesRow(date=date, topic=topic, path=path, retraction_summary=summary)
        for date, topic, path, summary in iter_supersedes_rows(decisions_file)
    ]
    rows.sort(key=lambda r: r.date, reverse=True)
    return rows


def render_role_a(rows: list[SupersedesRow], max_bytes: int | None = None) -> str:
    """The superseded-content table, or a one-line statement that there is none.

    Rows are dropped, never truncated, when the budget binds. The summary is the
    part a reader acts on — "treat the summary as current truth" — so a shortened
    one is worse than an absent one, because it looks complete. What overflows is
    signposted to `reasonhold decisions search` instead.
    """
    if not rows:
        return "## Superseded content\n\nNo active supersessions recorded.\n"

    shown = rows[:ROLE_A_MAX_ROWS]
    if max_bytes is not None:
        while shown and len(_role_a_table(shown, len(rows)).encode()) > max_bytes:
            shown = shown[:-1]
        if not shown:
            return (
                f"## Superseded content\n\n{len(rows)} active supersessions: too "
                f"many to list here. Run `reasonhold decisions search` before trusting any "
                f"architecture document.\n"
            )
    return _role_a_table(shown, len(rows))


ROLE_A_OVERFLOW_HINT = "`reasonhold decisions search` for the rest."
ROLE_A_HEADER = [
    "An active decision retracts each path below. Treat the summary as current "
    "truth and the document as stale where they disagree.",
    "",
    "| Path | Now holds | Decision | Date |",
    "|---|---|---|---|",
]


def _retraction_row(row: SupersedesRow) -> str:
    return (
        f"| `{_cell(row.path)}` | {_cell(row.retraction_summary)} "
        f"| `{_cell(row.topic)}` | {row.date.split('T')[0]} |"
    )


def _role_a_table(shown: list[SupersedesRow], total: int) -> str:
    lines = ["## Superseded content", "", *ROLE_A_HEADER]
    lines.extend(_retraction_row(row) for row in shown)
    if len(shown) < total:
        lines.append(f"\n*{len(shown)} most recent of {total}. {ROLE_A_OVERFLOW_HINT}*")
    return "\n".join(lines) + "\n"


@dataclass
class Section:
    title: str
    rows: list[str]
    empty: str | None
    more: str
    header: list[str] = field(default_factory=list)


def _render(sections: list[Section], shown: list[int]) -> str:
    parts = []
    for section, n in zip(sections, shown):
        if not section.rows:
            if section.empty is not None:
                parts.append(f"## {section.title}\n\n{section.empty}\n")
            continue
        lines = [f"## {section.title}", ""] + section.header + section.rows[:n]
        if n < len(section.rows):
            lines.append(f"\n*{n} most recent of {len(section.rows)}. {section.more}*")
        parts.append("\n".join(lines) + "\n")
    return "\n".join(parts)


def fit(sections: list[Section], max_lines: int, max_bytes: int) -> str:
    shown = [len(s.rows) for s in sections]

    def over(text: str) -> bool:
        return len(text.splitlines()) > max_lines or len(text.encode()) > max_bytes

    text = _render(sections, shown)
    while over(text):
        trimmable = [i for i in range(1, len(sections)) if shown[i] > 0]  # section 0 (Index) is never trimmed
        if not trimmable:
            break
        shown[trimmable[-1]] -= 1
        text = _render(sections, shown)
    return text


def index_lines(project, *, connect=None, timeout: float = TIMEOUT_INDEX) -> list[str]:
    """One probe of the index, bounded by a daemon thread so a hung store cannot hold the session."""
    result: list[str] = []

    def probe() -> None:
        try:
            from reasonhold.lifecycle import index_state
            from reasonhold.store import connect as default_connect

            client = (connect or default_connect)()
            try:
                state = index_state(project, client)
            finally:
                client.close()
            where = f"- Branch `{state.branch}`, collection `{state.collection}`"
            if not state.exists:
                result.append(f"{where}: index missing, run `reasonhold index`")
            elif state.fresh:
                result.append(f"{where}: fresh")
            else:
                result.append(f"{where}: stale")
                result.extend(f"  - {cause}" for cause in state.stale)
            result.extend(f"- Note: {note}" for note in state.notes)
        except Exception as exc:  # fail open: any failure is a line, never an exception
            result[:] = [f"- Index: unavailable ({type(exc).__name__}: {exc})"]

    worker = threading.Thread(target=probe, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        return [f"- Index: unavailable (no answer within {timeout:.0f}s)"]
    return result or ["- Index: unavailable"]


def _guarded(build) -> list[str]:
    """One section's rows; a failure becomes one error row, never a lost preamble."""
    try:
        return build()
    except Exception as exc:
        return [f"- unavailable ({type(exc).__name__}: {exc})"]


def skills_rows(root: Path):
    """The installed skill pack's notice, as a builder for _guarded."""
    def build() -> list[str]:
        from reasonhold.skills import skills_line

        line = skills_line(root)
        return [f"- {line}"] if line else []
    return build


def render_preamble(
    root: Path | str | None = None,
    *,
    max_lines: int = MAX_PREAMBLE_LINES,
    max_bytes: int = MAX_PREAMBLE_BYTES,
    index_probe=None,
) -> str:
    try:
        from reasonhold.errors import ManifestInvalid
        from reasonhold.pending import PendingLog
        from reasonhold.project import Project

        try:
            project = Project.load(root)
        except ManifestInvalid as exc:
            return f"ReasonHold is not configured here ({exc}).\n"
        try:
            index = (index_probe or index_lines)(project)
        except Exception as exc:
            index = [f"- Index: unavailable ({type(exc).__name__}: {exc})"]
        index = index + _guarded(skills_rows(project.root))

        def retractions() -> list[str]:
            return [_retraction_row(r) for r in load_active_supersedes(project.decisions_path)]

        def pending_rows(kind: str, fmt) -> list[str]:
            pending = PendingLog.load(project.pending_path)
            # Filter with the log's own predicate, passed as a value: this module's source must hold no direct file open.
            open_ids = set(filter(pending.is_open, (r["id"] for r in pending.records)))
            return [fmt(r) for r in reversed(pending.records) if r["kind"] == kind and r["id"] in open_ids]

        def conflict_row(c: dict) -> str:
            return f"- `{c['id']}` {_cell(c['doc_a'])} vs {_cell(c['doc_b'])}: {_cell(c['claim'])}"

        def candidate_row(c: dict) -> str:
            return f"- `{c['id']}` {_cell(c['target'])} <- {_cell(', '.join(c['reads']))} ({_cell(c['reason'])})"

        sections = [
            Section(f"ReasonHold: {project.id}", index, None, ""),
            Section(
                "Superseded content",
                _guarded(retractions),
                "No active supersessions recorded.",
                ROLE_A_OVERFLOW_HINT,
                header=ROLE_A_HEADER,
            ),
            Section("Open conflicts", _guarded(lambda: pending_rows("conflict", conflict_row)), None,
                    "`reasonhold conflicts` for the rest."),
            Section("Open candidates", _guarded(lambda: pending_rows("candidate_binding", candidate_row)), None,
                    "`reasonhold candidates list` for the rest."),
        ]
        return fit(sections, max_lines, max_bytes)
    except Exception as exc:  # the preamble always prints something and always exits 0
        return f"ReasonHold preamble unavailable ({type(exc).__name__}: {exc}).\n"


def claude_hook_json(text: str) -> str:
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}})
