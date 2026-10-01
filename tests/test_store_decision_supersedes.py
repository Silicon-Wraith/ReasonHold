"""Tests for store_decision supersedes validation."""

from pathlib import Path

import pytest

from reasonhold.server import _format_decision_content, _validate_supersedes


class TestValidateSupersedes:
    def test_none_returns_empty_list(self):
        assert _validate_supersedes(None) == []

    def test_empty_returns_empty_list(self):
        assert _validate_supersedes([]) == []

    def test_valid_entry_normalized(self):
        result = _validate_supersedes(
            [
                {"path": "nebulon-design/architecture/X.md", "retraction_summary": "X is retracted."},
            ]
        )
        assert result == [
            {"path": "nebulon-design/architecture/X.md", "retraction_summary": "X is retracted."},
        ]

    def test_valid_entry_strips_whitespace(self):
        result = _validate_supersedes(
            [
                {"path": "  path/to/doc.md  ", "retraction_summary": "  summary  "},
            ]
        )
        assert result[0]["path"] == "path/to/doc.md"
        assert result[0]["retraction_summary"] == "summary"

    def test_missing_path_raises(self):
        with pytest.raises(ValueError, match="path must be a non-empty string"):
            _validate_supersedes([{"retraction_summary": "x"}])

    def test_empty_path_raises(self):
        with pytest.raises(ValueError, match="path must be a non-empty string"):
            _validate_supersedes([{"path": "", "retraction_summary": "x"}])

    def test_missing_summary_raises(self):
        with pytest.raises(ValueError, match="retraction_summary must be a non-empty string"):
            _validate_supersedes([{"path": "p"}])

    def test_empty_summary_raises(self):
        with pytest.raises(ValueError, match="retraction_summary must be a non-empty string"):
            _validate_supersedes([{"path": "p", "retraction_summary": "   "}])

    def test_non_dict_entry_raises(self):
        with pytest.raises(ValueError, match="must be a dict"):
            _validate_supersedes(["string instead of dict"])


class TestFormatDecisionContent:
    def test_supersedes_block_rendered(self):
        record = {
            "topic": "t",
            "decision": "D",
            "rationale": "R",
            "alternatives_considered": [],
            "session_context": "C",
            "datetime": "2026-04-21T10:00:00+00:00",
            "status": "active",
            "supersedes": [
                {"path": "a.md", "retraction_summary": "a retracted"},
                {"path": "b.md#2", "retraction_summary": "b §2 retracted"},
            ],
        }
        content = _format_decision_content(record)
        assert "Supersedes:" in content
        assert "  - a.md: a retracted" in content
        assert "  - b.md#2: b §2 retracted" in content

    def test_supersedes_block_omitted_when_empty(self):
        record = {
            "topic": "t",
            "decision": "D",
            "rationale": "R",
            "alternatives_considered": [],
            "session_context": "C",
            "datetime": "2026-04-21T10:00:00+00:00",
            "status": "active",
            "supersedes": [],
        }
        content = _format_decision_content(record)
        assert "Supersedes:" not in content

    def test_supersedes_key_missing_tolerated(self):
        record = {
            "topic": "t",
            "decision": "D",
            "rationale": "R",
            "alternatives_considered": [],
            "session_context": "C",
            "datetime": "2026-03-01T10:00:00+00:00",
            "status": "active",
        }
        content = _format_decision_content(record)
        assert "Supersedes:" not in content
