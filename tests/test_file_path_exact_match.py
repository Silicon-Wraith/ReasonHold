"""file_path must match exactly, or indexing one file deletes another.

file_path was declared as a text property with WORD tokenization, so
Filter.by_property("file_path").equal(X) performs token containment rather than
string equality. Measured against the live index:

    equal("docs/specs/worker-design.md")
        also matched docs/specs/2026-03-16-analysis-worker-design.md
    equal("docs/architecture/architecture.md")
        also matched every other file in docs/architecture/
    equal("src/__init__.py")
        also matched every __init__.py under src/

Both delete paths filter on file_path, so indexing a file whose path tokens are
a subset of another file's path deleted that other file's chunks. Three
consecutive --full runs each lost exactly 159 objects across the same 20 files,
and Weaviate's own shard log confirmed it: tombstones_in_cycle 159 on a
freshly created shard.

Two defences, because the consequence is silent data loss: file_path is
declared with FIELD tokenization so equality is exact, and the delete path
re-checks the exact string before removing anything. Note that
collection_matches_expected_schema compares property NAMES only, so a
tokenization regression would not register as drift — the second defence is
what would catch it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import index as index_mod
import schema as schema_mod
import weaviate.classes.config as wvc


class TestFilePathTokenization:
    def test_file_path_uses_exact_field_tokenization(self):
        props = {p.name: p for p in schema_mod._collection_properties()}
        assert "file_path" in props
        assert props["file_path"].tokenization == wvc.Tokenization.FIELD, (
            "file_path is an identifier, not prose — WORD tokenization makes "
            "equality filters match by token containment and delete other files"
        )

    def test_identifier_properties_are_not_word_tokenized(self):
        """Any property used as an equality key needs exact matching."""
        props = {p.name: p for p in schema_mod._collection_properties()}
        for name in ("file_path",):
            assert props[name].tokenization != wvc.Tokenization.WORD, name


class _Obj:
    def __init__(self, uuid: str, file_path: str) -> None:
        self.uuid = uuid
        self.properties = {"file_path": file_path}


class OverMatchingCollection:
    """Simulates the WORD-tokenization filter returning other files' objects."""

    def __init__(self, returned: list[_Obj]) -> None:
        self._returned = returned
        self.deleted: list[str] = []

    class _Query:
        def __init__(self, outer):
            self._outer = outer

        def fetch_objects(self, **kwargs):
            outer = self._outer

            class R:
                objects = outer._returned

            return R()

    class _Data:
        def __init__(self, outer):
            self._outer = outer

        def delete_by_id(self, uuid):
            self._outer.deleted.append(str(uuid))

    @property
    def query(self):
        return OverMatchingCollection._Query(self)

    @property
    def data(self):
        return OverMatchingCollection._Data(self)


class TestDeleteRechecksExactPath:
    def test_never_deletes_a_chunk_belonging_to_another_file(self):
        """The defence that would have caught this even with WORD tokenization."""
        target = "docs/specs/worker-design.md"
        col = OverMatchingCollection(
            [
                _Obj("11111111-1111-5111-8111-111111111111", target),
                _Obj("22222222-2222-5222-8222-222222222222", "docs/specs/2026-03-16-analysis-worker-design.md"),
                _Obj("33333333-3333-5333-8333-333333333333", "docs/architecture/analysis-layer.md"),
            ]
        )

        index_mod._delete_stale_chunks(col, target, keep=set())

        assert "22222222-2222-5222-8222-222222222222" not in col.deleted
        assert "33333333-3333-5333-8333-333333333333" not in col.deleted

    def test_still_removes_this_file_s_stale_chunks(self):
        target = "docs/specs/worker-design.md"
        stale = "11111111-1111-5111-8111-111111111111"
        keep_me = "44444444-4444-5444-8444-444444444444"
        col = OverMatchingCollection([_Obj(stale, target), _Obj(keep_me, target)])

        index_mod._delete_stale_chunks(col, target, keep={keep_me})

        assert col.deleted == [stale]

    def test_delete_file_chunks_is_also_scoped_to_the_exact_path(self):
        """clean_orphans uses this path; it must not take neighbours with it."""
        target = "src/__init__.py"
        col = OverMatchingCollection(
            [
                _Obj("aaaaaaaa-aaaa-5aaa-8aaa-aaaaaaaaaaaa", target),
                _Obj("bbbbbbbb-bbbb-5bbb-8bbb-bbbbbbbbbbbb", "src/api/__init__.py"),
            ]
        )

        index_mod.delete_file_chunks(col, target)

        assert col.deleted == ["aaaaaaaa-aaaa-5aaa-8aaa-aaaaaaaaaaaa"]
