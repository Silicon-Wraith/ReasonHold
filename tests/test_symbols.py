"""The index is a symbol table; symbols.py is how a skill reads it exactly.

Index-backed /sync-docs checks report a defect when a symbol is ABSENT, so
their recall must be total. Decision `substrate-checks-use-property-filters`
bars vector search for exactly that reason: a chunk ranking below top_k would
become a false "missing symbol" finding. That rule is only worth anything if
something enforces it, which is what TestQueryPathIsExact does.

The freshness half exists because a drift check reading a stale index reports
on a snapshot — precisely the failure it exists to detect. Its interesting
bugs are not logical but representational: Weaviate hands back either a
tz-aware datetime or an ISO string depending on the client path, while
Path.stat().st_mtime is a naive float. index.py:501 already guards the string
case with an isinstance check; comparing a naive datetime against an aware one
raises TypeError, which would surface as a crashed audit rather than a wrong
answer. Both are pinned below.
"""

from __future__ import annotations

import reasonhold.codeindex as reasonhold_symbols
from datetime import UTC, datetime, timedelta
from pathlib import Path

from reasonhold.codeindex import (
    FreshnessReport,
    coerce_mtime,
    compare_freshness,
    select_by_prefix,
    symbol_names,
)

INDEXED_AT = datetime(2026, 8, 19, 12, 0, 0, tzinfo=UTC)


class TestFreshnessComparison:
    """Freshness must agree with index.py's own rule: file_mtime <= stored is fresh."""

    def test_working_copy_newer_than_index_is_stale(self):
        report = compare_freshness(
            indexed={"CLAUDE.md": INDEXED_AT},
            working={"CLAUDE.md": INDEXED_AT + timedelta(minutes=5)},
        )

        assert report.stale == ("CLAUDE.md",), f"edited file not reported stale: {report}"
        assert not report.is_clean

    def test_equal_mtimes_are_fresh(self):
        """index.py skips when file_mtime <= stored_mtime, so equality is fresh, not stale."""
        report = compare_freshness(
            indexed={"CLAUDE.md": INDEXED_AT},
            working={"CLAUDE.md": INDEXED_AT},
        )

        assert report.stale == (), f"equal mtimes wrongly reported stale: {report}"
        assert report.is_clean

    def test_working_copy_older_than_index_is_fresh(self):
        report = compare_freshness(
            indexed={"CLAUDE.md": INDEXED_AT},
            working={"CLAUDE.md": INDEXED_AT - timedelta(hours=1)},
        )

        assert report.is_clean, f"older working copy wrongly reported stale: {report}"

    def test_corpus_file_never_indexed_is_missing_not_stale(self):
        """A new file has no indexed mtime to compare against. It is a distinct finding."""
        report = compare_freshness(
            indexed={"CLAUDE.md": INDEXED_AT},
            working={"CLAUDE.md": INDEXED_AT, "docs/specs/new-design.md": INDEXED_AT},
        )

        assert report.missing == ("docs/specs/new-design.md",), f"new file not reported missing: {report}"
        assert report.stale == ()
        assert not report.is_clean

    def test_indexed_file_no_longer_in_corpus_is_orphaned(self):
        """A deleted or de-scoped file leaves chunks behind that still answer queries."""
        report = compare_freshness(
            indexed={"CLAUDE.md": INDEXED_AT, "docs/removed.md": INDEXED_AT},
            working={"CLAUDE.md": INDEXED_AT},
        )

        assert report.orphaned == ("docs/removed.md",), f"deleted file not reported orphaned: {report}"
        assert not report.is_clean

    def test_clean_index_reports_clean(self):
        report = compare_freshness(
            indexed={"CLAUDE.md": INDEXED_AT, "AGENTS.md": INDEXED_AT},
            working={"CLAUDE.md": INDEXED_AT, "AGENTS.md": INDEXED_AT},
        )

        assert report == FreshnessReport(stale=(), missing=(), orphaned=(), fresh=2)
        assert report.is_clean

    def test_findings_are_sorted_for_stable_output(self):
        """The skill prints these; unstable ordering makes two identical runs look different."""
        report = compare_freshness(
            indexed={},
            working={"z.md": INDEXED_AT, "a.md": INDEXED_AT, "m.md": INDEXED_AT},
        )

        assert report.missing == ("a.md", "m.md", "z.md")


class TestMtimeCoercion:
    """Weaviate returns a datetime or an ISO string; st_mtime is a naive float."""

    def test_iso_string_from_weaviate_is_coerced(self):
        assert coerce_mtime("2026-08-19T12:00:00+00:00") == INDEXED_AT

    def test_iso_string_with_z_suffix_is_coerced(self):
        assert coerce_mtime("2026-08-19T12:00:00Z") == INDEXED_AT

    def test_aware_datetime_passes_through(self):
        assert coerce_mtime(INDEXED_AT) == INDEXED_AT

    def test_naive_datetime_is_assumed_utc_not_rejected(self):
        """index.py always writes tz-aware UTC, so a naive value means a lossy round-trip."""
        assert coerce_mtime(datetime(2026, 8, 19, 12, 0, 0)) == INDEXED_AT

    def test_unparseable_value_is_none_not_an_exception(self):
        assert coerce_mtime("not-a-timestamp") is None
        assert coerce_mtime(None) is None

    def test_mixed_naive_and_aware_never_raises(self):
        """A TypeError here would crash the audit rather than report a wrong answer."""
        report = compare_freshness(
            indexed={"CLAUDE.md": "2026-08-19T12:00:00+00:00"},
            working={"CLAUDE.md": datetime(2026, 8, 19, 13, 0, 0)},
        )

        assert report.stale == ("CLAUDE.md",), f"naive/aware comparison went wrong: {report}"

    def test_uncoercible_indexed_value_is_treated_as_missing(self):
        """Better to reindex the file than to silently call it fresh on a bad timestamp."""
        report = compare_freshness(
            indexed={"CLAUDE.md": "garbage"},
            working={"CLAUDE.md": INDEXED_AT},
        )

        assert report.missing == ("CLAUDE.md",), f"bad indexed timestamp not surfaced: {report}"


