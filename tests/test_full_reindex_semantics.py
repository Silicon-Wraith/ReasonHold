"""A --full run must empty the collection, and no run may delete what it is inserting.

Two --full runs each reported ~4,660 chunks while the collection held exactly
159 fewer, with whole files missing and no insert errors. The cause was the
interaction of two behaviours that are individually reasonable:

  1. ensure_collection(recreate=True) returns early when the schema matches, so
     --full never actually emptied the collection.
  2. index_file called delete_file_chunks(rel_path) and then immediately
     inserted objects carrying the SAME deterministic UUID5 keys.

Weaviate applies deletes asynchronously, so a delete still in flight removes the
object the insert just wrote. Because a file's UUIDs are deleted in one tight
loop right before its insert, entire files disappeared — silently, since the
insert itself reported success.

Deterministic UUIDs make delete-then-insert unnecessary: an insert with the same
key is already an upsert. Only genuinely stale keys need deleting, and only
after the insert.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import reasonhold.indexer as index_mod
import reasonhold.store as store_mod
from reasonhold.indexer import index_file
from reasonhold.manifest import AreaManifest, Manifest
from reasonhold.store import CollectionMeta


class FakeClient:
    def __init__(self, exists: bool = True) -> None:
        self._exists = exists

        class _Collections:
            def __init__(self, outer):
                self._outer = outer

            def exists(self, name):
                return self._outer._exists

        self.collections = _Collections(self)


class TestFullReindexEmptiesTheCollection:
    def test_full_recreates_even_when_schema_matches(self, monkeypatch):
        """--full means 'force full re-index'. A matching schema is not a reason to skip."""
        calls = []
        monkeypatch.setattr(store_mod, "collection_matches_expected_schema", lambda c, n: True)
        monkeypatch.setattr(store_mod, "drop_collection", lambda c, n: calls.append("drop"))
        monkeypatch.setattr(store_mod, "create_collection", lambda c, n, m: calls.append("create"))

        store_mod.ensure_collection(
            FakeClient(exists=True), "RH_T__main", CollectionMeta("t", "main", "ollama:m", 4), recreate=True
        )

        assert calls == ["drop", "create"], f"--full did not recreate the collection: {calls}"

    def test_non_full_keeps_a_matching_collection(self, monkeypatch):
        calls = []
        monkeypatch.setattr(store_mod, "collection_matches_expected_schema", lambda c, n: True)
        monkeypatch.setattr(store_mod, "drop_collection", lambda c, n: calls.append("drop"))
        monkeypatch.setattr(store_mod, "create_collection", lambda c, n, m: calls.append("create"))

        store_mod.ensure_collection(
            FakeClient(exists=True), "RH_T__main", CollectionMeta("t", "main", "ollama:m", 4), recreate=False
        )

        assert calls == [], "an incremental run must not drop the collection"


class _Result:
    has_errors = False
    errors: dict = {}


class RecordingCollection:
    """Records the interleaving of deletes and inserts by UUID."""

    def __init__(self, existing_uuids: list[str] | None = None, file_path: str = "design.md") -> None:
        self.existing = list(existing_uuids or [])
        self.file_path = file_path
        self.events: list[tuple[str, str]] = []  # (op, uuid)

    class _Data:
        def __init__(self, outer):
            self._outer = outer

        def insert_many(self, objects):
            for o in objects:
                self._outer.events.append(("insert", str(o.uuid)))
            return _Result()

        def delete_by_id(self, uuid):
            self._outer.events.append(("delete", str(uuid)))

    @property
    def data(self):
        return RecordingCollection._Data(self)

    class _Query:
        def __init__(self, outer):
            self._outer = outer

        def fetch_objects(self, **kwargs):
            outer = self._outer

            class Obj:
                def __init__(self, u, path):
                    self.uuid = u
                    self.properties = {"file_path": path}

            class R:
                objects = [Obj(u, outer.file_path) for u in outer.existing]

            return R()

    @property
    def query(self):
        return RecordingCollection._Query(self)


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
    monkeypatch.setattr(index_mod, "embed_texts", lambda c, t, batch_size=8: [[0.1] * 8 for _ in t])
    p = tmp_path / "design.md"
    p.write_text(
        "# Design\n\nFirst body.\n\n## Second\n\nSecond body.\n\n## Third\n\nThird body.\n",
        encoding="utf-8",
    )
    return p


class TestNoDeleteOfWhatWeInsert:
    def test_never_deletes_a_uuid_it_inserts(self, doc, manifest):
        """The race: a delete in flight removes the object the insert just wrote.

        Simulates a re-index — the collection already holds this file's chunks
        under the same deterministic keys, which is exactly the situation every
        --full run was in, because --full never emptied the collection.
        """
        col = RecordingCollection()
        index_file(col, None, manifest, "markdown", doc, root=doc.parent)
        first_pass = [u for op, u in col.events if op == "insert"]
        assert first_pass, "fixture produced no chunks"

        # Re-index: the store now holds those very UUIDs.
        col.existing = first_pass
        col.events = []
        index_file(col, None, manifest, "markdown", doc, root=doc.parent)

        inserted = {u for op, u in col.events if op == "insert"}
        deleted = {u for op, u in col.events if op == "delete"}
        overlap = inserted & deleted
        assert not overlap, f"{len(overlap)} UUID(s) both deleted and inserted in one pass"

    def test_stale_chunks_are_still_removed(self, doc, manifest):
        """Shrinking a file must not leave its old tail chunks behind."""
        stale = "00000000-0000-5000-8000-000000000001"
        col = RecordingCollection(existing_uuids=[stale])
        index_file(col, None, manifest, "markdown", doc, root=doc.parent)

        deleted = [u for op, u in col.events if op == "delete"]
        assert stale in deleted, "a chunk no longer produced by the file was not removed"

    def test_stale_deletion_happens_after_the_insert(self, doc, manifest):
        stale = "00000000-0000-5000-8000-000000000001"
        col = RecordingCollection(existing_uuids=[stale])
        index_file(col, None, manifest, "markdown", doc, root=doc.parent)

        ops = [op for op, _ in col.events]
        assert "insert" in ops and "delete" in ops
        assert ops.index("insert") < ops.index("delete"), "stale delete ran before the insert"
