"""The indexer must refuse binary content instead of trusting the glob.

index_file() reads every file with read_text(errors="replace") and
detect_file_type() maps any unrecognised suffix to "markdown". Together those
mean a single widened glob in sync-doc.yaml — docs/**/* or tests/fixtures/* —
would decode a PDF into replacement-character noise and index it as a markdown
document, with the wrong file_type, no error, and no way to tell afterwards.

That is the same defect as issue #2 in the conversion pipeline, in a different
tool. The manifest is currently the only thing preventing it, which makes the
safety property a scoping accident rather than a guarantee. These tests pin it
as a guarantee.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reasonhold.index import detect_file_type, index_file, is_binary_file
from reasonhold.manifest import AreaManifest, Manifest

# Real PDF magic followed by binary. Decodes to ~50% U+FFFD under errors="replace".
PDF_BYTES = b"%PDF-1.4\n" + bytes(range(256)) * 200


@pytest.fixture
def manifest() -> Manifest:
    return Manifest(
        global_index=("AGENTS.md",),
        areas=(
            AreaManifest(
                name="pipeline",
                description="Pipeline",
                projects=("worker",),
                docs=("docs/specs/worker-design.md",),
                index=("src/worker/**/*.py",),
            ),
        ),
    )


class TestBinaryDetection:
    def test_pdf_is_binary(self, tmp_path):
        p = tmp_path / "report.pdf"
        p.write_bytes(PDF_BYTES)
        assert is_binary_file(p) is True

    def test_nul_bytes_make_a_file_binary(self, tmp_path):
        p = tmp_path / "export.dat"
        p.write_bytes(b"header\x00\x00\x00\x00payload\x00\x00")
        assert is_binary_file(p) is True

    def test_markdown_is_not_binary(self, tmp_path):
        p = tmp_path / "design.md"
        p.write_text("# Design\n\nThe converter writes markdown.\n", encoding="utf-8")
        assert is_binary_file(p) is False

    def test_utf8_prose_with_accents_is_not_binary(self, tmp_path):
        """Non-ASCII UTF-8 is text. Rejecting it would be a false positive."""
        p = tmp_path / "notes.md"
        p.write_text("Café, naïve, Ariadne — 日本語のテキスト\n", encoding="utf-8")
        assert is_binary_file(p) is False

    def test_empty_file_is_not_binary(self, tmp_path):
        p = tmp_path / "empty.md"
        p.write_text("", encoding="utf-8")
        assert is_binary_file(p) is False

    def test_a_few_bad_bytes_in_text_are_tolerated(self, tmp_path):
        p = tmp_path / "notes.md"
        p.write_bytes(b"# Notes\n\nThe defendant\xff\xfe pleaded guilty in open court.\n")
        assert is_binary_file(p) is False


class TestIndexFileRefusesBinary:
    def test_pdf_produces_no_chunks(self, tmp_path, manifest, monkeypatch):
        """A widened glob must not be able to put mojibake in the index."""
        import reasonhold.index as index_mod

        monkeypatch.setattr(index_mod, "PROJECT_ROOT", tmp_path)
        pdf = tmp_path / "fixture.pdf"
        pdf.write_bytes(PDF_BYTES)

        count = index_file(
            collection=None,
            oll_client=None,
            manifest=manifest,
            file_type=detect_file_type(pdf),
            path=pdf,
            dry_run=True,
        )
        assert count == 0

    def test_markdown_still_indexes(self, tmp_path, manifest, monkeypatch):
        """The guard must not suppress the corpus it exists to protect."""
        import reasonhold.index as index_mod

        monkeypatch.setattr(index_mod, "PROJECT_ROOT", tmp_path)
        md = tmp_path / "design.md"
        md.write_text("# Design\n\nThe converter writes markdown to disk.\n", encoding="utf-8")

        count = index_file(
            collection=None,
            oll_client=None,
            manifest=manifest,
            file_type=detect_file_type(md),
            path=md,
            dry_run=True,
        )
        assert count > 0


class TestFileTypeLabelling:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("design.md", "markdown"),
            ("worker.py", "python"),
            ("schema.sql", "sql"),
            ("sync-doc.yaml", "yaml"),
            ("compose.yml", "yaml"),
        ],
    )
    def test_known_suffixes_keep_their_type(self, tmp_path, name, expected):
        assert detect_file_type(tmp_path / name) == expected

    @pytest.mark.parametrize("name", ["report.pdf", "archive.zip", "photo.png", "model.bin"])
    def test_binary_suffixes_are_not_labelled_markdown(self, tmp_path, name):
        """Calling a PDF 'markdown' is wrong metadata, not a harmless default."""
        assert detect_file_type(tmp_path / name) != "markdown"

    def test_extensionless_text_still_defaults_to_markdown(self, tmp_path):
        """Dockerfile and justfile carry the deployment substrate and must index."""
        assert detect_file_type(tmp_path / "Dockerfile") == "markdown"
        assert detect_file_type(tmp_path / "justfile") == "markdown"
