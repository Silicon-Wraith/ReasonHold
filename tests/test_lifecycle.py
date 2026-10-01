import re

import pytest

from helpers import FakeClient, FakeCollection, FakeProvider, MINIMAL_MANIFEST, git, make_repo, write
from reasonhold.errors import ModelMismatch, ReasonHoldError
from reasonhold.lifecycle import gc, gc_candidates, index_lock, index_state, run_index
from reasonhold.project import Project
from reasonhold.store import CollectionMeta, read_meta
from reasonhold.writes import store_decision

NAME = re.compile(r"^[A-Z][A-Za-z0-9_]*$")
QUIET = dict(out=lambda *a: None)


@pytest.fixture(autouse=True)
def cache_dir(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path / "repo")


def build(root, client=None, provider=None):
    client = client or FakeClient()
    report = run_index(Project.load(root), client, provider or FakeProvider(), **QUIET)
    return client, report


def test_first_run_is_full_and_records_the_commit(repo):
    client, report = build(repo)
    assert report.full and report.reasons == ["no index for this branch yet"] and report.chunks > 0
    state = index_state(Project.load(repo), client)
    assert state.fresh and state.meta.indexed_commit == git(repo, "rev-parse", "HEAD")
    assert state.meta.last_full_index and state.meta.model_id == "ollama:fake" and state.meta.dims == 4


def test_second_run_is_incremental_and_skips_unchanged_files(repo):
    client, first = build(repo)
    _, second = build(repo, client)
    assert not second.full and second.files_indexed == 0 and second.files_skipped == first.files_indexed


def test_index_state_without_git(tmp_path):
    root = make_repo(tmp_path / "plain", commit=False)
    project = Project.load(root)
    client, report = build(root)
    state = index_state(project, client)
    assert state.branch == "no-git" and NAME.match(state.collection) and state.collection.startswith("RH_")
    assert any("not a git repository" in n for n in state.notes)
    assert state.fresh and report.full


def test_merge_forces_full_rebuild(repo):
    client, _ = build(repo)
    git(repo, "checkout", "-q", "-b", "feat")
    write(repo, "docs/specs/extra.md", "# Extra\n")
    git(repo, "add", "-A"); git(repo, "commit", "-q", "-m", "feat")
    git(repo, "checkout", "-q", "main")
    write(repo, "AGENTS.md", "# Agents v2\n")
    git(repo, "commit", "-qam", "main")
    git(repo, "merge", "-q", "--no-ff", "feat", "-m", "merge")
    state = index_state(Project.load(repo), client)
    assert any("merge commit" in r for r in state.rebuild)
    _, report = build(repo, client)
    assert report.full


def test_history_rewrite_forces_full_rebuild(repo):
    client, _ = build(repo)
    git(repo, "commit", "-q", "--amend", "-m", "rewritten")
    assert any("not an ancestor" in r for r in index_state(Project.load(repo), client).rebuild)


def test_head_moved_is_stale_but_not_a_rebuild(repo):
    client, _ = build(repo)
    write(repo, "AGENTS.md", "# Agents v2\n")
    git(repo, "commit", "-qam", "edit")
    state = index_state(Project.load(repo), client)
    assert state.rebuild == [] and any("HEAD moved" in s for s in state.stale)


def test_new_retraction_forces_full_rebuild(repo):
    client, _ = build(repo)
    project = Project.load(repo)
    store_decision(project, None, FakeProvider(), topic="t", decision="d", rationale="r",
                   supersedes=[{"path": "docs/specs/worker.md", "retraction_summary": "no retries"}],
                   provenance={"kind": "human"})
    assert any("decision log" in r for r in index_state(project, client).rebuild)


def test_authority_change_forces_full_rebuild(repo):
    client, _ = build(repo)
    write(repo, "sync-doc.yaml", MINIMAL_MANIFEST + "authority:\n  - {level: architecture, paths: [\"docs/**\"], weight: 0.1}\n")
    state = index_state(Project.load(repo), client)
    assert any("authority" in r for r in state.rebuild) and any("manifest changed" in s for s in state.stale)


def test_model_guard_blocks_an_incremental_run(repo):
    client, _ = build(repo)
    with pytest.raises(ModelMismatch):
        build(repo, client, FakeProvider(dims=8))


def test_full_run_replaces_a_mismatched_model(repo):
    client, _ = build(repo)
    report = run_index(Project.load(repo), client, FakeProvider(dims=8), full=True, **QUIET)
    assert report.full and read_meta(client, report.collection).dims == 8


def test_dry_run_touches_nothing(repo):
    client = FakeClient()
    report = run_index(Project.load(repo), client, FakeProvider(), dry_run=True, **QUIET)
    assert report.dry_run and report.chunks > 0 and client.created == []


def test_single_collection_mode_answers_from_the_default_branch(tmp_path):
    root = make_repo(tmp_path / "r", MINIMAL_MANIFEST + "project:\n  index: {branch_isolation: false}\n")
    client, _ = build(root)
    git(root, "checkout", "-q", "-b", "feat")
    project = Project.load(root)
    state = index_state(project, client)
    assert state.indexed_branch == "main" and state.collection == "RH_R__main"
    assert any("single-collection" in n for n in state.notes)
    report = run_index(project, client, FakeProvider(), **QUIET)
    assert report.chunks == 0 and "single-collection" in report.warnings[0]


def test_index_lock_refuses_a_concurrent_run(tmp_path):
    with index_lock("RH_X__main", lock_dir=tmp_path):
        with pytest.raises(ReasonHoldError, match="another"):
            with index_lock("RH_X__main", lock_dir=tmp_path):
                pass
    with index_lock("RH_X__main", lock_dir=tmp_path):
        pass


def meta_collection(name, project, branch):
    return FakeCollection(name, CollectionMeta(project, branch, "ollama:fake", 4).to_description())


def test_gc_drops_only_this_projects_deleted_branches(repo):
    client = FakeClient(
        meta_collection("RH_Repo__main", "repo", "main"),
        meta_collection("RH_Repo__gone", "repo", "gone"),
        meta_collection("RH_Repo__detached_abc_12345678", "repo", "detached-abc"),
        meta_collection("RH_Other__gone", "other", "gone"),
        FakeCollection("RH_Repo__nometa"),
        FakeCollection("AriadneDoc"),
    )
    project = Project.load(repo)
    assert gc_candidates(project, client) == ["RH_Repo__gone"]
    assert gc(project, client, confirm=lambda prompt: "n", **QUIET) == []
    assert gc(project, client, yes=True, **QUIET) == ["RH_Repo__gone"]
    assert client.deleted == ["RH_Repo__gone"]
