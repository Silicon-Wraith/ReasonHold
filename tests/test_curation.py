import pytest

from helpers import FakeClient, FakeProvider, MINIMAL_MANIFEST, git, make_repo, write
from reasonhold.curation import curate, promote, reject
from reasonhold.errors import UnknownRecord
from reasonhold.lifecycle import run_index
from reasonhold.pending import PendingLog
from reasonhold.project import Project
from reasonhold.writes import propose_binding

AGENT, HUMAN = {"kind": "agent"}, {"kind": "human"}
COMMENTED = "# Placement is declared, never inferred.\n" + MINIMAL_MANIFEST.replace(
    "docs: [docs/specs/worker.md]", "docs: [docs/specs/worker.md, docs/specs/extra.md]")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    root = tmp_path / "repo"
    root.mkdir()
    write(root, "docs/specs/extra.md", "# Extra\n")
    return make_repo(root, COMMENTED)


def test_rename_updates_every_reference_keeps_comments_and_records_an_alias(repo):
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "mv", "docs/specs/worker.md", "docs/specs/worker-v2.md")
    (edit,) = curate(Project.load(repo), since=base, dry_run=False)
    assert edit.cause == "rename" and sorted(edit.locations) == ["areas.worker.docs", "checks.worker-contract.reads"]
    text = (repo / "sync-doc.yaml").read_text()
    assert "docs/specs/worker.md" not in text and text.count("docs/specs/worker-v2.md") == 2
    assert text.startswith("# Placement is declared, never inferred.")
    log = PendingLog.load(Project.load(repo).pending_path)
    assert log.aliases() == {"docs/specs/worker.md": "docs/specs/worker-v2.md"}
    assert [r["kind"] for r in log.records] == ["path_alias", "curation"]
    assert curate(Project.load(repo), since=base, dry_run=False) == []
    assert len(PendingLog.load(Project.load(repo).pending_path).records) == 2


def test_dry_run_changes_nothing(repo):
    base = git(repo, "rev-parse", "HEAD")
    before = (repo / "sync-doc.yaml").read_text()
    git(repo, "mv", "docs/specs/worker.md", "docs/specs/worker-v2.md")
    assert len(curate(Project.load(repo), since=base, dry_run=True)) == 1
    assert (repo / "sync-doc.yaml").read_text() == before and not Project.load(repo).pending_path.exists()


def test_deletion_removes_entries_but_never_empties_a_list(repo):
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "rm", "-q", "docs/specs/extra.md", "docs/specs/worker.md")
    edits = {e.old_path: e for e in curate(Project.load(repo), since=base, dry_run=False)}
    assert edits["docs/specs/extra.md"].locations == ["areas.worker.docs"]
    assert edits["docs/specs/worker.md"].kept == ["areas.worker.docs", "checks.worker-contract.reads"]
    Project.load(repo)  # the manifest still loads: no list became empty


def test_curate_needs_a_base_commit(repo):
    assert curate(Project.load(repo), since=None, dry_run=False) == []


def test_promote_into_an_existing_check_and_into_a_new_check(repo):
    project = Project.load(repo)
    a = propose_binding(project, target="worker-contract", reads=["docs/specs/extra.md"],
                        validates_against=["src/worker/"], reason="r", provenance=AGENT)
    b = propose_binding(project, target="queue-contract", reads=["docs/architecture/overview.md"],
                        validates_against=["src/queue/"], reason="queue spec", provenance=AGENT)
    assert promote(project, a["id"], provenance=HUMAN)["created"] is False
    assert promote(project, b["id"], provenance=HUMAN)["created"] is True
    project = Project.load(repo)
    assert "docs/specs/extra.md" in project.manifest.check("worker-contract").reads
    assert project.manifest.check("queue-contract").validates_against == ("src/queue/",)
    assert PendingLog.load(project.pending_path).open() == []
    with pytest.raises(UnknownRecord):
        promote(project, a["id"], provenance=HUMAN)


def test_promote_into_an_area_and_reject(repo):
    project = Project.load(repo)
    a = propose_binding(project, target="worker", reads=["docs/architecture/overview.md"],
                        validates_against=["src/worker/"], reason="r", provenance=AGENT)
    b = propose_binding(project, target="worker", reads=["docs/specs/extra.md"],
                        validates_against=["src/worker/"], reason="r2", provenance=AGENT)
    promote(project, a["id"], provenance=HUMAN)
    reject(project, b["id"], note="duplicate", provenance=HUMAN)
    project = Project.load(repo)
    assert "docs/architecture/overview.md" in [d for a_ in project.manifest.areas if a_.name == "worker" for d in a_.docs]
    assert PendingLog.load(project.pending_path).resolution_for(b["id"])["outcome"] == "rejected"


def test_run_index_curates_first(repo):
    client = FakeClient()
    run_index(Project.load(repo), client, FakeProvider(), out=lambda *a: None)
    git(repo, "mv", "docs/specs/worker.md", "docs/specs/worker-v2.md")
    git(repo, "commit", "-qm", "rename")
    report = run_index(Project.load(repo), client, FakeProvider(), out=lambda *a: None)
    assert [c["old_path"] for c in report.curation] == ["docs/specs/worker.md"]
    assert "docs/specs/worker-v2.md" in (repo / "sync-doc.yaml").read_text()
