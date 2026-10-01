"""Install the packaged skill pack into a repository's .claude/skills/.

Each installed skill directory carries MARKER, so a later install replaces only
directories ReasonHold put there; any other directory with a packaged skill's
name stops the install before anything is written, and a marked directory the
pack no longer ships is removed. STAMP records the package version that
installed the pack, and the preamble compares it with the running package.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from reasonhold import __version__
from reasonhold.errors import SkillsConflict, SkillsInstallFailed

STAMP = ".reasonhold-version"
MARKER = ".reasonhold-skill"


def packaged_skills() -> list[Path]:
    base = Path(__file__).parent / "resources" / "skills"
    return sorted(p for p in base.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())


def skills_dir(root: Path | str) -> Path:
    return Path(root) / ".claude" / "skills"


def install(root: Path | str) -> dict:
    target = skills_dir(root)
    skills = packaged_skills()
    # is_symlink catches broken links, which exists() reports as absent.
    foreign = [s.name for s in skills if ((target / s.name).is_symlink() or (target / s.name).exists())
               and not _owned(target / s.name)]
    if foreign:
        listed = ", ".join(f".claude/skills/{n}" for n in foreign)
        raise SkillsConflict(f"refusing to overwrite {listed}: ReasonHold did not install it; "
                             "move or rename it, then run `reasonhold skills install` again")
    try:
        return _write(target, skills)
    except OSError as exc:
        raise SkillsInstallFailed(f"could not install the skill pack into {target}: {exc}") from exc


def _write(target: Path, skills: list[Path]) -> dict:
    target.mkdir(parents=True, exist_ok=True)
    for skill in skills:
        dest = target / skill.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(skill, dest, ignore=shutil.ignore_patterns("__pycache__"))
        (dest / MARKER).write_text(f"{__version__}\n")
    (target / STAMP).write_text(f"{__version__}\n")
    current = {s.name for s in skills}
    retired = [d for d in _marked(target) if d.name not in current]
    for d in retired:
        shutil.rmtree(d)
    return {"installed": sorted(current), "removed": [str(d) for d in retired],
            "version": __version__, "path": str(target)}


def _owned(d: Path) -> bool:
    """ReasonHold installed d: a real directory (never a symlink) carrying the marker."""
    return d.is_dir() and not d.is_symlink() and (d / MARKER).is_file()


def _marked(target: Path) -> list[Path]:
    """Skill directories ReasonHold installed, by their marker."""
    return sorted(d for d in target.iterdir() if _owned(d)) if target.is_dir() else []


def skills_line(root: Path | str) -> str | None:
    """The preamble's notice when skills ReasonHold installed are from another version or unstamped.

    None when the pack is current, and None where ReasonHold never installed skills
    (no stamp and no marked directory), so repositories that do not use them see nothing.
    """
    target = skills_dir(root)
    stamp = target / STAMP
    if stamp.is_file():
        installed = stamp.read_text().strip()
        if installed == __version__:
            return None
    elif _marked(target):
        installed = "none"
    else:
        return None
    return f"skills from {installed or 'none'}, package {__version__}: run `reasonhold skills install`"
