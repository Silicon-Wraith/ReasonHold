"""index_file must report what actually landed, not what it tried to send.

A --full run reported 4,652 chunks indexed while Weaviate held 4,493. Twenty
files were missing entirely — the log claimed 21, 22, and 61 chunks for files
that stored zero. The cause was not chunking: re-running the chunkers produces
zero duplicate chunk identities. It was collection.data.insert_many() failing
intermittently under load while index_file discarded the result and returned
len(objects), so the run reported success for batches that never landed.

Silent partial loss in a retrieval index is worse than a failed run: the
corpus looks complete, and the missing documents are simply never retrieved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import reasonhold.indexer as index_mod
from reasonhold.indexer import index_file
from reasonhold.manifest import AreaManifest, Manifest


class _Err:
    def __init__(self, message: str) -> None:
        self.message = message


class _Result:
    def __init__(self, errors: dict[int, _Err] | None = None) -> None:
        self.errors = errors or {}
        self.has_errors = bool(self.errors)


class FakeCollection:
    """Records insert attempts and fails on a configurable schedule."""

    def __init__(self, fail_indices_per_call: list[dict[int, str]]) -> None:
        self._schedule = fail_indices_per_call
        self.calls: list[int] = []
        self.deleted: list[str] = []

    def _next(self) -> dict[int, str]:
        return self._schedule.pop(0) if self._schedule else {}

    class _Data:
        def __init__(self, outer):
            self._outer = outer

        def insert_many(self, objects):
            self._outer.calls.append(len(objects))
            failures = self._outer._next()
            return _Result({i: _Err(msg) for i, msg in failures.items()})

        def delete_by_id(self, uuid):
            pass

    @property
    def data(self):
        return FakeCollection._Data(self)

    class _Query:
        def fetch_objects(self, **kwargs):
            class R:
                objects = []

            return R()

    @property
    def query(self):
        return FakeCollection._Query()


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


@pytest.fixture
def doc(tmp_path, monkeypatch) -> Path:
    p = tmp_path / "design.md"
    p.write_text(
        "# Design\n\nFirst section body.\n\n## Second\n\nSecond section body.\n\n## Third\n\nThird section body.\n",
        encoding="utf-8",
    )
    return p


def _fake_embed(_client, texts, batch_size=8):
    return [[0.1] * 8 for _ in texts]


class TestInsertVerification:
    def test_clean_insert_reports_full_count(self, doc, manifest, monkeypatch):
        monkeypatch.setattr(index_mod, "embed_texts", _fake_embed)
        col = FakeCollection([])
        count = index_file(col, None, manifest, "markdown", doc, root=doc.parent)
        assert count == col.calls[0]
        assert count > 0

    def test_failed_objects_are_retried(self, doc, manifest, monkeypatch):
        """A transient failure must not silently drop the chunk."""
        monkeypatch.setattr(index_mod, "embed_texts", _fake_embed)
        col = FakeCollection([{0: "context deadline exceeded"}, {}])
        count = index_file(col, None, manifest, "markdown", doc, root=doc.parent)
        assert len(col.calls) == 2, "failed objects were not retried"
        assert col.calls[1] == 1, "retry should resend only the failed object"
        assert count == col.calls[0], "all chunks landed after retry"

    def test_persistent_failure_is_not_counted_as_success(self, doc, manifest, monkeypatch):
        """This is the bug: len(objects) was returned regardless of outcome."""
        monkeypatch.setattr(index_mod, "embed_texts", _fake_embed)
        col = FakeCollection([{0: "boom", 1: "boom"}, {0: "boom", 1: "boom"}])
        count = index_file(col, None, manifest, "markdown", doc, root=doc.parent)
        assert count == col.calls[0] - 2, f"expected 2 chunks unaccounted for, got count={count}"

    def test_persistent_failure_is_reported(self, doc, manifest, monkeypatch, capsys):
        monkeypatch.setattr(index_mod, "embed_texts", _fake_embed)
        col = FakeCollection([{0: "boom"}, {0: "boom"}])
        index_file(col, None, manifest, "markdown", doc, root=doc.parent)
        out = capsys.readouterr().out
        assert "design.md" in out
        assert "boom" in out or "FAILED" in out.upper()

    def test_total_loss_returns_zero(self, doc, manifest, monkeypatch):
        monkeypatch.setattr(index_mod, "embed_texts", _fake_embed)

        class AllFail(FakeCollection):
            def _next(self):
                return {i: "down" for i in range(100)}

        count = index_file(AllFail([]), None, manifest, "markdown", doc, root=doc.parent)
        assert count == 0, "a wholly failed file must not report chunks indexed"
