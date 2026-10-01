import asyncio
import json
import sys
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from reasonhold.api import AGENT_TOOLS

pytestmark = pytest.mark.integration
REASONHOLD = str(Path(sys.executable).with_name("reasonhold"))


async def _session(root: Path):
    transport = StdioTransport(command=REASONHOLD, args=["--root", str(root), "mcp"])
    async with Client(transport) as c:
        names = {t.name for t in await c.list_tools()}
        result = await c.call_tool("governing_docs", {"path": "src/worker/main.py"})
    data = getattr(result, "data", None)
    return names, data if data is not None else json.loads(result.content[0].text)


def test_mcp_over_stdio(live_repo):
    names, governing = asyncio.run(_session(live_repo))
    assert names == set(AGENT_TOOLS)
    assert "docs/specs/worker.md" in [d["path"] for d in governing["documents"]]
