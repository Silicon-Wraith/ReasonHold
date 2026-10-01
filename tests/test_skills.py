import pytest

from helpers import make_repo, write
from reasonhold import __version__
from reasonhold.cli import main
from reasonhold.errors import SkillsConflict
from reasonhold.preamble import render_preamble
from reasonhold.skills import MARKER, STAMP, install, packaged_skills, skills_line


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


def fresh_probe(project):
    return ["- Branch `main`, collection `RH_R__main`: fresh"]


def names():
    return sorted(p.name for p in packaged_skills())


def test_install_copies_the_pack_and_stamps_the_version(tmp_path):
    out = install(tmp_path)
    target = tmp_path / ".claude" / "skills"
    assert out == {"installed": names(), "version": __version__, "path": str(target)}
    assert names() and all((target / n / "SKILL.md").is_file() for n in names())
    assert all((target / n / MARKER).is_file() for n in names())
    assert (target / STAMP).read_text().strip() == __version__


def test_reinstall_replaces_skills_reasonhold_installed(tmp_path):
    install(tmp_path)
    skill = tmp_path / ".claude" / "skills" / names()[0]
    (skill / "SKILL.md").write_text("edited")
    (skill / "stale.md").write_text("left over")
    install(tmp_path)
    assert (skill / "SKILL.md").read_text() == (packaged_skills()[0] / "SKILL.md").read_text()
    assert not (skill / "stale.md").exists()


def test_refuses_to_overwrite_a_skill_reasonhold_did_not_install(tmp_path):
    foreign = write(tmp_path, f".claude/skills/{names()[-1]}/SKILL.md", "mine")
    write(tmp_path, ".claude/skills/other/SKILL.md", "other")
    with pytest.raises(SkillsConflict, match=names()[-1]):
        install(tmp_path)
    assert foreign.read_text() == "mine"
    assert not (tmp_path / ".claude" / "skills" / STAMP).exists()
    assert not (tmp_path / ".claude" / "skills" / names()[0]).exists()


def test_install_leaves_unrelated_skills_alone(tmp_path):
    other = write(tmp_path, ".claude/skills/other/SKILL.md", "other")
    install(tmp_path)
    assert other.read_text() == "other"


def test_skills_line_names_the_stamp_and_the_package(tmp_path):
    assert skills_line(tmp_path) == f"skills from none, package {__version__}: run `reasonhold skills install`"
    install(tmp_path)
    assert skills_line(tmp_path) is None
    (tmp_path / ".claude" / "skills" / STAMP).write_text("0.0.9\n")
    assert skills_line(tmp_path) == f"skills from 0.0.9, package {__version__}: run `reasonhold skills install`"


def test_preamble_reports_missing_or_stale_skills(tmp_path):
    root = make_repo(tmp_path / "r")
    assert "skills from none" in render_preamble(root, index_probe=fresh_probe)
    install(root)
    assert "reasonhold skills install" not in render_preamble(root, index_probe=fresh_probe)


def test_cli_skills_install(tmp_path, capsys):
    assert main(["skills", "install", "--root", str(tmp_path)]) == 0
    assert (tmp_path / ".claude" / "skills" / STAMP).is_file()
    assert __version__ in capsys.readouterr().out


def test_cli_skills_install_refusal_exits_2(tmp_path, capsys):
    write(tmp_path, f".claude/skills/{names()[0]}/SKILL.md", "mine")
    assert main(["--root", str(tmp_path), "skills", "install"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("reasonhold:") and "did not install" in err
