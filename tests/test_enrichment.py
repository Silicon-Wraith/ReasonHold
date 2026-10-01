"""Tests for deterministic enrichment and embedding text rendering."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from enrichment import _classify_authority, enrich_chunk, render_embedding_text
from manifest import AreaManifest, Manifest


class TestEnrichment:
    def test_adds_authority_area_and_project(self):
        manifest = Manifest(
            global_index=("AGENTS.md",),
            areas=(
                AreaManifest(
                    name="simulator-controller",
                    description="Controller",
                    projects=("Nebulon.Simulator.Controller",),
                    docs=("docs/superpowers/specs/controller.md",),
                    index=("src/Nebulon.Simulator.Controller/**/*.cs",),
                ),
            ),
        )
        chunk = {
            "content": "public class Controller {}",
            "chunk_type": "csharp_type",
            "file_path": "src/Nebulon.Simulator.Controller/Controller.cs",
            "chunk_index": 0,
            "type_name": "Controller",
            "section_path": "Controller",
        }

        enriched = enrich_chunk(chunk, manifest)

        assert enriched["authority_level"] == "implementation"
        assert enriched["document_kind"] == "source_code"
        assert enriched["area"] == "simulator-controller"
        assert enriched["project"] == "Nebulon.Simulator.Controller"

    def test_renders_context_plus_body(self):
        chunk = {
            "content": "Requirement text.",
            "file_path": "docs/superpowers/specs/sample.md",
            "document_kind": "implementation_spec",
            "authority_level": "implementation-spec",
            "area": "simulator-controller",
            "section_path": "Sample > Must-Do",
            "semantic_label": "must_do",
        }

        rendered = render_embedding_text(chunk)

        assert "Document kind: implementation_spec" in rendered
        assert "Authority: implementation-spec" in rendered
        assert "Area: simulator-controller" in rendered
        assert "Section path: Sample > Must-Do" in rendered
        assert rendered.endswith("Requirement text.")


class TestAriadneAuthorityLadder:
    """_classify_authority must encode AGENTS.md's documentation precedence.

    The ladder is what lets retrieval prefer the governing document over a
    plan that merely describes how it was executed. Ariadne's precedence is
    architecture > specs > plans > src, with reviews and bug investigations
    as records rather than authority. A path that falls through to the
    generic "reference" default is a classifier gap, not a neutral outcome —
    it flattens the ladder for that whole directory.
    """

    ARIADNE_PATHS = [
        ("docs/architecture/pipeline-architecture.md", "architecture", "architecture_doc"),
        ("docs/architecture/v1-data-model.md", "architecture", "architecture_doc"),
        ("docs/specs/2026-08-06-deployment-architecture-design.md", "implementation-spec", "implementation_spec"),
        ("docs/plans/2026-08-07-deployment-stack-plan.md", "implementation-plan", "implementation_plan"),
        ("docs/reviews/2026-08-08-cuda-spike-findings.md", "review", "review_finding"),
        ("docs/bugs/2026-08-19-example.md", "review", "bug_investigation"),
        ("docs/operator-runbook.md", "reference", "operational_guide"),
        ("docs/python_programming_standards.md", "reference", "operational_guide"),
        ("src/worker/converter.py", "implementation", "source_code"),
        ("tests/unit/test_file_parser_docling_failure.py", "test", "test_code"),
        ("AGENTS.md", "project-guidance", "project_guidance"),
        ("CLAUDE.md", "project-guidance", "project_guidance"),
        ("sync-doc.yaml", "project-manifest", "sync_doc_manifest"),
        ("docs-rag/decisions.jsonl", "decision", "decision_log"),
    ]

    @pytest.mark.parametrize("path,authority,kind", ARIADNE_PATHS)
    def test_classifies_ariadne_paths(self, path, authority, kind):
        assert _classify_authority(path) == (authority, kind)

    def test_deployment_substrate_is_not_generic_reference(self):
        """Compose files and Dockerfiles carry the container rearchitecture."""
        for path in ("compose.app.yml", "Dockerfile", "compose.infra.yml", "justfile"):
            authority, kind = _classify_authority(path)
            assert authority == "deployment", f"{path} -> {authority}"
            assert kind == "deployment_config"

    def test_tooling_code_is_distinct_from_product_code(self):
        assert _classify_authority("docs-rag/index.py") == ("tooling", "tooling_code")
        assert _classify_authority("devtools/reset_postgres.py") == ("tooling", "tooling_code")

    def test_ui_source_classified_as_implementation(self):
        authority, kind = _classify_authority("ui/src/components/PipelineFlowBar.vue")
        assert authority == "implementation"
        assert kind == "frontend_code"

    def test_no_ariadne_doc_falls_through_to_bare_reference_kind(self):
        """The generic fallback must not swallow a governed docs/ directory."""
        for path, _, _ in self.ARIADNE_PATHS:
            _, kind = _classify_authority(path)
            assert kind != "reference", f"{path} hit the generic fallback"


class TestAuthorityWeightsCoverTheLadder:
    """Every authority level the classifier emits needs a rank, or the
    ladder silently flattens to 0.0 at query time."""

    def test_every_emitted_level_has_a_weight(self):
        from server import AUTHORITY_WEIGHTS

        emitted = {
            _classify_authority(path)[0]
            for path in (
                "docs/architecture/architecture.md",
                "docs/specs/x-design.md",
                "docs/plans/x-plan.md",
                "docs/reviews/x.md",
                "src/worker/converter.py",
                "tests/unit/test_x.py",
                "AGENTS.md",
                "sync-doc.yaml",
                "docs-rag/decisions.jsonl",
            )
        }
        missing = sorted(level for level in emitted if level not in AUTHORITY_WEIGHTS)
        assert not missing, f"authority levels with no rank: {missing}"

    def test_precedence_order_matches_agents_md(self):
        from server import AUTHORITY_WEIGHTS

        assert (
            AUTHORITY_WEIGHTS["architecture"]
            > AUTHORITY_WEIGHTS["implementation-spec"]
            > AUTHORITY_WEIGHTS["implementation-plan"]
            > AUTHORITY_WEIGHTS["implementation"]
        )
