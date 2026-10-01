import asyncio
import json

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from helpers import FakeClient, FakeProvider, make_repo
from reasonhold.api import AGENT_TOOLS, ReasonHold
from reasonhold.mcp_server import build_server, instructions


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


@pytest.fixture
def server(tmp_path):
    client = FakeClient()
    rh = ReasonHold(make_repo(tmp_path / "r"), connect=lambda: client, provider=FakeProvider())
    return build_server(rh), rh


def run(coro):
    return asyncio.run(coro)


async def _names(server):
    async with Client(server) as c:
        return {t.name for t in await c.list_tools()}


async def _call(server, name, args):
    async with Client(server) as c:
        result = await c.call_tool(name, args)
    data = getattr(result, "data", None)
    return data if data is not None else json.loads(result.content[0].text)


def test_tool_set_matches_the_spec(server):
    names = run(_names(server[0]))
    assert names == set(AGENT_TOOLS)
    assert not names & {"promote", "reject", "index", "curate", "gc", "resolve"}


def test_instructions_name_the_project(server):
    text = instructions(server[1].project)
    assert "r" in text and "retraction" in text and "bypasses" in text


def test_governing_docs_over_mcp(server):
    out = run(_call(server[0], "governing_docs", {"path": "src/worker/main.py"}))
    assert [d["path"] for d in out["documents"]][-1] == "docs/specs/worker.md"


def test_store_decision_over_mcp_records_agent_provenance(server):
    srv, rh = server
    out = run(_call(srv, "store_decision", {"topic": "t", "decision": "d", "rationale": "r"}))
    assert out["record"]["provenance"] == {"kind": "agent", "actor": "mcp"}
    with pytest.raises(ToolError):
        run(_call(srv, "store_decision", {"topic": "t2", "decision": "d", "rationale": "r",
                                          "provenance": {"kind": "human"}}))
    assert rh.project.decisions_path.read_text().count("\n") == 1


def test_errors_reach_the_agent_with_the_fix(server):
    with pytest.raises(ToolError, match="reasonhold index"):
        run(_call(server[0], "search_docs", {"query": "anything"}))
