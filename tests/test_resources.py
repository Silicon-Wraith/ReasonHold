import json
import re
from importlib import resources
from pathlib import Path

import pytest

RES = resources.files("reasonhold").joinpath("resources")
SKILLS = ["session-bootstrap", "record-decision", "consult-before-design", "propose-and-report", "reindex"]
README = Path(__file__).resolve().parents[1] / "README.md"


@pytest.mark.parametrize("name", SKILLS)
def test_skill_has_frontmatter_and_stays_short(name):
    text = RES.joinpath(f"skills/{name}/SKILL.md").read_text()
    match = re.match(r"^---\nname: (.+)\ndescription: (.+)\n---\n", text)
    assert match and match.group(1) == name and len(match.group(2)) > 20
    assert len(text.splitlines()) <= 60


def test_only_the_proposal_skill_mentions_promotion_and_only_as_a_human_step():
    for name in SKILLS:
        text = RES.joinpath(f"skills/{name}/SKILL.md").read_text()
        if name == "propose-and-report":
            assert "Agents cannot promote" in text
        else:
            assert "promote" not in text


def test_claude_hook_recipe():
    data = json.loads(RES.joinpath("hooks/claude-settings.json").read_text())
    (entry,) = data["hooks"]["SessionStart"]
    (hook,) = entry["hooks"]
    assert hook["command"].startswith("reasonhold preamble --format claude-hook") and hook["timeout"] == 20
    assert "jq" not in hook["command"]


def test_post_merge_hook_runs_in_the_background_and_fails_open():
    text = RES.joinpath("hooks/post-merge").read_text()
    assert text.startswith("#!/bin/sh") and "reasonhold index" in text and "&" in text and text.rstrip().endswith("exit 0")


def test_mcp_entry():
    data = json.loads(RES.joinpath("mcp.json").read_text())
    assert data["mcpServers"]["reasonhold"] == {"command": "reasonhold", "args": ["mcp"]}


def test_readme_states_the_limits():
    text = README.read_text()
    assert "bypasses the retraction overlay" in text
    assert "unverified" in text  # Codex and other CLIs until verified (R-20)


def test_no_em_dashes_in_user_facing_text():
    texts = [README.read_text(), RES.joinpath("agents-snippet.md").read_text()]
    texts += [RES.joinpath(f"skills/{n}/SKILL.md").read_text() for n in SKILLS]
    assert all("—" not in t for t in texts)