class TestPrefixSelection:
    """Prefix narrowing happens in Python, after retrieval, so completeness is visible."""

    ROWS = [
        {"file_path": "src/database/projects.py", "section_heading": "create_project"},
        {"file_path": "src/database/postgres/triggers/touch.sql", "section_heading": "touch_fn"},
        {"file_path": "src/worker/chunker.py", "section_heading": "chunk"},
    ]

    def test_prefix_keeps_only_matching_paths(self):
        rows = select_by_prefix(self.ROWS, ["src/database/"])

        assert [r["file_path"] for r in rows] == [
            "src/database/projects.py",
            "src/database/postgres/triggers/touch.sql",
        ]

    def test_deeper_prefix_isolates_trigger_functions(self):
        """wrapper-call-sites must exclude triggers; this is how it gets that list."""
        rows = select_by_prefix(self.ROWS, ["src/database/postgres/triggers/"])

        assert [r["section_heading"] for r in rows] == ["touch_fn"]

    def test_multiple_prefixes_union(self):
        rows = select_by_prefix(self.ROWS, ["src/worker/", "src/database/projects.py"])

        assert len(rows) == 2

    def test_no_prefix_returns_everything(self):
        assert select_by_prefix(self.ROWS, []) == self.ROWS
        assert select_by_prefix(self.ROWS, None) == self.ROWS

    def test_non_matching_prefix_returns_empty_not_error(self):
        """An empty result is a legitimate answer — 'no symbols here' — not a failure."""
        assert select_by_prefix(self.ROWS, ["src/nonexistent/"]) == []


class TestSymbolNames:
    def test_names_are_sorted_and_deduped(self):
        rows = [
            {"section_heading": "get_project_sp"},
            {"section_heading": "create_project_sp"},
            {"section_heading": "get_project_sp"},
        ]

        assert symbol_names(rows) == ["create_project_sp", "get_project_sp"]

    def test_blank_headings_are_dropped(self):
        rows = [{"section_heading": ""}, {"section_heading": None}, {"section_heading": "real_fn"}]

        assert symbol_names(rows) == ["real_fn"]

    def test_missing_key_does_not_raise(self):
        assert symbol_names([{"file_path": "x.py"}]) == []


class TestQueryPathIsExact:
    """Decision `substrate-checks-use-property-filters`, enforced rather than asserted."""

    BANNED = ("near_vector", "near_text", "hybrid", "bm25", "generate")

    def test_source_contains_no_ranked_search_call(self):
        source = (Path(reasonhold_symbols.__file__)).read_text()

        found = [term for term in self.BANNED if term in source]

        assert not found, (
            f"codeindex.py references ranked search ({', '.join(found)}). "
            "An absence finding sourced from a ranked result is the false positive "
            "decision `substrate-checks-use-property-filters` exists to prevent."
        )

    def test_source_uses_property_filters_and_iterator(self):
        source = (Path(reasonhold_symbols.__file__)).read_text()

        assert "by_property" in source, "codeindex.py does not filter by property"
        assert "iterator(" in source, "codeindex.py does not use iterator(), so recall is not total"


class TestEmptyFilesAreNotFreshnessFindings:
    """A 0-byte file produces no chunks, so absence from the index is correct.

    index.py:294 returns 0 for a file that chunks to nothing. Reporting those as
    "not indexed" put 15 permanent lines into a freshness report that is meant to
    gate the audit — and worse, would make --freshness exit non-zero forever and
    trigger a reindex that could not possibly change the outcome.

    Dropping them silently would be the opposite mistake: docs/operator-runbook.md
    is 0 bytes while sync-doc.yaml lists it as a deployment doc, and
    tests/unit/test_scrapy_downloader.py is an empty test. Those are real findings
    for the audit to raise, just not freshness ones. So they are reported in their
    own category and excluded from the freshness verdict.
    """

    def test_empty_file_is_categorised_empty_not_missing(self):
        report = compare_freshness(
            indexed={"CLAUDE.md": INDEXED_AT},
            working={"CLAUDE.md": INDEXED_AT, "src/__init__.py": INDEXED_AT},
            empty={"src/__init__.py"},
        )

        assert report.empty == ("src/__init__.py",), f"empty file miscategorised: {report}"
        assert report.missing == (), "an empty file is not a missing file"

    def test_empty_files_do_not_make_the_index_stale(self):
        """Otherwise --freshness exits 1 forever and forces a no-op reindex."""
        report = compare_freshness(
            indexed={"CLAUDE.md": INDEXED_AT},
            working={"CLAUDE.md": INDEXED_AT, "src/__init__.py": INDEXED_AT},
            empty={"src/__init__.py"},
        )

        assert report.is_clean, f"empty files wrongly blocked the audit: {report}"

    def test_a_genuinely_missing_file_still_reports_missing(self):
        report = compare_freshness(
            indexed={},
            working={"docs/specs/new-design.md": INDEXED_AT, "src/__init__.py": INDEXED_AT},
            empty={"src/__init__.py"},
        )

        assert report.missing == ("docs/specs/new-design.md",)
        assert report.empty == ("src/__init__.py",)
        assert not report.is_clean

    def test_empty_defaults_to_nothing_so_existing_callers_are_unaffected(self):
        report = compare_freshness(indexed={}, working={"a.md": INDEXED_AT})

        assert report.empty == ()
        assert report.missing == ("a.md",)
