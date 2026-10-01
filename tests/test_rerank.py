"""Tests for metadata-aware docs reranking."""

from pathlib import Path

from reasonhold.search import _detect_query_intents, _rerank_docs


class TestRerank:
    def test_detect_query_intents_supports_mixed_signal_queries(self):
        intents = _detect_query_intents("What decision led to MetricsSnapshot?")

        assert intents["decision"] == 1.0
        assert intents["symbol"] == 1.0
        assert intents["conceptual"] == 0.0

    def test_conceptual_query_prefers_spec_over_manifest_and_tests(self):
        results = [
            {
                "score": 0.64,
                "file_path": "sync-doc.yaml",
                "chunk_type": "sync_doc_area",
                "authority_level": "project-manifest",
                "document_kind": "sync_doc_manifest",
                "section_heading": "simulator-controller",
                "type_name": "",
                "member_name": "",
                "content": "",
            },
            {
                "score": 0.63,
                "file_path": "tests/Nebulon.Simulator.Controller.Tests/Coordination/EndToEndSimulationTests.cs",
                "chunk_type": "csharp_type",
                "authority_level": "test",
                "document_kind": "test_code",
                "section_heading": "EndToEndSimulationTests",
                "type_name": "EndToEndSimulationTests",
                "member_name": "",
                "content": "",
            },
            {
                "score": 0.62,
                "file_path": "docs/superpowers/specs/2026-03-31-simulator-controller-plane-design.md",
                "chunk_type": "markdown_section",
                "authority_level": "implementation-spec",
                "document_kind": "implementation_spec",
                "section_heading": "Simulator Controller Plane Design > Revised Simulator Plan Order",
                "type_name": "",
                "member_name": "",
                "content": "",
            },
        ]

        ranked = _rerank_docs("simulator controller lifecycle ordering", results)

        assert ranked[0]["file_path"] == "docs/superpowers/specs/2026-03-31-simulator-controller-plane-design.md"
        assert ranked[-1]["file_path"] == "sync-doc.yaml"

    def test_symbol_query_prefers_exact_type_match(self):
        results = [
            {
                "score": 0.70,
                "file_path": "tests/Nebulon.Simulator.Controller.Tests/Metrics/MetricsSnapshotTests.cs",
                "chunk_type": "csharp_type",
                "authority_level": "test",
                "document_kind": "test_code",
                "section_heading": "MetricsSnapshotTests",
                "type_name": "MetricsSnapshotTests",
                "member_name": "",
                "content": "",
            },
            {
                "score": 0.66,
                "file_path": "src/Nebulon.Simulator.Controller/Metrics/MetricsSnapshot.cs",
                "chunk_type": "csharp_type",
                "authority_level": "implementation",
                "document_kind": "source_code",
                "section_heading": "MetricsSnapshot",
                "type_name": "MetricsSnapshot",
                "member_name": "",
                "content": "",
            },
        ]

        ranked = _rerank_docs("MetricsSnapshot", results)

        assert ranked[0]["file_path"] == "src/Nebulon.Simulator.Controller/Metrics/MetricsSnapshot.cs"

    def test_decision_query_prefers_decision_log(self):
        results = [
            {
                "score": 0.66,
                "file_path": "docs-rag/decisions.jsonl",
                "chunk_type": "decision",
                "authority_level": "decision",
                "document_kind": "decision_log",
                "section_heading": "qwen3-embedding-configuration",
                "type_name": "",
                "member_name": "",
                "content": "",
            },
            {
                "score": 0.69,
                "file_path": "docs/superpowers/specs/2026-04-01-docs-rag-retrieval-pipeline-design.md",
                "chunk_type": "markdown_section",
                "authority_level": "implementation-spec",
                "document_kind": "implementation_spec",
                "section_heading": "Docs RAG Retrieval Pipeline Design > Embedding Configuration",
                "type_name": "",
                "member_name": "",
                "content": "",
            },
        ]

        ranked = _rerank_docs("why was qwen chosen as the embedding model", results)

        assert ranked[0]["file_path"] == "docs-rag/decisions.jsonl"

    def test_conceptual_query_overturns_small_base_advantage_for_manifest(self):
        results = [
            {
                "score": 0.72,
                "file_path": "sync-doc.yaml",
                "chunk_type": "sync_doc_area",
                "authority_level": "project-manifest",
                "document_kind": "sync_doc_manifest",
                "section_heading": "simulator-controller",
                "type_name": "",
                "member_name": "",
                "content": "",
            },
            {
                "score": 0.67,
                "file_path": "docs/superpowers/specs/2026-03-31-simulator-controller-plane-design.md",
                "chunk_type": "markdown_section",
                "authority_level": "implementation-spec",
                "document_kind": "implementation_spec",
                "section_heading": "Simulator Controller Plane Design > Revised Simulator Plan Order",
                "type_name": "",
                "member_name": "",
                "content": "",
            },
        ]

        ranked = _rerank_docs("simulator controller lifecycle ordering", results)

        assert ranked[0]["file_path"] == "docs/superpowers/specs/2026-03-31-simulator-controller-plane-design.md"

    def test_conceptual_query_can_override_large_manifest_base_gap(self):
        results = [
            {
                "score": 0.92,
                "file_path": "sync-doc.yaml",
                "chunk_type": "sync_doc_area",
                "authority_level": "project-manifest",
                "document_kind": "sync_doc_manifest",
                "section_heading": "simulator-controller",
                "type_name": "",
                "member_name": "",
                "content": "",
            },
            {
                "score": 0.67,
                "file_path": "docs/superpowers/specs/2026-03-31-simulator-controller-plane-design.md",
                "chunk_type": "markdown_section",
                "authority_level": "implementation-spec",
                "document_kind": "implementation_spec",
                "section_heading": "Simulator Controller Plane Design > Revised Simulator Plan Order",
                "type_name": "",
                "member_name": "",
                "content": "",
            },
        ]

        ranked = _rerank_docs("simulator controller lifecycle ordering", results)

        assert ranked[0]["file_path"] == "docs/superpowers/specs/2026-03-31-simulator-controller-plane-design.md"
