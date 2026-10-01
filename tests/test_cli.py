import io
import json
import os
import subprocess
import sys

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


def test_json_index_output_is_parseable(tmp_path, cli):
    root = make_repo(tmp_path / "r")
    code, out, _ = cli("--root", str(root), "--json", "index")
    assert code == 0 and "full" in json.loads(out)


def test_init_with_unusable_directory_name_exits_2(tmp_path, cli):
    bad = tmp_path / "___"
    bad.mkdir()
    code, _, err = cli("--root", str(bad), "init")
    assert code == 2 and err.startswith("reasonhold:")


def test_init_attributes_top_level_files_and_references_nothing_missing(tmp_path, cli):
    write(tmp_path, "pkg/top.py", "x = 1\n")
    write(tmp_path, "pkg/sub/deep.py", "y = 2\n")
    assert cli("--root", str(tmp_path), "init")[0] == 0
    manifest = Project.load(tmp_path).manifest
    assert manifest.infer_area("pkg/top.py") == "pkg" and manifest.infer_area("pkg/sub/deep.py") == "pkg"
    assert manifest.areas[0].docs == ("reasonhold.yaml",)  # no docs or guidance files: the manifest anchors
    code, out, _ = cli("--root", str(tmp_path), "--json", "check")
    assert code == 0 and not [p for p in json.loads(out) if "missing" in p["message"] or "not found" in p["message"]]
    code, out, _ = cli("--root", str(tmp_path), "--json", "coverage")
    result = json.loads(out)
    assert code == 0 and result["missing_references"] == [] and result["holes"] == 0


def test_index_has_no_area_option(tmp_path, cli, capsys):
    with pytest.raises(SystemExit):
        cli("--root", str(tmp_path), "index", "--area", "x")


def test_decide_stdin_rejects_unknown_and_missing_fields_with_exit_2(tmp_path, cli, monkeypatch):
    root = make_repo(tmp_path / "r")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"topic": "t", "decision": "d", "rationale": "r", "bogus": 1})))
    code, _, err = cli("--root", str(root), "decide", "--stdin")
    assert code == 2 and err.startswith("reasonhold:") and "bogus" in err
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"topic": "t"})))
    code, _, err = cli("--root", str(root), "decide", "--stdin")
    assert code == 2 and err.startswith("reasonhold:") and "decision" in err and "rationale" in err


def test_index_exits_1_on_an_incomplete_index_warning(tmp_path, monkeypatch, capsys):
    class Fake:
        def __init__(self, root): pass
        def close(self): pass
        def index(self, **kw):
            return {"warnings": ["reported 3 chunks but the collection holds 2; the index is incomplete, re-run with --full"]}

    assert main(["--root", str(tmp_path), "index"], factory=Fake) == 1

    class Clean(Fake):
        def index(self, **kw):
            return {"warnings": ["a.py: skipped (ValueError: x)"]}

    assert main(["--root", str(tmp_path), "index"], factory=Clean) == 0


def test_mcp_without_a_manifest_exits_2_with_one_line(tmp_path, capsys):
    assert main(["--root", str(tmp_path), "mcp"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("reasonhold:") and len(err.strip().splitlines()) == 1


@pytest.mark.parametrize("argv", [["check"], ["preamble", "--format", "claude-hook"]])
def test_console_commands_print_no_authlib_deprecation_warning(tmp_path, argv):
    pytest.importorskip("authlib")
    make_repo(tmp_path / "r")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONWARNINGS"}
    env["XDG_CACHE_HOME"] = str(tmp_path / "cache")
    code = "import sys; from reasonhold.cli import main; sys.exit(main(sys.argv[1:]))"
    done = subprocess.run([sys.executable, "-c", code, "--root", str(tmp_path / "r"), *argv],
                          capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
    assert "AuthlibDeprecationWarning" not in done.stderr


def test_mcp_read_only_flag_reaches_the_server(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr("reasonhold.mcp_server.serve",
                        lambda root, read_only=False: seen.update(root=root, read_only=read_only))
    assert main(["--root", str(tmp_path), "mcp", "--read-only"]) == 0
    assert seen == {"root": tmp_path.resolve(), "read_only": True}
    assert main(["--root", str(tmp_path), "mcp"]) == 0
    assert seen["read_only"] is False
    other = tmp_path / "other"
    assert main(["mcp", "--root", str(other), "--read-only"]) == 0
    assert seen == {"root": other.resolve(), "read_only": True}
