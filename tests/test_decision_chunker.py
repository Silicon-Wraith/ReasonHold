"""Tests for JSONL decision chunker."""

import json
from pathlib import Path

from reasonhold.chunkers import chunk_decisions


class TestDecisionChunker:
    def test_chunks_single_record(self):
        record = {
            "topic": "spacy-model-selection",
            "decision": "Use en_core_web_lg on CPU",
            "rationale": "9.6x faster, frees GPU for Docling",
            "alternatives_considered": ["en_core_web_trf on GPU"],
            "datetime": "2026-03-06T14:32:00-05:00",
            "session_context": "spaCy NER benchmark",
            "tags": ["performance", "spacy"],
            "status": "active",
        }
        text = json.dumps(record)
        chunks = chunk_decisions(text, "decisions.jsonl")

        assert len(chunks) == 1
        chunk = chunks[0]
        assert chunk["chunk_type"] == "decision"
        assert chunk["section_heading"] == "spacy-model-selection"
        assert chunk["chunk_index"] == 0
        assert "Use en_core_web_lg on CPU" in chunk["content"]
        assert "9.6x faster" in chunk["content"]
        assert "en_core_web_trf on GPU" in chunk["content"]
        assert chunk["decision_status"] == "active"

    def test_chunks_multiple_records(self):
        records = [
            {
                "topic": "topic-a",
                "decision": "Decision A",
                "rationale": "Reason A",
                "alternatives_considered": [],
                "datetime": "2026-03-06T10:00:00-05:00",
                "session_context": "Context A",
                "tags": ["a"],
                "status": "active",
            },
            {
                "topic": "topic-b",
                "decision": "Decision B",
                "rationale": "Reason B",
                "alternatives_considered": ["Alt B"],
                "datetime": "2026-03-06T11:00:00-05:00",
                "session_context": "Context B",
                "tags": ["b"],
                "status": "active",
            },
        ]
        text = "\n".join(json.dumps(r) for r in records)
        chunks = chunk_decisions(text, "decisions.jsonl")

        assert len(chunks) == 2
        assert chunks[0]["section_heading"] == "topic-a"
        assert chunks[1]["section_heading"] == "topic-b"
        assert chunks[0]["chunk_index"] == 0
        assert chunks[1]["chunk_index"] == 1

    def test_empty_file(self):
        chunks = chunk_decisions("", "decisions.jsonl")
        assert chunks == []

    def test_skips_malformed_lines(self):
        text = '{"topic": "good", "decision": "OK", "rationale": "R", "alternatives_considered": [], "datetime": "2026-03-06T10:00:00-05:00", "session_context": "C", "tags": [], "status": "active"}\nnot json\n'
        chunks = chunk_decisions(text, "decisions.jsonl")
        assert len(chunks) == 1
        assert chunks[0]["section_heading"] == "good"

    def test_content_format(self):
        record = {
            "topic": "batch-insert-strategy",
            "decision": "Use insert_many over batch.fixed_size",
            "rationale": "12ms vs 1050ms for single objects",
            "alternatives_considered": ["batch.fixed_size", "batch.dynamic"],
            "datetime": "2026-03-05T16:00:00-05:00",
            "session_context": "Weaviate perf investigation",
            "tags": ["weaviate", "performance"],
            "status": "active",
        }
        text = json.dumps(record)
        chunks = chunk_decisions(text, "decisions.jsonl")
        content = chunks[0]["content"]

        assert "Decision: Use insert_many over batch.fixed_size" in content
        assert "Topic: batch-insert-strategy" in content
        assert "Rationale: 12ms vs 1050ms" in content
        assert "batch.fixed_size" in content
        assert "batch.dynamic" in content
        assert "Weaviate perf investigation" in content
        assert "Tags: weaviate, performance" in content

    def test_supersedes_rendered_in_content(self):
        record = {
            "topic": "neighborhood-removal",
            "decision": "Neighborhoods removed as first-class concept",
            "rationale": "Per-link ECDH handles censorship resistance.",
            "alternatives_considered": [],
            "datetime": "2026-04-21T16:35:16.234663+00:00",
            "session_context": "",
            "tags": [],
            "status": "active",
            "supersedes": [
                {
                    "path": "nebulon-design/architecture/NEIGHBORHOOD_FORMATION_ALGORITHM.md",
                    "retraction_summary": "Neighborhoods removed. Voronoi cells retained only for geographic relay.",
                },
                {
                    "path": "nebulon-design/architecture/SUPERNODE_ELECTION_CONSENSUS.md#3.2",
                    "retraction_summary": "Primary supernode no longer announces generation increments.",
                },
            ],
        }
        text = json.dumps(record)
        chunks = chunk_decisions(text, "decisions.jsonl")

        content = chunks[0]["content"]
        assert "Supersedes:" in content
        assert "NEIGHBORHOOD_FORMATION_ALGORITHM.md" in content
        assert "Voronoi cells retained" in content
        assert "SUPERNODE_ELECTION_CONSENSUS.md#3.2" in content

    def test_supersedes_omitted_when_empty(self):
        record = {
            "topic": "ordinary-decision",
            "decision": "D",
            "rationale": "R",
            "alternatives_considered": [],
            "datetime": "2026-04-21T10:00:00+00:00",
            "session_context": "",
            "tags": [],
            "status": "active",
            "supersedes": [],
        }
        text = json.dumps(record)
        chunks = chunk_decisions(text, "decisions.jsonl")

        content = chunks[0]["content"]
        assert "Supersedes:" not in content

    def test_supersedes_missing_field_tolerated(self):
        record = {
            "topic": "legacy-decision",
            "decision": "D",
            "rationale": "R",
            "alternatives_considered": [],
            "datetime": "2026-03-01T10:00:00+00:00",
            "session_context": "",
            "tags": [],
            "status": "active",
        }
        text = json.dumps(record)
        chunks = chunk_decisions(text, "decisions.jsonl")

        content = chunks[0]["content"]
        assert "Supersedes:" not in content
        assert chunks[0]["decision_status"] == "active"
