import json
from types import SimpleNamespace

import pytest

pytest.importorskip("agno")

from agno.knowledge.protocol import KnowledgeProtocol  # noqa: E402

from helpers import FakeClient, FakeProvider, make_repo  # noqa: E402
from reasonhold.agno import ReasonHoldKnowledge, ReasonHoldTools, reasonhold_context, render_context  # noqa: E402
from reasonhold.api import AGENT_TOOLS, ReasonHold  # noqa: E402


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


@pytest.fixture
def rh(tmp_path):
    client = FakeClient()
    return ReasonHold(make_repo(tmp_path / "r"), connect=lambda: client, provider=FakeProvider())


def test_toolkit_exposes_exactly_the_agent_tools(rh):
    tools = ReasonHoldTools(rh)
    assert set(tools.get_functions()) == set(AGENT_TOOLS)


def test_toolkit_store_decision_signs_as_an_agent(rh):
    out = json.loads(ReasonHoldTools(rh).store_decision(topic="t", decision="d", rationale="r"))
    assert out["record"]["provenance"] == {"kind": "agent", "actor": "agno"}


def test_toolkit_errors_are_returned_not_raised(rh):
    out = json.loads(ReasonHoldTools(rh).search_docs("anything"))
    assert "reasonhold index" in out["error"]


def test_knowledge_satisfies_the_protocol_and_carries_retractions(rh, monkeypatch):
    knowledge = ReasonHoldKnowledge(rh)
    assert isinstance(knowledge, KnowledgeProtocol)
    hits = [{"content": "c", "file_path": "docs/x.md", "authority_level": "architecture",
             "retraction_summary": "now LIFO", "kind": "document"}]
    monkeypatch.setattr(rh, "search_docs", lambda q, k: {"index": {}, "results": hits})
    (doc,) = knowledge.retrieve("queue")
    assert doc.name == "docs/x.md" and doc.meta_data["retraction_summary"] == "now LIFO"
    assert "retraction_summary" in knowledge.build_context()


def test_context_hook_prepends_preamble_and_governing_docs(rh):
    hook = reasonhold_context(["src/worker/main.py"], rh=rh)
    run_input = SimpleNamespace(input_content="Fix the retry bug.")
    hook(run_input=run_input, agent=None)
    assert run_input.input_content.endswith("Fix the retry bug.")
    assert "docs/specs/worker.md" in run_input.input_content


def test_render_context_fails_open(rh, monkeypatch):
    def boom(path):
        raise RuntimeError("no")

    monkeypatch.setattr(rh, "governing_docs", boom)
    assert "unavailable" in render_context(rh, ["src/worker/main.py"])
