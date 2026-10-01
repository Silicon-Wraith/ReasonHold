import pytest

from helpers import MINIMAL_MANIFEST, git, make_repo, write
from reasonhold.errors import UnknownRecord
from reasonhold.governance import conflicts, coverage, decision, governing_docs, retractions_for
from reasonhold.jsonl import append_jsonl
from reasonhold.pending import make_record
from reasonhold.project import Project
from reasonhold.writes import propose_binding, report_conflict, store_decision

HUMAN, AGENT = {"kind": "human"}, {"kind": "agent"}


class NoEmbed:
    model_id, dims = "x", 1

    def embed(self, texts):
        return [[0.0] for _ in texts]


def decide(project, **kw):
    args = dict(topic="t", decision="d", rationale="r", provenance=HUMAN)
    args.update(kw)
    return store_decision(project, None, NoEmbed(), **args)["record"]


@pytest.fixture
def project(tmp_path):
    return Project.load(make_repo(tmp_path))


def test_governing_docs_orders_by_authority_then_binding(project):
    out = governing_docs(project, "src/worker/main.py")
    assert out["area"] == "worker"
    assert [(d["path"], d["binding"]["kind"]) for d in out["documents"]] == [
        ("docs/architecture/overview.md", "global"),
        ("docs/specs/worker.md", "check"),
    ]
    assert out["documents"][0]["authority_level"] == "architecture"


def test_retractions_conflicts_and_candidates_attach(project):
    decide(project, supersedes=[{"path": "docs/specs/worker.md#Retries", "retraction_summary": "no retries"}])
    c = report_conflict(project, doc_a="docs/architecture/overview.md", doc_b="docs/specs/worker.md#Retries",
                        paths=["src/worker/"], claim="retry count", evidence_a="a", evidence_b="b", provenance=AGENT)
    cand = propose_binding(project, target="worker-contract", reads=["docs/specs/retry.md"],
                           validates_against=["src/worker/"], reason="r", provenance=AGENT)
    out = governing_docs(project, "src/worker/main.py")
    spec = out["documents"][1]
    assert spec["retractions"][0]["retraction_summary"] == "no retries"
    assert [x["id"] for x in spec["open_conflicts"]] == [c["id"]]
    assert [x["id"] for x in out["open_candidates"]] == [cand["id"]]
    assert [x["id"] for x in conflicts(project, path="docs/specs/worker.md")] == [c["id"]]


def test_overlap_hint_for_same_level_docs(tmp_path):
    manifest = MINIMAL_MANIFEST.replace("docs: [docs/architecture/overview.md]",
                                        "docs: [docs/architecture/overview.md, docs/architecture/queue.md]")
    root = make_repo(tmp_path, manifest)
    write(root, "docs/architecture/queue.md", "# Queue\n")
    project = Project.load(root)
    (hint,) = governing_docs(project, "src/worker/main.py")["overlap_hints"]
    assert hint["level"] == "architecture" and len(hint["documents"]) == 2
    decide(project, supersedes=[{"path": "docs/architecture/queue.md", "retraction_summary": "gone"}])
    assert governing_docs(project, "src/worker/main.py")["overlap_hints"] == []


def test_archival_documents_never_govern(tmp_path):
    manifest = MINIMAL_MANIFEST.replace("  index: [AGENTS.md]", "  archival: [docs/architecture/overview.md]\n  index: [AGENTS.md]")
    project = Project.load(make_repo(tmp_path, manifest))
    assert "docs/architecture/overview.md" not in [d["path"] for d in governing_docs(project, "src/worker/main.py")["documents"]]


def test_governing_docs_rejects_escaping_paths(project):
    with pytest.raises(ValueError):
        governing_docs(project, "../etc/passwd")


def test_retractions_follow_path_aliases(project):
    decide(project, supersedes=[{"path": "docs/old.md", "retraction_summary": "wrong"}])
    append_jsonl(project.pending_path, make_record("path_alias", {"old_path": "docs/old.md", "new_path": "docs/new.md"}, AGENT))
    (r,) = retractions_for(project, "docs/new.md")
    assert r["via_alias"] is True and r["retraction_summary"] == "wrong"


def test_decision_lookup(project):
    a = decide(project, topic="a", datetime_="t1")
    b = decide(project, topic="b", datetime_="t2", supersedes_records=[a["id"]])
    got = decision(project, a["id"])
    assert got["status"] == "superseded" and got["superseded_by"] == [b["id"]]
    with pytest.raises(UnknownRecord):
        decision(project, "dec-000000000000")


def test_coverage_reports_holes(project):
    write(project.root, "src/other/x.py", "x = 1\n")
    write(project.root, "docs/specs/orphan.md", "# Orphan\n")
    out = coverage(project)
    assert out["uncovered_sources"] == ["src/other/x.py"]
    assert out["unplaced_docs"] == ["docs/specs/orphan.md"]
    assert out["unbound_sources"] == [] and out["missing_references"] == []
    assert out["holes"] == 2


def test_coverage_without_git(tmp_path):
    project = Project.load(make_repo(tmp_path, commit=False))
    assert coverage(project)["holes"] == 0
