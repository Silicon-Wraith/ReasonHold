"""Tests for semantic markdown chunking."""

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from chunkers import chunk_markdown


class TestSemanticMarkdownChunker:
    def test_labels_must_do_and_success_criteria_sections(self):
        text = textwrap.dedent("""\
            # Sample Spec

            ## Must-Do

            Requirement text.

            ## Success Criteria

            Outcome text.
        """)

        chunks = chunk_markdown(text, "docs/superpowers/specs/sample.md")

        must_do = next(chunk for chunk in chunks if chunk["section_heading"] == "Sample Spec > Must-Do")
        success = next(chunk for chunk in chunks if chunk["section_heading"] == "Sample Spec > Success Criteria")
        assert must_do["semantic_label"] == "must_do"
        assert success["semantic_label"] == "success_criteria"
