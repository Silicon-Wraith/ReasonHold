import hashlib
import json

from reasonhold.chunkers import chunk_decisions
from reasonhold.decisions import DecisionLog, decision_id, iter_supersedes_rows, record_id


def rec(topic, dt, **extra):
    return {"topic": topic, "decision": "d", "rationale": "r", "datetime": dt, **extra}


def dump(path, *records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


def test_decision_id_matches_the_constraint():
    expected = "dec-" + hashlib.sha256(b"topic-a|2026-10-01T00:00:00+00:00").hexdigest()[:12]
    assert decision_id("topic-a", "2026-10-01T00:00:00+00:00") == expected


def test_ids_are_derived_for_legacy_records_and_kept_when_explicit():
    assert record_id(rec("a", "t1")) == decision_id("a", "t1")
    assert record_id(rec("a", "t1", id="dec-000000000000")) == "dec-000000000000"


def test_status_is_computed_from_supersedes_records(tmp_path):
    a = rec("a", "t1")
    b = rec("b", "t2", supersedes_records=[decision_id("a", "t1")])
    c = rec("c", "t3", status="superseded")
    log = DecisionLog.load(dump(tmp_path / "d.jsonl", a, b, c))
    assert log.status(decision_id("a", "t1")) == "superseded"
    assert log.superseded_by(decision_id("a", "t1")) == [decision_id("b", "t2")]
    assert log.status(decision_id("b", "t2")) == "active"
    assert log.status(decision_id("c", "t3")) == "superseded"
    assert [r["topic"] for r in log.active()] == ["b"]


def test_a_superseded_record_stops_retracting(tmp_path):
    a = rec("a", "t1", supersedes=[{"path": "docs/x.md", "retraction_summary": "x is wrong"}])
    b = rec("b", "t2", supersedes_records=[decision_id("a", "t1")])
    path = dump(tmp_path / "d.jsonl", a)
    assert [r.path for r in DecisionLog.load(path).retractions()] == ["docs/x.md"]
    path = dump(tmp_path / "d.jsonl", a, b)
    assert DecisionLog.load(path).retractions() == []
    assert list(iter_supersedes_rows(path)) == []


def test_retraction_fields_and_hash(tmp_path):
    a = rec("a", "t1", supersedes=[{"path": "docs/x.md#Queue", "retraction_summary": "LIFO now"}])
    log = DecisionLog.load(dump(tmp_path / "d.jsonl", a))
    (r,) = log.retractions()
    assert (r.file_path, r.section, r.topic, r.decision_id) == ("docs/x.md", "Queue", "a", decision_id("a", "t1"))
    before = log.retraction_sha256()
    log2 = DecisionLog.load(dump(tmp_path / "d.jsonl", a, rec("b", "t2")))
    assert log2.retraction_sha256() == before
    log3 = DecisionLog.load(dump(tmp_path / "d.jsonl", a, rec("b", "t2", supersedes_records=[decision_id("a", "t1")])))
    assert log3.retraction_sha256() != before


def test_malformed_lines_are_skipped(tmp_path):
    path = tmp_path / "d.jsonl"
    path.write_text('{"topic": "a", "datetime": "t1"}\nnot json\n\n')
    assert [r["topic"] for r in DecisionLog.load(path).records] == ["a"]
    assert DecisionLog.load(tmp_path / "missing.jsonl").records == []


def test_decision_chunks_carry_record_id_and_computed_status():
    a = rec("a", "t1")
    b = rec("b", "t2", supersedes_records=[decision_id("a", "t1")])
    chunks = chunk_decisions(json.dumps(a) + "\n" + json.dumps(b) + "\n", "decisions.jsonl")
    assert [c["record_id"] for c in chunks] == [decision_id("a", "t1"), decision_id("b", "t2")]
    assert [c["decision_status"] for c in chunks] == ["superseded", "active"]
    assert "Status: superseded" in chunks[0]["content"]


def test_non_object_json_lines_are_skipped(tmp_path):
    from reasonhold.decisions import DecisionLog

    path = tmp_path / "decisions.jsonl"
    path.write_text('[1]\n5\n"s"\nnull\n{"id": "dec-1", "topic": "t", "decision": "d", "datetime": "x"}\n')
    log = DecisionLog.load(path)
    assert log.get("dec-1") is not None
