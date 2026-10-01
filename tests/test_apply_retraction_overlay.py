"""Tests for apply_retraction_to_chunks filtering and update behavior."""

from dataclasses import dataclass, field
from pathlib import Path

import pytest

pytest.importorskip("weaviate")

from reasonhold.server import apply_retraction_to_chunks


@dataclass
class FakeObj:
    uuid: str
    properties: dict


@dataclass
class FakeDataAPI:
    updates: list = field(default_factory=list)

    def update(self, uuid: str, properties: dict):
        self.updates.append((uuid, dict(properties)))


@dataclass
class FakeCollection:
    objs: list
    data: FakeDataAPI = field(default_factory=FakeDataAPI)

    def iterator(self, include_vector=False):
        return iter(self.objs)


@dataclass
class FakeCollections:
    collection: FakeCollection

    def get(self, name):
        return self.collection


@dataclass
class FakeClient:
    collection: FakeCollection

    @property
    def collections(self):
        return FakeCollections(self.collection)


def _make_client(objs):
    return FakeClient(FakeCollection(objs=objs))


class TestApplyRetractionToChunks:
    def test_updates_all_matching_chunks(self):
        objs = [
            FakeObj("u1", {"file_path": "a.md", "chunk_type": "markdown_section", "section_heading": "Overview"}),
            FakeObj("u2", {"file_path": "a.md", "chunk_type": "markdown_section", "section_heading": "Details"}),
            FakeObj("u3", {"file_path": "b.md", "chunk_type": "markdown_section", "section_heading": "Overview"}),
        ]
        client = _make_client(objs)
        updated = apply_retraction_to_chunks(
            client=client,
            path="a.md",
            retraction_summary="retracted",
            retraction_decision="topic-t",
            retraction_date="2026-04-22T10:00:00+00:00",
        )
        assert updated == 2
        updated_uuids = {u for (u, _) in client.collection.data.updates}
        assert updated_uuids == {"u1", "u2"}
        for _, props in client.collection.data.updates:
            assert props == {
                "retraction_summary": "retracted",
                "retraction_decision": "topic-t",
                "retraction_date": "2026-04-22T10:00:00+00:00",
            }

    def test_skips_non_matching_path(self):
        objs = [
            FakeObj("u1", {"file_path": "a.md", "chunk_type": "markdown_section", "section_heading": "x"}),
        ]
        client = _make_client(objs)
        assert (
            apply_retraction_to_chunks(
                client=client,
                path="b.md",
                retraction_summary="r",
                retraction_decision="t",
                retraction_date="d",
            )
            == 0
        )
        assert client.collection.data.updates == []

    def test_never_annotates_decision_chunks(self):
        objs = [
            FakeObj("u1", {"file_path": "docs-rag/decisions.jsonl", "chunk_type": "decision", "section_heading": "t"}),
        ]
        client = _make_client(objs)
        assert (
            apply_retraction_to_chunks(
                client=client,
                path="docs-rag/decisions.jsonl",
                retraction_summary="r",
                retraction_decision="t",
                retraction_date="d",
            )
            == 0
        )

    def test_section_anchor_matches_heading_substring(self):
        objs = [
            FakeObj(
                "u1",
                {
                    "file_path": "doc.md",
                    "chunk_type": "markdown_section",
                    "section_heading": "3.2 Generation Authority",
                },
            ),
            FakeObj(
                "u2", {"file_path": "doc.md", "chunk_type": "markdown_section", "section_heading": "4.1 Other Section"}
            ),
        ]
        client = _make_client(objs)
        updated = apply_retraction_to_chunks(
            client=client,
            path="doc.md#3.2",
            retraction_summary="r",
            retraction_decision="t",
            retraction_date="d",
        )
        assert updated == 1
        assert client.collection.data.updates[0][0] == "u1"

    def test_section_anchor_misses_when_no_heading(self):
        objs = [
            FakeObj("u1", {"file_path": "doc.md", "chunk_type": "markdown_section", "section_heading": ""}),
        ]
        client = _make_client(objs)
        assert (
            apply_retraction_to_chunks(
                client=client,
                path="doc.md#3.2",
                retraction_summary="r",
                retraction_decision="t",
                retraction_date="d",
            )
            == 0
        )
