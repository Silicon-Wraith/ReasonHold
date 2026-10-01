import io
import json

import pytest

from helpers import FakeClient, FakeProvider, make_repo, write
from reasonhold.api import ReasonHold
from reasonhold.cli import main
from reasonhold.project import Project


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


@pytest.fixture
def cli(tmp_path, capsys):
    client = FakeClient()

    def factory(root):
        return ReasonHold(root, connect=lambda: client, provider=FakeProvider())

    def run(*argv):
        code = main(list(argv), factory=factory)
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return run


def test_init_scaffolds_a_loadable_manifest(tmp_path, cli):
    write(tmp_path, "README.md", "# R\n")
    write(tmp_path, "docs/specs/a.md", "# A\n")
    write(tmp_path, "pkg/x.py", "x = 1\n")
    code, out, _ = cli("--root", str(tmp_path), "init")
    assert code == 0 and (tmp_path / "reasonhold.yaml").exists()
    project = Project.load(tmp_path)
    assert [a.name for a in project.manifest.areas] == ["pkg"]
    assert (tmp_path / "decisions.jsonl").exists()
    assert cli("--root", str(tmp_path), "init")[0] == 2


def test_check_and_coverage_exit_codes(tmp_path, cli):
    root = make_repo(tmp_path / "r")
    assert cli("--root", str(root), "check")[0] == 0
    assert cli("--root", str(root), "coverage")[0] == 0
    write(root, "src/other/x.py", "x = 1\n")
    code, out, _ = cli("--root", str(root), "coverage")
    assert code == 1 and "src/other/x.py" in out


def test_errors_exit_2_with_the_fix_on_stderr(tmp_path, cli):
    root = make_repo(tmp_path / "r")
    code, _, err = cli("--root", str(root), "search", "anything")
    assert code == 2 and "reasonhold index" in err


def test_index_decide_show_and_govern(tmp_path, cli):
    root = make_repo(tmp_path / "r")
    assert cli("--root", str(root), "index")[0] == 0
    code, out, _ = cli("--root", str(root), "--json", "decide", "--topic", "queue", "--decision", "FIFO",
                       "--rationale", "r", "--supersede", "docs/specs/worker.md#Retries=no retries")
    record = json.loads(out)["record"]
    assert code == 0 and record["supersedes"][0]["path"] == "docs/specs/worker.md#Retries"
    code, out, _ = cli("--root", str(root), "--json", "decisions", "show", record["id"])
    assert json.loads(out)["status"] == "active"
    code, out, _ = cli("--root", str(root), "govern", "src/worker/main.py")
    assert code == 0 and "docs/specs/worker.md" in out and "no retries" in out


def test_decide_from_stdin(tmp_path, cli, monkeypatch):
    root = make_repo(tmp_path / "r")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"topic": "t", "decision": "d", "rationale": "r"})))
    code, out, _ = cli("--root", str(root), "--json", "decide", "--stdin")
    assert code == 0 and json.loads(out)["record"]["provenance"]["kind"] == "human"


def test_candidates_list_promote_reject(tmp_path, cli):
    from reasonhold.writes import propose_binding

    root = make_repo(tmp_path / "r")
    project = Project.load(root)
    a = propose_binding(project, target="worker-contract", reads=["AGENTS.md"], validates_against=["src/worker/"],
                        reason="r", provenance={"kind": "agent"})
    b = propose_binding(project, target="worker-contract", reads=["README.md"], validates_against=["src/worker/"],
                        reason="r", provenance={"kind": "agent"})
    code, out, _ = cli("--root", str(root), "candidates")
    assert code == 0 and a["id"] in out and b["id"] in out
    assert cli("--root", str(root), "candidates", "promote", a["id"])[0] == 0
    assert cli("--root", str(root), "candidates", "reject", b["id"], "--note", "no")[0] == 0
    assert cli("--root", str(root), "candidates", "promote", a["id"])[0] == 2


def test_preamble_always_exits_zero(tmp_path, cli):
    code, out, _ = cli("--root", str(tmp_path), "preamble", "--format", "claude-hook")
    assert code == 0 and json.loads(out)["hookSpecificOutput"]["hookEventName"] == "SessionStart"
