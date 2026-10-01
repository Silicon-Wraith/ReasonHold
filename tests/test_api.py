import pytest

from helpers import FakeClient, FakeProvider, MINIMAL_MANIFEST, git, make_repo, write
from reasonhold.api import ReasonHold
from reasonhold.errors import IndexMissing, IndexStale, ModelMismatch, StoreUnavailable

QUIET = lambda *a: None  # noqa: E731
HUMAN = {"kind": "human"}


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


def rh_for(root, client=None, provider=None):
    client = client or FakeClient()
    return ReasonHold(root, connect=lambda: client, provider=provider or FakeProvider()), client


def test_queries_never_index_and_name_the_fix(tmp_path):
    rh, client = rh_for(make_repo(tmp_path / "r"))
    with pytest.raises(IndexMissing, match="reasonhold index"):
        rh.search_docs("anything")
    assert client.created == []


def test_index_then_freshness_is_clean(tmp_path):
    rh, _ = rh_for(make_repo(tmp_path / "r"))
    assert rh.index(out=QUIET)["full"] is True
    fresh = rh.freshness()
    assert fresh["clean"] is True and fresh["index"]["fresh"] is True


def test_model_guard_applies_to_queries(tmp_path):
    root = make_repo(tmp_path / "r")
    rh, client = rh_for(root)
    rh.index(out=QUIET)
    other, _ = rh_for(root, client, FakeProvider(dims=8))
    with pytest.raises(ModelMismatch):
        other.search_docs("q")


def test_empty_symbol_answer_on_stale_index_is_refused(tmp_path, monkeypatch):
    root = make_repo(tmp_path / "r")
    rh, _ = rh_for(root)
    rh.index(out=QUIET)
    monkeypatch.setattr("reasonhold.codeindex.query_chunks", lambda *a, **k: [])
    assert rh.symbols("python_function")["results"] == []
    write(root, "AGENTS.md", "# changed\n")
    git(root, "commit", "-qam", "change")
    with pytest.raises(IndexStale):
        rh.symbols("python_function")


def test_store_decision_keeps_the_retraction_hash_in_step(tmp_path):
    rh, _ = rh_for(make_repo(tmp_path / "r"))
    rh.index(out=QUIET)
    out = rh.store_decision(topic="t", decision="d", rationale="r", provenance=HUMAN,
                            supersedes=[{"path": "docs/specs/worker.md", "retraction_summary": "no"}])
    assert out["indexed"] and rh.state().rebuild == []


def test_store_decision_with_weaviate_down_still_appends(tmp_path):
    root = make_repo(tmp_path / "r")

    def down():
        raise StoreUnavailable("cannot reach Weaviate at localhost:8081")

    rh = ReasonHold(root, connect=down, provider=FakeProvider())
    out = rh.store_decision(topic="t", decision="d", rationale="r", provenance=HUMAN)
    assert out["indexed"] is False and any("localhost:8081" in w for w in out["warnings"])
    assert (root / "decisions.jsonl").read_text().count("\n") == 1


def test_single_collection_feature_branch_does_not_write_to_the_default_index(tmp_path):
    root = make_repo(tmp_path / "r", MINIMAL_MANIFEST + "project:\n  index: {branch_isolation: false}\n")
    rh, client = rh_for(root)
    rh.index(out=QUIET)
    before = len(client.store["RH_R__main"].objects)
    git(root, "checkout", "-q", "-b", "feat")
    out = rh.store_decision(topic="t", decision="d", rationale="r", provenance=HUMAN)
    assert out["indexed"] is False and len(client.store["RH_R__main"].objects) == before


def test_curate_and_preamble_through_the_facade(tmp_path):
    root = make_repo(tmp_path / "r")
    rh, _ = rh_for(root)
    assert rh.curate()["edits"] == [] and rh.curate()["warnings"]
    rh.index(out=QUIET)
    git(root, "mv", "docs/specs/worker.md", "docs/specs/w2.md")
    assert [e["old_path"] for e in rh.curate(dry_run=True)["edits"]] == ["docs/specs/worker.md"]
    assert "fresh" in rh.preamble() or "stale" in rh.preamble()
