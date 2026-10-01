"""Role A is the section that earns the preamble's cost.

It tells a session which documents are partially retracted before it reads them.
Everything else in the preamble is convenience; this is the part that prevents
acting on superseded design.

The parsing is shared with docs-rag/index.py rather than duplicated, because a
second implementation of retraction parsing is the same drift generator that got
.claude/memory/MEMORY.md retired — an unaudited second copy of an audited fact.

But the two consumers need different shapes, and that difference is the subtle
part. index.py's load_retraction_overlay returns a dict keyed by path, so later
decisions win on collision; that is right for annotating a chunk, which can only
carry one retraction. Role A must show the operator EVERY retraction, including
two corrections to the same document. Hence a shared row-level parse, with the
overlay built on top of it.
"""

from __future__ import annotations

import reasonhold.bootstrap as reasonhold_bootstrap
from pathlib import Path

import pytest

from reasonhold.bootstrap import SupersedesRow, load_active_supersedes, render_role_a

FIXTURE = Path(__file__).parent / "fixtures" / "decisions_sample.jsonl"


@pytest.fixture
def rows():
    return load_active_supersedes(FIXTURE)


class TestLoadActiveSupersedes:
    def test_builds_one_row_per_path_retraction_pair(self, rows):
        assert len(rows) == 5, [r.path for r in rows]

    def test_excludes_records_whose_status_is_superseded(self, rows):
        """A superseded decision's retraction no longer holds."""
        assert not [r for r in rows if "ghost" in r.path]

    def test_records_without_supersedes_contribute_nothing(self, rows):
        assert not [r for r in rows if r.topic == "no-supersedes"]

    def test_section_anchor_is_preserved_verbatim(self, rows):
        anchored = [r for r in rows if r.path.startswith("docs/architecture/beta.md")]
        assert anchored[0].path == "docs/architecture/beta.md#Design Principles"

    def test_both_retractions_of_the_same_path_appear(self, rows):
        """The overlay collapses these; Role A must not.

        index.py keys its overlay by path, so a second correction to the same
        document silently replaces the first. A reader of the preamble needs both.
        """
        alpha = [r for r in rows if r.path == "docs/architecture/alpha.md"]
        assert len(alpha) == 2, f"a retraction was collapsed away: {alpha}"

    def test_one_record_may_retract_several_paths(self, rows):
        multi = sorted(r.path for r in rows if r.topic == "multi-entry")
        assert multi == ["docs/one.md", "docs/two.md"]

    def test_entries_missing_path_or_summary_are_skipped(self, rows):
        assert not [r for r in rows if "nosummary" in r.path]

    def test_unparseable_lines_do_not_abort_the_scan(self, rows):
        """The fixture ends with a junk line; everything before it must survive."""
        assert len(rows) == 5

    def test_sorted_newest_first(self, rows):
        dates = [r.date for r in rows]
        assert dates == sorted(dates, reverse=True)

    def test_missing_file_returns_empty_not_an_exception(self, tmp_path):
        assert load_active_supersedes(tmp_path / "nope.jsonl") == []


class TestRenderRoleA:
    def test_empty_renders_a_short_line_not_an_empty_table(self):
        """3 of 177 decisions carry supersedes today, so empty is the normal case."""
        out = render_role_a([])
        assert "No active supersessions" in out
        assert "|" not in out
        assert len(out.splitlines()) <= 4

    def test_table_carries_path_summary_topic_and_date(self, rows):
        out = render_role_a(rows)
        assert "docs/architecture/alpha.md" in out
        assert "A second, later correction" in out
        assert "second-retraction-same-path" in out
        assert "2026-05-14" in out

    def test_pipes_in_content_are_escaped(self):
        row = SupersedesRow(
            date="2026-01-01T00:00:00+00:00", topic="t", path="docs/a.md", retraction_summary="has | a pipe"
        )
        out = render_role_a([row])
        assert r"has \| a pipe" in out

    def test_newlines_in_a_summary_do_not_break_the_table(self):
        row = SupersedesRow(
            date="2026-01-01T00:00:00+00:00", topic="t", path="docs/a.md", retraction_summary="line one\nline two"
        )
        out = render_role_a([row])
        assert "line one line two" in out
        assert len([ln for ln in out.splitlines() if ln.startswith("|")]) == 3


class TestSharedParsing:
    def test_bootstrap_does_not_reimplement_the_decisions_scan(self):
        """The decisions.jsonl parse is shared with index.py; a second copy is the defect.

        Scoped to that file deliberately. bootstrap.py legitimately parses other
        JSON — `gh pr list --json` in Role C — so a blanket ban on json.loads
        would be wrong and would have to be relaxed later, which is how a guard
        stops guarding.
        """
        source = (Path(reasonhold_bootstrap.__file__)).read_text()
        assert "iter_supersedes_rows" in source, "bootstrap.py must reuse index.py's shared supersedes parse"
        assert "open(" not in source, (
            "bootstrap.py opens a file directly; the decisions scan is delegated "
            "to index.py and nothing else here should need file I/O"
        )

    def test_the_guard_tolerates_a_default_argument(self):
        """Regression: an earlier version of the guard above matched
        `decisions_file: Path = DECISIONS_FILE)` and failed on correct code.
        A guard that fires on legitimate use gets relaxed, and then guards nothing.
        """
        source = (Path(reasonhold_bootstrap.__file__)).read_text()
        assert "= DECISIONS_FILE" in source, "the default argument is expected here"

    def test_overlay_still_collapses_by_path(self):
        """index.py's own behaviour must be unchanged by the refactor."""
        from reasonhold.overlay import load_retraction_overlay

        overlay = load_retraction_overlay(FIXTURE)
        assert overlay["docs/architecture/alpha.md"]["retraction_decision"] == "second-retraction-same-path", (
            "later decision must still win"
        )
        assert "docs/architecture/ghost.md" not in overlay


