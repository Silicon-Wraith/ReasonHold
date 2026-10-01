"""Tests for manifest-driven retrieval scope."""

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from manifest import load_manifest


class TestManifest:
    def test_loads_global_and_area_index(self, tmp_path):
        manifest_path = tmp_path / "sync-doc.yaml"
        manifest_path.write_text(
            textwrap.dedent("""\
            global:
              checks:
                - source-layout
              index:
                - AGENTS.md
                - sync-doc.yaml

            areas:
              simulator-controller:
                description: "Controller"
                projects:
                  - Nebulon.Simulator.Controller
                checks:
                  - simulator-design-spec
                docs:
                  - docs/superpowers/specs/controller.md
                index:
                  - src/Nebulon.Simulator.Controller/**/*.cs
                  - tests/Nebulon.Simulator.Controller.Tests/**/*.cs
        """)
        )

        manifest = load_manifest(manifest_path)

        assert "AGENTS.md" in manifest.global_index
        assert manifest.areas[0].name == "simulator-controller"
        assert manifest.areas[0].index[0] == "src/Nebulon.Simulator.Controller/**/*.cs"

    def test_fails_when_global_index_missing(self, tmp_path):
        manifest_path = tmp_path / "sync-doc.yaml"
        manifest_path.write_text(
            textwrap.dedent("""\
            global:
              checks:
                - source-layout

            areas:
              core:
                description: "Core"
                projects:
                  - Nebulon.Core
                docs:
                  - nebulon-design/CONSTANTS.md
                index:
                  - src/Nebulon.Core/**/*.cs
        """)
        )

        with pytest.raises(ValueError, match="global.index"):
            load_manifest(manifest_path)

    def test_fails_when_area_index_missing(self, tmp_path):
        manifest_path = tmp_path / "sync-doc.yaml"
        manifest_path.write_text(
            textwrap.dedent("""\
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
        """)
        )

        with pytest.raises(ValueError, match="areas.core.index"):
            load_manifest(manifest_path)

    def test_infers_area_from_doc_and_source_paths(self, tmp_path):
        manifest_path = tmp_path / "sync-doc.yaml"
        manifest_path.write_text(
            textwrap.dedent("""\
            global:
              checks:
                - source-layout
              index:
                - AGENTS.md

            areas:
              simulator-controller:
                description: "Controller"
                projects:
                  - Nebulon.Simulator.Controller
                docs:
                  - docs/superpowers/specs/controller.md
                index:
                  - src/Nebulon.Simulator.Controller/**/*.cs
        """)
        )

        manifest = load_manifest(manifest_path)

        assert manifest.infer_area("docs/superpowers/specs/controller.md") == "simulator-controller"
        assert manifest.infer_area("src/Nebulon.Simulator.Controller/Services/Foo.cs") == "simulator-controller"
