import pytest

from reasonhold.authority import (
    BUILTIN_LEVEL_WEIGHTS,
    DEFAULT_LADDER,
    AuthorityRule,
    classify,
    ladder_sha256,
    level_weights,
    parse_ladder,
    path_matches,
)
from reasonhold.errors import ManifestInvalid

SEED_CASES = [
    ("docs-rag/decisions.jsonl", ("decision", "decision_log")),
    ("sync-doc.yaml", ("project-manifest", "sync_doc_manifest")),
    ("AGENTS.md", ("project-guidance", "project_guidance")),
    ("CLAUDE.md", ("project-guidance", "project_guidance")),
    ("docs/architecture/x.md", ("architecture", "architecture_doc")),
    ("docs/specs/x.md", ("implementation-spec", "implementation_spec")),
    ("docs/plans/x.md", ("implementation-plan", "implementation_plan")),
    ("docs/reviews/x.md", ("review", "review_finding")),
    ("docs/bugs/x.md", ("review", "bug_investigation")),
    ("docs/runbook.md", ("reference", "operational_guide")),
    ("justfile", ("deployment", "deployment_config")),
    ("compose.infra.yml", ("deployment", "deployment_config")),
    ("Dockerfile", ("deployment", "deployment_config")),
    (".claude/skills/x/SKILL.md", ("tooling", "skill_definition")),
    ("docs-rag/index.py", ("tooling", "tooling_code")),
    ("scripts/x.sh", ("tooling", "tooling_code")),
    ("src/worker/x.py", ("implementation", "source_code")),
    ("ui/src/x.vue", ("implementation", "frontend_code")),
    ("tests/test_x.py", ("test", "test_code")),
    ("tools/x.py", ("tooling", "tooling_code")),
    ("README.txt", ("reference", "reference")),
]


@pytest.mark.parametrize("path, expected", SEED_CASES)
def test_default_ladder_reproduces_seed_classification(path, expected):
    got = classify(path, DEFAULT_LADDER, decisions_rel="docs-rag/decisions.jsonl", manifest_rel="sync-doc.yaml")
    assert got == expected


def test_seed_weights_are_reproduced():
    w = level_weights(DEFAULT_LADDER)
    assert w["architecture"] == 0.08 and w["implementation-spec"] == 0.06 and w["implementation-plan"] == 0.05
    assert w["project-guidance"] == 0.03 and w["deployment"] == 0.02 and w["implementation"] == 0.0
    assert w["review"] == 0.0 and w["reference"] == -0.02 and w["tooling"] == -0.04 and w["test"] == -0.05
    assert w["decision"] == BUILTIN_LEVEL_WEIGHTS["decision"] == 0.0
    assert w["project-manifest"] == BUILTIN_LEVEL_WEIGHTS["project-manifest"] == -0.06


def test_path_matches():
    assert path_matches("docs/specs/a/b.md", "docs/specs/**")
    assert not path_matches("docs/specsx/a.md", "docs/specs/**")
    assert path_matches("a/b/c.py", "*.py")
    assert path_matches("CLAUDE.md", "CLAUDE.md") and not path_matches("x/CLAUDE.md", "CLAUDE.md")


def test_custom_ladder_from_manifest_data():
    ladder = parse_ladder([
        {"level": "spec", "paths": ["design/**"], "document_kind": "design_doc", "weight": 0.07},
        {"level": "implementation", "paths": ["lib/**"]},
    ])
    assert classify("design/a.md", ladder, decisions_rel=None, manifest_rel=None) == ("spec", "design_doc")
    assert classify("lib/x.py", ladder, decisions_rel=None, manifest_rel=None) == ("implementation", "implementation")
    assert classify("other.md", ladder, decisions_rel=None, manifest_rel=None) == ("reference", "reference")
    assert level_weights(ladder)["spec"] == 0.07


@pytest.mark.parametrize("raw", [
    "not a list",
    [{"paths": ["x/**"]}],
    [{"level": "a", "paths": []}],
    [{"level": "a", "paths": ["/abs/**"]}],
    [{"level": "a", "paths": ["../up/**"]}],
    [{"level": "a", "paths": ["x/**"], "weight": "high"}],
])
def test_parse_ladder_rejects_bad_input(raw):
    with pytest.raises(ManifestInvalid):
        parse_ladder(raw)


def test_ladder_hash_changes_with_rules():
    a = ladder_sha256(DEFAULT_LADDER)
    b = ladder_sha256(DEFAULT_LADDER + (AuthorityRule("x", "x", ("x/**",)),))
    assert a != b and len(a) == 64
