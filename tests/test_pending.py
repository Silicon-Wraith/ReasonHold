import json

import pytest

from helpers import FakeCollection, FakeProvider, make_repo
from reasonhold.errors import UnknownRecord
from reasonhold.pending import PendingLog, follow_alias, make_record, pending_id
from reasonhold.project import Project
from reasonhold.writes import propose_binding, report_conflict, resolve, store_decision

AGENT = {"kind": "agent", "actor": "architect"}


@pytest.fixture
def project(tmp_path):
    make_repo(tmp_path, commit=False)
    return Project.load(tmp_path)


def test_pending_id_matches_the_constraint():
    import hashlib

    payload = {"old_path": "a.md", "new_path": "b.md"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    expected = "pen-" + hashlib.sha256(f"path_alias|t1|{canonical}".encode()).hexdigest()[:12]
    assert pending_id("path_alias", "t1", payload) == expected
    assert make_record("path_alias", payload, AGENT, datetime_="t1")["id"] == expected


def test_open_until_resolved(project):
    cand = propose_binding(project, target="worker-contract", reads=["docs/specs/retry.md"],
                           validates_against=["src/worker/"], reason="new spec", provenance=AGENT)
    log = PendingLog.load(project.pending_path)
    assert [r["id"] for r in log.open("candidate_binding")] == [cand["id"]]
    resolve(project, pending_ids=[cand["id"]], outcome="rejected", note="no", provenance={"kind": "human"})
    log = PendingLog.load(project.pending_path)
    assert log.open() == [] and log.resolution_for(cand["id"])["outcome"] == "rejected"


def test_resolve_refuses_unknown_or_closed_ids(project):
    with pytest.raises(UnknownRecord):
        resolve(project, pending_ids=["pen-000000000000"], outcome="resolved", provenance={"kind": "human"})
    conflict = report_conflict(project, doc_a="docs/a.md#Queue", doc_b="docs/b.md", paths=["src/q.py"],
                               claim="FIFO or LIFO", evidence_a="FIFO", evidence_b="LIFO", provenance=AGENT)
    resolve(project, pending_ids=[conflict["id"]], outcome="resolved", provenance={"kind": "human"})
    with pytest.raises(UnknownRecord):
        resolve(project, pending_ids=[conflict["id"]], outcome="resolved", provenance={"kind": "human"})


def test_invalid_writes_append_nothing(project):
    with pytest.raises(ValueError):
        report_conflict(project, doc_a="docs/a.md", doc_b="docs/a.md", paths=[], claim="x",
                        evidence_a="a", evidence_b="b", provenance=AGENT)
    with pytest.raises(ValueError):
        propose_binding(project, target="", reads=["x.md"], validates_against=["src/"], reason="r", provenance=AGENT)
    with pytest.raises(ValueError):
        propose_binding(project, target="t", reads=["/etc/passwd"], validates_against=["src/"], reason="r", provenance=AGENT)
    assert not project.pending_path.exists()


def test_store_decision_resolves_a_conflict_in_one_call(project):
    conflict = report_conflict(project, doc_a="docs/a.md", doc_b="docs/b.md", paths=["src/q.py"],
                               claim="c", evidence_a="a", evidence_b="b", provenance=AGENT)
    out = store_decision(project, FakeCollection(), FakeProvider(), topic="queue", decision="FIFO",
                         rationale="r", resolves=[conflict["id"]], provenance={"kind": "human"})
    log = PendingLog.load(project.pending_path)
    assert not log.is_open(conflict["id"])
    assert log.resolution_for(conflict["id"])["decision_id"] == out["record"]["id"]
    assert out["record"]["resolves"] == [conflict["id"]]


def test_store_decision_with_unknown_resolves_appends_nothing(project):
    with pytest.raises(UnknownRecord):
        store_decision(project, FakeCollection(), FakeProvider(), topic="t", decision="d", rationale="r",
                       resolves=["pen-000000000000"], provenance={"kind": "human"})
    assert project.decisions_path.read_text() == ""


def test_aliases_follow_chains_and_survive_loops():
    log = PendingLog([
        make_record("path_alias", {"old_path": "a.md", "new_path": "b.md"}, AGENT, datetime_="t1"),
        make_record("path_alias", {"old_path": "b.md", "new_path": "c.md"}, AGENT, datetime_="t2"),
    ])
    assert follow_alias("a.md", log.aliases()) == "c.md"
    assert log.former_names("c.md") == {"a.md", "b.md", "c.md"}
    assert follow_alias("x.md", {"x.md": "y.md", "y.md": "x.md"}) in {"x.md", "y.md"}


def test_retry_after_crash_between_appends_closes_the_conflict(project):
    from reasonhold.decisions import decision_id
    from reasonhold.jsonl import append_jsonl

    conflict = report_conflict(project, doc_a="docs/a.md", doc_b="docs/b.md", paths=["src/q.py"],
                               claim="c", evidence_a="a", evidence_b="b", provenance=AGENT)
    rid = decision_id("queue", "t1")
    append_jsonl(project.decisions_path, {"id": rid, "topic": "queue", "decision": "FIFO", "rationale": "r",
                                          "datetime": "t1", "resolves": [conflict["id"]],
                                          "provenance": {"kind": "human"}})
    out = store_decision(project, FakeCollection(), FakeProvider(), topic="queue", decision="FIFO", rationale="r",
                         resolves=[conflict["id"]], provenance={"kind": "human"}, datetime_="t1")
    assert out["warnings"] == ["already recorded"]
    log = PendingLog.load(project.pending_path)
    assert not log.is_open(conflict["id"])
    assert log.resolution_for(conflict["id"])["decision_id"] == rid
    assert len(project.decisions_path.read_text().splitlines()) == 1


def test_identical_retry_after_success_appends_nothing(project):
    conflict = report_conflict(project, doc_a="docs/a.md", doc_b="docs/b.md", paths=[],
                               claim="c", evidence_a="a", evidence_b="b", provenance=AGENT)
    kwargs = dict(topic="queue", decision="FIFO", rationale="r", resolves=[conflict["id"]],
                  provenance={"kind": "human"}, datetime_="t1")
    store_decision(project, FakeCollection(), FakeProvider(), **kwargs)
    before = (project.decisions_path.read_text(), project.pending_path.read_text())
    out = store_decision(project, FakeCollection(), FakeProvider(), **kwargs)
    assert out["warnings"] == ["already recorded"]
    assert (project.decisions_path.read_text(), project.pending_path.read_text()) == before
