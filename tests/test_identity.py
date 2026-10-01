import re
import subprocess

import pytest

from reasonhold.identity import (
    NO_GIT_BRANCH,
    changed_since,
    collection_name,
    current_branch,
    head_commit,
    is_ancestor,
    local_branches,
    merges_between,
)

NAME = re.compile(r"^[A-Z][A-Za-z0-9_]*$")


def run(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, stdin=subprocess.DEVNULL)


@pytest.fixture
def repo(tmp_path):
    run(tmp_path, "init", "-q", "-b", "main")
    run(tmp_path, "config", "user.email", "t@example.com")
    run(tmp_path, "config", "user.name", "t")
    (tmp_path / "a.md").write_text("one\n")
    run(tmp_path, "add", "a.md")
    run(tmp_path, "commit", "-q", "-m", "one")
    return tmp_path


def test_branch_and_head(repo):
    assert current_branch(repo) == "main"
    assert len(head_commit(repo)) == 40


def test_detached_head(repo):
    run(repo, "checkout", "-q", "--detach")
    assert current_branch(repo).startswith("detached-")


def test_non_git_directory_uses_no_git_branch(tmp_path):
    assert current_branch(tmp_path) == NO_GIT_BRANCH
    assert head_commit(tmp_path) is None


def test_merges_and_ancestry(repo):
    base = head_commit(repo)
    run(repo, "checkout", "-q", "-b", "feat")
    (repo / "b.md").write_text("b\n")
    run(repo, "add", "b.md")
    run(repo, "commit", "-q", "-m", "b")
    run(repo, "checkout", "-q", "main")
    (repo / "c.md").write_text("c\n")
    run(repo, "add", "c.md")
    run(repo, "commit", "-q", "-m", "c")
    run(repo, "merge", "-q", "--no-ff", "feat", "-m", "merge feat")
    assert merges_between(repo, base, head_commit(repo))
    assert is_ancestor(repo, base, head_commit(repo))
    assert not is_ancestor(repo, head_commit(repo), base)
    assert local_branches(repo) == {"main", "feat"}


def test_changed_since(repo):
    base = head_commit(repo)
    assert not changed_since(repo, base, "a.md")
    (repo / "a.md").write_text("two\n")
    assert changed_since(repo, base, "a.md")


@pytest.mark.parametrize("branch", ["main", "feat/a-b", "feat/a_b", "Feat/A.b", "ünïcode", "x" * 300, "detached-abc1234"])
def test_collection_names_are_valid(branch):
    name = collection_name("ariadne", branch)
    assert NAME.match(name) and name.startswith("RH_Ariadne__") and len(name) <= 100


def test_collection_names_are_valid_and_distinct():
    names = {collection_name("ariadne", b) for b in ["feat/a-b", "feat/a_b", "feat-a-b", "Feat/A-B", "main"]}
    assert len(names) == 5
    assert collection_name("ariadne", "main") == "RH_Ariadne__main"
    assert NAME.match(collection_name("9lives", "main"))
