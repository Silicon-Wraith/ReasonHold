"""Tests for retraction overlay construction and matching in the indexer."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from index import load_retraction_overlay, retraction_for_chunk


def _write_records(tmp_path, records):
    target = tmp_path / "decisions.jsonl"
    with open(target, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return target


class TestLoadRetractionOverlay:
    def test_empty_file_returns_empty(self, tmp_path):
        target = tmp_path / "empty.jsonl"
        target.write_text("")
        assert load_retraction_overlay(target) == {}

    def test_missing_file_returns_empty(self, tmp_path):
        assert load_retraction_overlay(tmp_path / "nope.jsonl") == {}

    def test_active_supersedes_entry_loaded(self, tmp_path):
        target = _write_records(
            tmp_path,
            [
                {
                    "topic": "t1",
                    "datetime": "2026-04-21T10:00:00+00:00",
                    "status": "active",
                    "supersedes": [
                        {"path": "a.md", "retraction_summary": "a retracted"},
                    ],
                }
            ],
        )
        overlay = load_retraction_overlay(target)
        assert overlay == {
            "a.md": {
                "retraction_summary": "a retracted",
                "retraction_decision": "t1",
                "retraction_date": "2026-04-21T10:00:00+00:00",
            }
        }

    def test_superseded_status_ignored(self, tmp_path):
        target = _write_records(
            tmp_path,
            [
                {
                    "topic": "t1",
                    "datetime": "2026-04-21T10:00:00+00:00",
                    "status": "superseded",
                    "supersedes": [
                        {"path": "a.md", "retraction_summary": "a retracted"},
                    ],
                }
            ],
        )
        assert load_retraction_overlay(target) == {}

    def test_later_active_wins_on_path_collision(self, tmp_path):
        target = _write_records(
            tmp_path,
            [
                {
                    "topic": "early",
                    "datetime": "2026-01-01T10:00:00+00:00",
                    "status": "active",
                    "supersedes": [{"path": "x.md", "retraction_summary": "early"}],
                },
                {
                    "topic": "later",
                    "datetime": "2026-04-01T10:00:00+00:00",
                    "status": "active",
                    "supersedes": [{"path": "x.md", "retraction_summary": "later"}],
                },
            ],
        )
        overlay = load_retraction_overlay(target)
        assert overlay["x.md"]["retraction_summary"] == "later"

    def test_entries_missing_fields_skipped(self, tmp_path):
        target = _write_records(
            tmp_path,
            [
                {
                    "topic": "t",
                    "datetime": "2026-04-21T10:00:00+00:00",
                    "status": "active",
                    "supersedes": [
                        {"path": "", "retraction_summary": "bad"},
                        {"path": "ok.md", "retraction_summary": ""},
                        {"path": "good.md", "retraction_summary": "good"},
                    ],
                }
            ],
        )
        overlay = load_retraction_overlay(target)
        assert "good.md" in overlay
        assert "ok.md" not in overlay
        assert "" not in overlay

    def test_non_list_supersedes_skipped(self, tmp_path):
        target = _write_records(
            tmp_path,
            [
                {
                    "topic": "bad",
                    "datetime": "2026-04-21T10:00:00+00:00",
                    "status": "active",
                    "supersedes": "not a list",
                },
                {
                    "topic": "good",
                    "datetime": "2026-04-21T10:00:01+00:00",
                    "status": "active",
                    "supersedes": [{"path": "g.md", "retraction_summary": "g"}],
                },
            ],
        )
        overlay = load_retraction_overlay(target)
        assert overlay == {
            "g.md": {
                "retraction_summary": "g",
                "retraction_decision": "good",
                "retraction_date": "2026-04-21T10:00:01+00:00",
            }
        }


class TestRetractionForChunk:
    def test_exact_path_matches(self):
        overlay = {"doc.md": {"retraction_summary": "r", "retraction_decision": "t", "retraction_date": "d"}}
        chunk = {"file_path": "doc.md", "section_heading": "anything"}
        assert retraction_for_chunk(chunk, overlay) == overlay["doc.md"]

    def test_no_path_no_match(self):
        overlay = {"other.md": {"retraction_summary": "r", "retraction_decision": "t", "retraction_date": "d"}}
        chunk = {"file_path": "doc.md", "section_heading": "x"}
        assert retraction_for_chunk(chunk, overlay) is None

    def test_section_anchor_substring_matches_heading(self):
        overlay = {
            "doc.md#3.2": {"retraction_summary": "r", "retraction_decision": "t", "retraction_date": "d"},
        }
        chunk = {"file_path": "doc.md", "section_heading": "3.2 Generation Authority"}
        assert retraction_for_chunk(chunk, overlay) == overlay["doc.md#3.2"]

    def test_section_anchor_does_not_match_other_section(self):
        overlay = {
            "doc.md#3.2": {"retraction_summary": "r", "retraction_decision": "t", "retraction_date": "d"},
        }
        chunk = {"file_path": "doc.md", "section_heading": "4.1 Another Section"}
        assert retraction_for_chunk(chunk, overlay) is None

    def test_empty_file_path_no_match(self):
        overlay = {"doc.md": {"retraction_summary": "r", "retraction_decision": "t", "retraction_date": "d"}}
        chunk = {"file_path": "", "section_heading": "x"}
        assert retraction_for_chunk(chunk, overlay) is None


class TestEndToEndChunkWithRetraction:
    """Non-Weaviate integration: confirm that an indexer-style pipeline
    attaches retraction metadata to the right chunks and leaves others
    untouched, using only the public helpers."""

    def test_chunk_gets_retraction_when_path_matches(self, tmp_path):
        target = _write_records(
            tmp_path,
            [
                {
                    "topic": "t1",
                    "datetime": "2026-04-21T10:00:00+00:00",
                    "status": "active",
                    "supersedes": [{"path": "design/a.md", "retraction_summary": "A retracted"}],
                }
            ],
        )
        overlay = load_retraction_overlay(target)

        chunks = [
            {"file_path": "design/a.md", "section_heading": "Overview"},
            {"file_path": "design/b.md", "section_heading": "Overview"},
        ]

        enriched = []
        for chunk in chunks:
            props = {"file_path": chunk["file_path"]}
            if chunk.get("chunk_type") != "decision":
                retraction = retraction_for_chunk(chunk, overlay)
                if retraction:
                    props["retraction_summary"] = retraction["retraction_summary"]
                    props["retraction_decision"] = retraction["retraction_decision"]
                    props["retraction_date"] = retraction["retraction_date"]
            enriched.append(props)

        assert enriched[0]["retraction_summary"] == "A retracted"
        assert "retraction_summary" not in enriched[1]

    def test_decision_chunks_are_not_themselves_annotated(self, tmp_path):
        target = _write_records(
            tmp_path,
            [
                {
                    "topic": "t1",
                    "datetime": "2026-04-21T10:00:00+00:00",
                    "status": "active",
                    "supersedes": [
                        {"path": "docs-rag/decisions.jsonl", "retraction_summary": "nope"},
                    ],
                }
            ],
        )
        overlay = load_retraction_overlay(target)

        decision_chunk = {
            "file_path": "docs-rag/decisions.jsonl",
            "chunk_type": "decision",
            "section_heading": "t1",
        }

        # Prove the overlay would otherwise match this chunk's path — so the
        # only thing preventing annotation is the chunk_type guard.
        assert retraction_for_chunk(decision_chunk, overlay) is not None

        props = {"file_path": decision_chunk["file_path"]}
        if decision_chunk.get("chunk_type") != "decision":
            retraction = retraction_for_chunk(decision_chunk, overlay)
            if retraction:
                props["retraction_summary"] = retraction["retraction_summary"]

        assert "retraction_summary" not in props