class TestRoleCFreshness:
    """Orientation, not authority. Cheap to render, cheaper to skip when broken."""

    def test_freshness_comes_from_symbols_not_an_ad_hoc_check(self):
        """One definition of 'is the index current', shared with /sync-docs."""
        source = (Path(reasonhold_bootstrap.__file__)).read_text()
        assert "symbols.py" in source and "--freshness" in source

    def test_no_current_focus_file_is_read(self):
        """Nebulon's preamble reads one; Ariadne has no equivalent and does not invent one."""
        source = (Path(reasonhold_bootstrap.__file__)).read_text()
        assert "CURRENT_FOCUS" not in source

    def test_recent_decisions_are_capped(self):
        source = (Path(reasonhold_bootstrap.__file__)).read_text()
        assert "LAST_N_DECISIONS = 15" in source

    def test_recent_commits_are_capped(self):
        source = (Path(reasonhold_bootstrap.__file__)).read_text()
        assert "LAST_N_COMMITS = 10" in source

    def test_a_failing_subprocess_degrades_to_one_line(self, monkeypatch):
        """No gh, no git, no index — the preamble still renders."""
        import reasonhold.bootstrap as bootstrap
        monkeypatch.setattr(bootstrap, "_run", lambda *a, **k: (127, "", "not found"))
        out = bootstrap.render_role_c()
        assert out, "role C vanished entirely instead of degrading"
        assert len(out.splitlines()) < 20

    def test_empty_pr_list_renders_no_pr_section(self, monkeypatch):
        """Ariadne has opened no PRs. An empty section is still noise."""
        import reasonhold.bootstrap as bootstrap
        monkeypatch.setattr(bootstrap, "_run", lambda *a, **k: (0, "", ""))
        assert "Open PRs" not in bootstrap.render_role_c()


class TestPreambleBudget:
    """The preamble is paid for on every session start, so the cap is a number.

    Calibrated against Nebulon's render, measured at 3,390 bytes / 52 lines. A
    budget expressed as an intention drifts upward one useful addition at a time,
    which is why this is a test and not a guideline.
    """

    MAX_LINES = 60
    MAX_BYTES = 4096

    def test_full_preamble_is_within_budget(self):
        import reasonhold.bootstrap as bootstrap
        out = bootstrap.render_preamble()
        assert len(out.splitlines()) <= self.MAX_LINES, (
            f"preamble is {len(out.splitlines())} lines, budget {self.MAX_LINES}"
        )
        assert len(out.encode()) <= self.MAX_BYTES, f"preamble is {len(out.encode())} bytes, budget {self.MAX_BYTES}"

    def test_budget_holds_with_a_full_role_a_table(self, monkeypatch):
        """The worst realistic case: ROLE_A_MAX_ROWS retractions, each verbose."""
        import reasonhold.bootstrap as bootstrap
        rows = [
            bootstrap.SupersedesRow(
                date="2026-08-19T00:00:00+00:00",
                topic=f"some-fairly-long-decision-topic-{i}",
                path=f"docs/architecture/some-document-with-a-long-name-{i}.md",
                retraction_summary="A retraction summary of the length these "
                "actually run to in practice, which is a "
                "sentence or two of real prose.",
            )
            for i in range(bootstrap.ROLE_A_MAX_ROWS)
        ]
        monkeypatch.setattr(bootstrap, "load_active_supersedes", lambda *a, **k: rows)
        monkeypatch.setattr(bootstrap, "_run", lambda *a, **k: (0, "", ""))
        out = bootstrap.render_preamble()
        assert len(out.encode()) <= self.MAX_BYTES, (
            f"a full Role A table blows the budget: {len(out.encode())} bytes. "
            "Lower ROLE_A_MAX_ROWS or truncate summaries."
        )


class TestTimeoutBudget:
    """A hook that outlives its own timeout looks exactly like a hung session start."""

    def test_worst_case_sum_is_under_the_hook_timeout(self):
        import reasonhold.bootstrap as bootstrap
        HOOK_TIMEOUT = 20
        assert bootstrap.TIMEOUT_TOTAL_BUDGET < HOOK_TIMEOUT, (
            f"worst-case subprocess time {bootstrap.TIMEOUT_TOTAL_BUDGET}s meets or "
            f"exceeds the {HOOK_TIMEOUT}s hook timeout"
        )

    def test_and_well_under_the_30s_design_cap(self):
        import reasonhold.bootstrap as bootstrap
        assert bootstrap.TIMEOUT_TOTAL_BUDGET < 30

    def test_the_network_call_is_the_tightest(self):
        """gh hits GitHub; the design says the preamble must not block on network."""
        import reasonhold.bootstrap as bootstrap
        assert bootstrap.TIMEOUT_GH <= bootstrap.TIMEOUT_FRESHNESS
