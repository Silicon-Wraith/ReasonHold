import json

import pytest

from helpers import FakeCollection, FakeProvider, make_repo
from reasonhold.decisions import DecisionLog, decision_id
from reasonhold.errors import StoreUnavailable, UnknownRecord
from reasonhold.project import Project
from reasonhold.writes import apply_retraction_to_chunks, mark_records_superseded, store_decision

HUMAN = {"kind": "human", "actor": "operator"}


@pytest.fixture
def project(tmp_path):
    make_repo(tmp_path, commit=False)
    return Project.load(tmp_path)


def lines(project):
    return [json.loads(x) for x in project.decisions_path.read_text().splitlines() if x.strip()]


def call(project, collection, provider, **kw):
    args = dict(topic="queue-order", decision="LIFO", rationale="because", provenance=HUMAN)
    args.update(kw)
    return store_decision(project, collection, provider, **args)


def test_store_decision_appends_then_indexes(project):
    col = FakeCollection()
    col.add("u1", file_path="docs/architecture/overview.md", chunk_type="markdown_section", section_heading="Queue")
    out = call(project, col, FakeProvider(), datetime_="2026-10-01T00:00:00+00:00",
               supersedes=[{"path": "docs/architecture/overview.md#queue", "retraction_summary": "LIFO now"}])
    (stored,) = lines(project)
    assert stored["id"] == decision_id("queue-order", "2026-10-01T00:00:00+00:00")
    assert stored["provenance"] == HUMAN and stored["supersedes_records"] == []
    assert out["indexed"] is True and out["annotated_chunks"] == 1 and out["warnings"] == []
    decision_chunks = [o for o in col.objects.values() if o.properties.get("chunk_type") == "decision"]
    assert decision_chunks[0].properties["record_id"] == stored["id"]
    assert decision_chunks[0].properties["file_path"] == "decisions.jsonl"
    assert col.objects["u1"].properties["retraction_summary"] == "LIFO now"


def test_store_decision_appends_nothing_when_embedding_fails(project):
    with pytest.raises(StoreUnavailable):
        call(project, FakeCollection(), FakeProvider(fail=True))
    assert project.decisions_path.read_text() == ""
    call(project, FakeCollection(), FakeProvider())
    assert len(lines(project)) == 1


def test_same_topic_and_datetime_is_idempotent(project):
    for _ in range(2):
        out = call(project, FakeCollection(), FakeProvider(), datetime_="2026-10-01T00:00:00+00:00")
    assert len(lines(project)) == 1 and out["warnings"] == ["already recorded"]


def test_unknown_supersedes_record_is_rejected_before_anything_happens(project):
    provider = FakeProvider()
    with pytest.raises(UnknownRecord):
        call(project, FakeCollection(), provider, supersedes_records=["dec-000000000000"])
    assert provider.calls == [] and project.decisions_path.read_text() == ""


def test_invalid_input_is_rejected(project):
    with pytest.raises(ValueError):
        call(project, FakeCollection(), FakeProvider(), topic="")
    with pytest.raises(ValueError):
        call(project, FakeCollection(), FakeProvider(), provenance={"kind": "robot"})
    with pytest.raises(ValueError):
        call(project, FakeCollection(), FakeProvider(), supersedes=[{"path": "x"}])


def test_supersedes_records_marks_old_chunks_superseded(project):
    first = call(project, FakeCollection(), FakeProvider(), topic="a", datetime_="t1")["record"]
    col = FakeCollection()
    col.add("old", chunk_type="decision", record_id=first["id"], decision_status="active")
    out = call(project, col, FakeProvider(), topic="b", datetime_="t2", supersedes_records=[first["id"]])
    assert col.objects["old"].properties["decision_status"] == "superseded"
    assert DecisionLog.load(project.decisions_path).status(first["id"]) == "superseded"
    assert out["status"] == "active"


def test_index_failure_after_append_is_a_warning(project):
    col = FakeCollection()
    col.fail_inserts = True
    out = call(project, col, FakeProvider())
    assert len(lines(project)) == 1 and out["indexed"] is False
    assert "run `reasonhold index`" in out["warnings"][0]


def test_missing_index_is_a_warning(project):
    out = call(project, None, FakeProvider())
    assert len(lines(project)) == 1 and out["indexed"] is False and out["warnings"]


def test_helpers_respect_decision_chunks():
    col = FakeCollection()
    col.add("d", chunk_type="decision", file_path="docs/x.md", record_id="dec-1")
    assert apply_retraction_to_chunks(col, "docs/x.md", "s", "t", "d") == 0
    assert mark_records_superseded(col, ["dec-1"]) == 1
