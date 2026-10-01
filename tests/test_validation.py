import json
from pathlib import Path

from helpers import make_repo, write
from reasonhold.project import Project
from reasonhold.validation import check

REPO_ROOT = Path(__file__).resolve().parents[1]


def messages(problems, severity=None):
    return [p.message for p in problems if severity is None or p.severity == severity]


def test_clean_repo_has_no_problems(tmp_path):
    make_repo(tmp_path, commit=False)
    assert check(Project.load(tmp_path)) == []


def test_check_reports_missing_referenced_files(tmp_path):
    make_repo(tmp_path, commit=False)
    (tmp_path / "docs/specs/worker.md").unlink()
    problems = check(Project.load(tmp_path))
    warnings = messages(problems, "warning")
    assert any("docs/specs/worker.md" in m for m in warnings)
    assert sum("docs/specs/worker.md" in m for m in warnings) == 2   # areas.worker.docs and checks.worker-contract.reads


def test_check_reports_bad_decision_lines_with_line_numbers(tmp_path):
    make_repo(tmp_path, commit=False)
    good = {"topic": "a", "decision": "d", "rationale": "r", "datetime": "t1"}
    (tmp_path / "decisions.jsonl").write_text(
        json.dumps(good) + "\nnot json\n" + json.dumps({"topic": "b"}) + "\n"
        + json.dumps({**good, "topic": "c", "datetime": "t2", "supersedes_records": ["dec-000000000000"]}) + "\n"
        + json.dumps(good) + "\n"
    )
    problems = [p for p in check(Project.load(tmp_path)) if p.file == "decisions.jsonl"]
    assert sorted({p.line for p in problems if p.severity == "error"}) == [2, 3, 4, 5]
    assert any("duplicate id" in p.message for p in problems)


def test_check_reports_undefined_check_names(tmp_path):
    make_repo(tmp_path, commit=False)
    text = (tmp_path / "sync-doc.yaml").read_text().replace("checks: [worker-contract]", "checks: [nope]")
    write(tmp_path, "sync-doc.yaml", text)
    assert any("nope" in m for m in messages(check(Project.load(tmp_path))))


def test_this_repository_validates():
    """ReasonHold's own decision log (Auctor's 8 records plus 10) must pass its own check."""
    problems = [p for p in check(Project.load(REPO_ROOT)) if p.file == "decisions.jsonl" and p.severity == "error"]
    assert problems == []
