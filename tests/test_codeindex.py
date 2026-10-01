import os
from datetime import UTC, datetime

import pytest

from helpers import FakeCollection, make_repo
from reasonhold.codeindex import absence_guard, freshness, is_code
from reasonhold.errors import IndexMissing, IndexStale
from reasonhold.lifecycle import IndexState
from reasonhold.project import Project


def state(exists=True, stale=()):
    return IndexState("p", "main", "main", "RH_P__main", exists, None, None, list(stale), [], [])


def test_freshness_compares_the_corpus_with_the_index(tmp_path):
    project = Project.load(make_repo(tmp_path, commit=False))
    col = FakeCollection()
    old = datetime(2020, 1, 1, tzinfo=UTC).isoformat()
    col.add("1", file_path="AGENTS.md", last_modified=old)
    col.add("2", file_path="gone.md", last_modified=old)
    report = freshness(project, col)
    assert "AGENTS.md" in report.stale and "gone.md" in report.orphaned
    assert "docs/specs/worker.md" in report.missing and "decisions.jsonl" in report.empty


def test_absence_guard():
    absence_guard(state(), None)
    with pytest.raises(IndexMissing):
        absence_guard(state(exists=False), None)
    with pytest.raises(IndexStale, match="HEAD moved"):
        absence_guard(state(stale=["HEAD moved"]), None)


def test_is_code():
    assert is_code({"file_type": "python"}) and not is_code({"file_type": "markdown"})
