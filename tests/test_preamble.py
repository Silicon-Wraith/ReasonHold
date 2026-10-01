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

import json
import time
from pathlib import Path

import pytest
from helpers import FakeClient, FakeCollection, make_repo

import reasonhold.preamble
from reasonhold.errors import StoreUnavailable
from reasonhold.jsonl import append_jsonl
from reasonhold.pending import make_record
from reasonhold.project import Project
from reasonhold.preamble import (
    MAX_PREAMBLE_BYTES,
    MAX_PREAMBLE_LINES,
    TIMEOUT_INDEX,
    SupersedesRow,
    claude_hook_json,
    index_lines,
    load_active_supersedes,
    render_preamble,
    render_role_a,
)

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
        source = (Path(reasonhold.preamble.__file__)).read_text()
        assert "iter_supersedes_rows" in source, "bootstrap.py must reuse index.py's shared supersedes parse"
        assert "open(" not in source, (
            "bootstrap.py opens a file directly; the decisions scan is delegated "
            "to index.py and nothing else here should need file I/O"
        )

    def test_overlay_still_collapses_by_path(self):
        """index.py's own behaviour must be unchanged by the refactor."""
        from reasonhold.overlay import load_retraction_overlay

        overlay = load_retraction_overlay(FIXTURE)
        assert overlay["docs/architecture/alpha.md"]["retraction_decision"] == "second-retraction-same-path", (
            "later decision must still win"
        )
        assert "docs/architecture/ghost.md" not in overlay


AGENT = {"kind": "agent"}
LONG = "A retraction summary of the length these actually run to in practice, a sentence or two of prose."


def crowded_repo(tmp_path):
    root = make_repo(tmp_path, commit=False)
    with open(root / "decisions.jsonl", "w") as fh:
        for i in range(40):
            fh.write(json.dumps({"topic": f"topic-{i:02d}", "decision": "d", "rationale": "r",
                                 "datetime": f"2026-09-{1 + i % 28:02d}T00:00:{i:02d}+00:00",
                                 "supersedes": [{"path": f"docs/architecture/long-document-name-{i}.md",
                                                 "retraction_summary": LONG}]}) + "\n")
    for i in range(20):
        append_jsonl(root / "reasonhold.pending.jsonl", make_record("conflict", {
            "doc_a": f"docs/a{i}.md", "doc_b": f"docs/b{i}.md", "paths": [], "claim": "they disagree about retries",
            "evidence_a": "a", "evidence_b": "b"}, AGENT, datetime_=f"t{i:02d}"))
        append_jsonl(root / "reasonhold.pending.jsonl", make_record("candidate_binding", {
            "target": "worker-contract", "reads": [f"docs/c{i}.md"], "validates_against": ["src/worker/"],
            "reason": "new spec"}, AGENT, datetime_=f"u{i:02d}"))
    return root


def fresh_probe(project):
    return ["- Branch `main`, collection `RH_X__main`: fresh"]


def within_budget(text):
    return len(text.splitlines()) <= MAX_PREAMBLE_LINES and len(text.encode()) <= MAX_PREAMBLE_BYTES


def test_preamble_fails_open_without_store(tmp_path):
    root = make_repo(tmp_path, commit=False)

    def down(project):
        raise StoreUnavailable("cannot reach Weaviate at localhost:8081")

    out = render_preamble(root, index_probe=down)
    assert "unavailable" in out and "localhost:8081" in out and within_budget(out)


def test_preamble_without_a_manifest_is_one_line(tmp_path):
    out = render_preamble(tmp_path)
    assert "not configured" in out and len(out.splitlines()) == 1


def test_budget_drops_whole_rows_lowest_priority_first(tmp_path):
    out = render_preamble(crowded_repo(tmp_path), index_probe=fresh_probe)
    assert within_budget(out)
    assert "fresh" in out                                    # the index section is never trimmed
    assert "most recent of 20" in out                        # candidates (and maybe conflicts) were trimmed
    table_rows = [ln for ln in out.splitlines() if ln.startswith("| `docs/")]
    assert table_rows and all(ln.endswith("|") for ln in table_rows)   # rows dropped whole, never cut
    assert out.index("Superseded content") < out.index("Open conflicts") < out.index("Open candidates")


def test_retractions_outrank_conflicts_and_candidates(tmp_path):
    out = render_preamble(crowded_repo(tmp_path), index_probe=fresh_probe, max_bytes=2048)
    assert len(out.encode()) <= 2048 and "| `docs/" in out
    assert "0 most recent of 20. `reasonhold candidates list`" in out
    assert "0 most recent of 20. `reasonhold conflicts`" in out


def test_claude_hook_format():
    payload = json.loads(claude_hook_json("hello"))
    assert payload == {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "hello"}}


def test_probe_timeout_is_under_the_hook_timeout():
    assert TIMEOUT_INDEX < 20


def test_index_lines_times_out_on_a_hung_store(tmp_path):
    project = Project.load(make_repo(tmp_path, commit=False))
    start = time.monotonic()
    out = index_lines(project, connect=lambda: time.sleep(2), timeout=0.2)
    assert time.monotonic() - start < 1.0
    assert len(out) == 1 and "unavailable" in out[0]


def test_index_lines_reports_a_connect_error(tmp_path):
    project = Project.load(make_repo(tmp_path, commit=False))

    def boom():
        raise StoreUnavailable("no route to host")

    out = index_lines(project, connect=boom)
    assert out == ["- Index: unavailable (StoreUnavailable: no route to host)"]


def test_index_lines_missing_index_closes_the_client(tmp_path):
    project = Project.load(make_repo(tmp_path, commit=False))
    client = FakeClient()
    out = index_lines(project, connect=lambda: client)
    assert "index missing" in out[0]
    assert client.closed


def test_index_lines_stale_lists_causes(tmp_path):
    project = Project.load(make_repo(tmp_path, commit=False))
    from reasonhold.lifecycle import index_state

    probe_client = FakeClient()
    name = index_state(project, probe_client).collection
    client = FakeClient(FakeCollection(name))      # exists, but carries no ReasonHold metadata
    out = index_lines(project, connect=lambda: client)
    assert "stale" in out[0]
    assert any("no ReasonHold metadata" in ln for ln in out[1:])
    assert client.closed


def test_a_corrupt_pending_log_does_not_cost_the_other_sections(tmp_path, monkeypatch):
    root = crowded_repo(tmp_path)

    def broken(cls, path):
        raise ValueError("corrupt pending log")

    monkeypatch.setattr("reasonhold.pending.PendingLog.load", classmethod(broken))
    out = render_preamble(root, index_probe=fresh_probe, max_lines=1000, max_bytes=100000)
    assert "fresh" in out and "| `docs/" in out
    assert out.count("unavailable (ValueError: corrupt pending log)") == 2   # conflicts and candidates
