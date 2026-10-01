"""Git facts about the checkout, and the collection name derived from them."""

from __future__ import annotations

import hashlib
import re
import subprocess
import unicodedata
from pathlib import Path

NO_GIT_BRANCH = "no-git"
MAX_NAME = 100


def git(root: Path, *args: str, timeout: float = 5.0) -> str | None:
    try:
        done = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def head_commit(root: Path) -> str | None:
    return git(root, "rev-parse", "--verify", "-q", "HEAD")


def current_branch(root: Path) -> str:
    branch = git(root, "symbolic-ref", "--short", "-q", "HEAD")
    if branch:
        return branch
    head = git(root, "rev-parse", "--short", "--verify", "-q", "HEAD")
    return f"detached-{head}" if head else NO_GIT_BRANCH


def is_ancestor(root: Path, older: str, newer: str) -> bool:
    try:
        done = subprocess.run(
            ["git", "merge-base", "--is-ancestor", older, newer],
            cwd=root, capture_output=True, timeout=5.0, stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


def merges_between(root: Path, older: str, newer: str) -> list[str]:
    out = git(root, "rev-list", "--merges", f"{older}..{newer}")
    return out.split() if out else []


def changed_since(root: Path, older: str, rel_path: str) -> bool:
    try:
        done = subprocess.run(
            ["git", "diff", "--quiet", older, "--", rel_path],
            cwd=root, capture_output=True, timeout=5.0, stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return True
    return done.returncode != 0


def local_branches(root: Path) -> set[str]:
    out = git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    return set(out.split()) if out else set()


def default_branch(root: Path) -> str:
    ref = git(root, "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD")
    if ref and "/" in ref:
        return ref.split("/", 1)[1]
    branches = local_branches(root)
    return "main" if "main" in branches else current_branch(root)


def _sanitize(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9_]", "_", ascii_value)).strip("_")


def collection_name(project_id: str, branch: str) -> str:
    project = _sanitize(project_id) or "P"
    project = project[0].upper() + project[1:]
    if not project[0].isalpha():
        project = "P" + project
    slug = _sanitize(branch) or "branch"
    lossy = slug != branch
    name = f"RH_{project}__{slug}"
    if lossy or len(name) > MAX_NAME:
        digest = hashlib.sha256(branch.encode()).hexdigest()[:8]
        name = f"{name[: MAX_NAME - 9]}_{digest}"
    return name
