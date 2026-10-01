#!/usr/bin/env python3
"""Render the session-bootstrap preamble.

Usage:
    python docs-rag/bootstrap.py                  # full preamble to stdout
    python docs-rag/bootstrap.py --section role_a # superseded content only
    python docs-rag/bootstrap.py --section role_c # freshness only

Exit codes: 0 always, short of a crash. This runs from a SessionStart hook, so a
failure here must not cost the operator their session — every section degrades to
a single line rather than raising, and a section that cannot be rendered says so.

Role A is the section that earns the preamble's cost. It names the documents an
active decision has retracted, so a session learns that before it reads them
rather than after acting on them. Role C is orientation: what changed lately.

The decisions.jsonl scan is imported from index.py rather than repeated here.
A second implementation of "what counts as an active retraction" is the drift
generator that got .claude/memory/ retired for holding a second copy of an
audited fact.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from reasonhold.decisions import iter_supersedes_rows

from reasonhold.config import DECISIONS_FILE

# Display caps. The budget these serve is asserted in tests/test_bootstrap.py:
# the whole preamble stays within 60 lines and 4KB, because it is paid for on
# every session start and budgets expressed as intentions drift upward.
ROLE_A_MAX_ROWS = 25
LAST_N_DECISIONS = 15
LAST_N_COMMITS = 10

# Hard budget for the whole preamble, asserted in tests. Calibrated against the
# reference implementation's render, measured at 3,390 bytes / 52 lines.
MAX_PREAMBLE_LINES = 60
MAX_PREAMBLE_BYTES = 4096

# Per-call timeouts, in seconds. These are chosen so their SUM stays well under
# the SessionStart hook's own timeout — a hook that outlives its budget is
# indistinguishable to the operator from a hung session start. Individually
# generous limits that sum past the cap is the easy mistake here: five calls at
# the old 8s default summed to 40s against a 30s cap.
TIMEOUT_FRESHNESS = 6.0  # queries Weaviate
TIMEOUT_GIT = 3.0  # local, should be instant
TIMEOUT_GH = 3.0  # hits the network; a PR count is not worth more
TIMEOUT_TOTAL_BUDGET = TIMEOUT_FRESHNESS + TIMEOUT_GH + 3 * TIMEOUT_GIT


@dataclass(frozen=True)
class SupersedesRow:
    date: str
    topic: str
    path: str
    retraction_summary: str


def _cell(text: str) -> str:
    """Make a string safe inside a markdown table cell."""
    return str(text).replace("|", r"\|").replace("\n", " ").replace("\r", " ")


def _run(cmd: list[str], timeout: float = TIMEOUT_GIT) -> tuple[int, str, str]:
    """Run a command, never raise. Returns (returncode, stdout, stderr).

    Every external call in Role C goes through here. A missing binary, a timeout,
    or a non-zero exit degrades that one line rather than the session.
    """
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except (OSError, subprocess.SubprocessError):
        return 127, "", "unavailable"


def load_active_supersedes(decisions_file: Path = DECISIONS_FILE) -> list[SupersedesRow]:
    """Every active retraction, newest first, nothing collapsed.

    Deliberately not the same shape as index.py's load_retraction_overlay, which
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
    signposted to search_decisions instead.
    """
    if not rows:
        return "## Superseded content\n\nNo active supersessions recorded.\n"

    shown = rows[:ROLE_A_MAX_ROWS]
    if max_bytes is not None:
        while shown and len(_role_a_table(shown, len(rows)).encode()) > max_bytes:
            shown = shown[:-1]
        if not shown:
            return (
                f"## Superseded content\n\n{len(rows)} active supersessions — too "
                f"many to list here. Run `search_decisions` before trusting any "
                f"architecture document.\n"
            )
    return _role_a_table(shown, len(rows))


def _role_a_table(shown: list[SupersedesRow], total: int) -> str:
    lines = [
        "## Superseded content",
        "",
        "An active decision retracts each path below. Treat the summary as current "
        "truth and the document as stale where they disagree.",
        "",
        "| Path | Now holds | Decision | Date |",
        "|---|---|---|---|",
    ]
    for row in shown:
        lines.append(
            f"| `{_cell(row.path)}` | {_cell(row.retraction_summary)} "
            f"| `{_cell(row.topic)}` | {row.date.split('T')[0]} |"
        )
    if len(shown) < total:
        lines.append(f"\n*{len(shown)} most recent of {total}. `search_decisions` for the rest.*")
    return "\n".join(lines) + "\n"


def render_role_c() -> str:
    """Freshness snapshot: what changed lately, and whether the index knows.

    Orientation only. Every line is optional — a section whose command fails is
    omitted rather than rendered as an error, because a session start is a poor
    place to learn that `gh` is not installed.
    """
    lines = ["## Freshness", ""]

    rc, out, _ = _run(
        [sys.executable, str(Path(__file__).with_name("symbols.py")), "--freshness"], timeout=TIMEOUT_FRESHNESS
    )
    if out:
        lines.append(f"- Index: {out.splitlines()[0]}")
    elif rc != 0:
        lines.append("- Index: freshness unavailable")

    rc, out, _ = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if rc == 0 and out:
        _, dirty, _ = _run(["git", "status", "--porcelain"])
        n = len([ln for ln in dirty.splitlines() if ln.strip()])
        lines.append(f"- Branch: `{out}`" + (f", {n} uncommitted" if n else ", clean"))

    rc, out, _ = _run(["gh", "pr", "list", "--json", "number,title", "--limit", "10"], timeout=TIMEOUT_GH)
    if rc == 0 and out and out.strip() not in ("", "[]"):
        lines.append(f"- Open PRs: {out.count('number')}")

    rc, out, _ = _run(["git", "log", f"-{LAST_N_COMMITS}", "--format=%h %s"])
    if rc == 0 and out:
        lines.append(f"- Last {LAST_N_COMMITS} commits:")
        lines.extend(f"  - {ln[:92]}" for ln in out.splitlines()[:LAST_N_COMMITS])

    return "\n".join(lines) + "\n"


def render_preamble() -> str:
    """Role C first, then Role A with whatever budget remains.

    Role C is small and bounded; Role A is the part that grows with the decision
    log. Giving Role A the remainder means the section that can overflow is the
    one that adapts, rather than the fixed section being squeezed by it.
    """
    role_c = render_role_c()
    remaining = MAX_PREAMBLE_BYTES - len(role_c.encode()) - 2
    role_a = render_role_a(load_active_supersedes(), max_bytes=max(remaining, 0))
    return role_a + "\n" + role_c


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the session preamble.")
    parser.add_argument("--section", choices=["role_a", "role_c"], help="One section only")
    args = parser.parse_args()

    if args.section == "role_a":
        sys.stdout.write(render_role_a(load_active_supersedes()))
    elif args.section == "role_c":
        sys.stdout.write(render_role_c())
    else:
        sys.stdout.write(render_preamble())
    return 0


if __name__ == "__main__":
    sys.exit(main())
