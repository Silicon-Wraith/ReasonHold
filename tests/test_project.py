import textwrap

import pytest

from reasonhold.authority import DEFAULT_LADDER
from reasonhold.errors import ManifestInvalid
from reasonhold.project import EmbeddingConfig, Project
from reasonhold.settings import weaviate_settings_from_env

LEGACY = """\
global:
  checks: [source-layout]
  docs: [docs/architecture/overview.md]
  archival: [docs/old.md]
  index: [AGENTS.md, sync-doc.yaml]
areas:
  worker:
    description: Worker
    projects: [worker]
    docs: [docs/specs/worker.md]
    index: ["src/worker/**/*.py"]
    checks: [worker-contract]
checks:
  worker-contract:
    description: Worker follows its spec
    mode: index
    reads: [docs/specs/worker.md]
    validates_against: [src/worker/]
"""


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))
    return path


def test_legacy_manifest_loads_with_defaults(tmp_path):
    write(tmp_path, "sync-doc.yaml", LEGACY)
    p = Project.load(tmp_path)
    assert p.manifest_rel == "sync-doc.yaml"
    assert p.ladder == DEFAULT_LADDER
    assert p.embedding == EmbeddingConfig()
    assert p.id == tmp_path.name.lower().replace("_", "-")
    assert p.decisions_rel == "decisions.jsonl"
    assert p.pending_rel == "reasonhold.pending.jsonl"
    assert p.branch_isolation is True
    assert p.manifest.global_docs == ("docs/architecture/overview.md",)
    assert p.manifest.global_archival == ("docs/old.md",)
    assert p.manifest.check("worker-contract").reads == ("docs/specs/worker.md",)
    assert p.manifest.areas[0].checks == ("worker-contract",)


def test_legacy_decision_log_location_is_honored(tmp_path):
    write(tmp_path, "sync-doc.yaml", LEGACY)
    write(tmp_path, "docs-rag/decisions.jsonl", "")
    assert Project.load(tmp_path).decisions_rel == "docs-rag/decisions.jsonl"


def test_reasonhold_yaml_wins_and_reads_new_blocks(tmp_path):
    write(tmp_path, "sync-doc.yaml", LEGACY)
    write(tmp_path, "reasonhold.yaml", LEGACY + """\
project:
  id: Ariadne
  decisions: docs/decisions.jsonl
  embedding: {provider: openai_compatible, model: m, base_url: "http://h:1/v1", api_key_env: KEY}
  index: {branch_isolation: false}
authority:
  - {level: architecture, paths: ["docs/architecture/**"], weight: 0.08}
""")
    p = Project.load(tmp_path)
    assert p.manifest_rel == "reasonhold.yaml" and p.id == "ariadne"
    assert p.decisions_rel == "docs/decisions.jsonl"
    assert p.embedding == EmbeddingConfig("openai_compatible", "m", "http://h:1/v1", "KEY")
    assert p.branch_isolation is False and p.ladder[0].level == "architecture"


def test_corpus_globs_include_the_decision_log(tmp_path):
    write(tmp_path, "sync-doc.yaml", LEGACY)
    assert Project.load(tmp_path).corpus_globs()[-1] == "decisions.jsonl"


def test_missing_manifest_is_manifest_invalid(tmp_path):
    with pytest.raises(ManifestInvalid):
        Project.load(tmp_path)


@pytest.mark.parametrize("bad", ["/etc/passwd", "../outside.md", "docs/../../x.md"])
def test_manifest_rejects_escaping_paths(tmp_path, bad):
    write(tmp_path, "sync-doc.yaml", LEGACY.replace("docs/old.md", bad))
    with pytest.raises(ManifestInvalid):
        Project.load(tmp_path)


def test_bad_check_mode_is_rejected(tmp_path):
    write(tmp_path, "sync-doc.yaml", LEGACY.replace("mode: index", "mode: vector"))
    with pytest.raises(ManifestInvalid):
        Project.load(tmp_path)


def test_weaviate_settings_from_env():
    s = weaviate_settings_from_env({"REASONHOLD_WEAVIATE_PORT": "9000", "DOCS_RAG_WEAVIATE_HOST": "h"})
    assert (s.host, s.http_port, s.grpc_port, s.cloud_url) == ("h", 9000, 50052, None)
    c = weaviate_settings_from_env({"REASONHOLD_WEAVIATE_CLOUD_URL": "https://x.weaviate.cloud", "REASONHOLD_WEAVIATE_API_KEY_ENV": "K"})
    assert c.cloud_url == "https://x.weaviate.cloud" and c.api_key_env == "K"
