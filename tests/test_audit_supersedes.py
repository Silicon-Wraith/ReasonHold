"""Find decisions that read like retractions but retract nothing on the record.

This is the detector for the ADR-016 class of failure: a decision superseded a
design document, the decision was recorded, and no document ever said so — leaving
docs/architecture/design-decisions.md still asserting a design the code had already
moved away from. Nothing caught it for months.

The hard part is not matching retraction language. It is not crying wolf. A check
that flags every decision containing the word "remove" gets ignored within a week,
and an ignored check is worse than none because it looks like coverage.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from audit_supersedes import find_candidates, render_report

FIXTURE = Path(__file__).parent / "fixtures" / "audit_sample.jsonl"


@pytest.fixture
def candidates():
    return find_candidates(FIXTURE)


class TestFindCandidates:
    def test_flags_retraction_language_with_no_supersedes(self, candidates):
        topics = {c.topic for c in candidates}
        assert "replace-fastapi-with-servicestack" in topics

    def test_flags_an_empty_supersedes_list_not_just_a_missing_key(self, candidates):
        """`supersedes: []` is the same defect as no key at all."""
        assert "deprecate-queue-manager" in {c.topic for c in candidates}

    def test_does_not_flag_a_decision_that_already_supersedes(self, candidates):
        assert "retract-the-old-chunking-adr" not in {c.topic for c in candidates}

    def test_does_not_flag_a_decision_with_no_retraction_language(self, candidates):
        assert "choose-spacy-lg" not in {c.topic for c in candidates}

    def test_ignores_records_that_are_themselves_superseded(self, candidates):
        """A superseded decision's obligations no longer apply."""
        assert "kill-the-legacy-path" not in {c.topic for c in candidates}

    def test_a_decision_that_says_it_retracts_nothing_is_not_flagged(self, candidates):
        """The anti-false-positive case, and the reason this is not a keyword grep.

        remove-worktree-phase matches on "remove" but states in its own text that
        nothing was previously documented, so there is nothing to retract. Flagging
        it would train the reader to ignore the report.
        """
        assert "remove-worktree-phase" not in {c.topic for c in candidates}, (
            "flagged a decision that explicitly retracts nothing — this check would be noise"
        )

    def test_reports_which_word_triggered_the_match(self, candidates):
        """A finding the reader cannot evaluate is a finding they will skip."""
        c = next(c for c in candidates if c.topic == "replace-fastapi-with-servicestack")
        assert c.matched in ("replace", "replaces")

    def test_missing_file_returns_empty_not_an_exception(self, tmp_path):
        assert find_candidates(tmp_path / "nope.jsonl") == []


class TestRenderReport:
    def test_clean_store_says_so_explicitly(self):
        out = render_report([])
        assert "No decisions" in out or "none" in out.lower()

    def test_report_names_the_topic_and_the_trigger(self, candidates):
        out = render_report(candidates)
        assert "replace-fastapi-with-servicestack" in out
        assert "replace" in out


class TestDoesNotMutate:
    def test_the_decision_log_is_never_written(self):
        source = (Path(__file__).parent.parent / "audit_supersedes.py").read_text()
        for forbidden in ("open(", '"w"', "'w'", "write_text", "unlink"):
            assert forbidden not in source or forbidden == "open(", (
                f"audit_supersedes.py may modify the decision log: {forbidden}"
            )


class TestNegationGuard:
    """A check that flags 'not replaced' for containing 'replace' gets ignored."""

    def test_a_topic_saying_not_replaced_is_not_flagged(self, tmp_path):
        f = tmp_path / "d.jsonl"
        f.write_text(
            '{"topic":"validate-skills-upgraded-not-replaced","datetime":"2026-08-20T00:00:00+00:00",'
            '"status":"active","decision":"The skills gain a spine and are not replaced.","rationale":"r"}\n'
        )
        assert find_candidates(f) == []

    def test_rather_than_and_instead_of_also_negate(self, tmp_path):
        f = tmp_path / "d.jsonl"
        f.write_text(
            '{"topic":"a","datetime":"2026-08-20T00:00:00+00:00","status":"active",'
            '"decision":"We extend it rather than replace it.","rationale":"r"}\n'
        )
        assert find_candidates(f) == []

    def test_one_negated_and_one_real_use_still_flags(self, tmp_path):
        """Narrow by design: negation excuses only when every occurrence is negated."""
        f = tmp_path / "d.jsonl"
        f.write_text(
            '{"topic":"b","datetime":"2026-08-20T00:00:00+00:00","status":"active",'
            '"decision":"Not replaced, but the old adapter is removed.","rationale":"r"}\n'
        )
        assert len(find_candidates(f)) == 1
