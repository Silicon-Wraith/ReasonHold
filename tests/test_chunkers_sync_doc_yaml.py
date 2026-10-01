"""Tests for sync-doc.yaml semantic chunking."""

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from chunkers import chunk_yaml


class TestSyncDocChunker:
    def test_chunks_global_areas_and_checks(self):
        text = textwrap.dedent("""\
            global:
              checks:
                - source-layout
              index:
                - AGENTS.md

            areas:
              core:
                description: "Core"
                projects:
                  - Nebulon.Core
                docs:
                  - nebulon-design/CONSTANTS.md
                index:
                  - src/Nebulon.Core/**/*.cs

            checks:
              source-layout:
                description: "Verify source layout"
                reads:
                  - CLAUDE.md
                validates_against:
                  - src/*/
        """)

        chunks = chunk_yaml(text, "sync-doc.yaml")

        assert any(chunk["chunk_type"] == "sync_doc_global" for chunk in chunks)
        assert any(chunk["chunk_type"] == "sync_doc_area" and chunk["section_heading"] == "core" for chunk in chunks)
        assert any(
            chunk["chunk_type"] == "sync_doc_check" and chunk["section_heading"] == "source-layout" for chunk in chunks
        )
