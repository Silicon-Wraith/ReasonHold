import pytest

from helpers import FakeProvider, git, write
from reasonhold.api import ReasonHold
from reasonhold.errors import ModelMismatch

pytestmark = pytest.mark.integration
QUIET = lambda *a: None  # noqa: E731


def test_index_search_retract_and_guard(live_repo):
    with ReasonHold(live_repo) as rh:
        report = rh.index(out=QUIET)
        assert report["full"] and report["chunks"] > 0 and not report["warnings"]
        assert rh.state().collection.startswith("RH_Test_")
        hits = rh.search_docs("how many times does the worker retry")["results"]
        assert hits[0]["file_path"] == "docs/specs/worker.md"
        rh.store_decision(topic="no-retries", decision="The worker does not retry.", rationale="idempotency",
                          supersedes=[{"path": "docs/specs/worker.md#Retries", "retraction_summary": "no retries"}],
                          provenance={"kind": "human"})
        hits = rh.search_docs("how many times does the worker retry")["results"]
        assert any(h.get("retraction_summary") == "no retries" for h in hits)
        decisions = rh.search_decisions("worker retries")["results"]
        assert decisions[0]["status"] == "active" and decisions[0]["id"].startswith("dec-")
        assert rh.state().rebuild == []
    with ReasonHold(live_repo, provider=FakeProvider(dims=8)) as other:
        with pytest.raises(ModelMismatch):
            other.search_docs("anything")


def test_merge_triggers_full_reindex(live_repo):
    with ReasonHold(live_repo) as rh:
        rh.index(out=QUIET)
        git(live_repo, "checkout", "-q", "-b", "feat")
        write(live_repo, "docs/specs/extra.md", "# Extra\n")
        git(live_repo, "add", "-A"); git(live_repo, "commit", "-qm", "feat")
        git(live_repo, "checkout", "-q", "main")
        write(live_repo, "AGENTS.md", "# Agents v2\n")
        git(live_repo, "commit", "-qam", "main")
        git(live_repo, "merge", "-q", "--no-ff", "feat", "-m", "merge")
        report = rh.index(out=QUIET)
        assert report["full"] and any("merge" in r for r in report["reasons"])


def test_gc_drops_a_deleted_branch(live_repo):
    with ReasonHold(live_repo) as rh:
        rh.index(out=QUIET)
        git(live_repo, "checkout", "-q", "-b", "temp")
        rh.index(out=QUIET)
        temp = rh.state().collection
        git(live_repo, "checkout", "-q", "main")
        git(live_repo, "branch", "-q", "-D", "temp")
        assert rh.gc(yes=True, out=QUIET) == [temp]
        assert not rh.client.collections.exists(temp)
