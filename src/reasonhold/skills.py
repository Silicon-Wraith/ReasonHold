"""Install the packaged skill pack into a repository's .claude/skills/.

Each installed skill directory carries MARKER, so a later install replaces only
directories ReasonHold put there; any other directory with a packaged skill's
name stops the install before anything is written. STAMP records the package
version that installed the pack, and the preamble compares it with the running
package.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from reasonhold import __version__
from reasonhold.errors import SkillsConflict

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
    foreign = [s.name for s in skills if (target / s.name).exists() and not (target / s.name / MARKER).is_file()]
    if foreign:
        listed = ", ".join(f".claude/skills/{n}" for n in foreign)
        raise SkillsConflict(f"refusing to overwrite {listed}: ReasonHold did not install it; "
                             "move or rename it, then run `reasonhold skills install` again")
    target.mkdir(parents=True, exist_ok=True)
    for skill in skills:
        dest = target / skill.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(skill, dest, ignore=shutil.ignore_patterns("__pycache__"))
        (dest / MARKER).write_text(f"{__version__}\n")
    (target / STAMP).write_text(f"{__version__}\n")
    return {"installed": [s.name for s in skills], "version": __version__, "path": str(target)}


def skills_line(root: Path | str) -> str | None:
    """The preamble's notice when the installed pack is missing or from another version; None when current."""
    stamp = skills_dir(root) / STAMP
    installed = stamp.read_text().strip() if stamp.is_file() else ""
    if installed == __version__:
        return None
    return f"skills from {installed or 'none'}, package {__version__}: run `reasonhold skills install`"
