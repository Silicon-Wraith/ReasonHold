from types import SimpleNamespace

import pytest

from helpers import FakeProvider
from reasonhold.search import search_decisions, search_docs


class VectorCollection:
    def __init__(self, hits):
        self.hits, self.calls = hits, []
        self.query = SimpleNamespace(near_vector=self.near_vector)

    def near_vector(self, near_vector, limit, filters=None, return_metadata=None):
        self.calls.append({"limit": limit, "filters": filters})
        objs = [SimpleNamespace(properties=p, metadata=SimpleNamespace(distance=d)) for p, d in self.hits]
        return SimpleNamespace(objects=objs[:limit])


def hit(path, level, **extra):
    return {"file_path": path, "authority_level": level, "document_kind": "", "chunk_type": "markdown_section",
            "file_type": "markdown", "section_heading": "", "type_name": "", "member_name": "", "content": "c", **extra}


def test_search_docs_reranks_with_ladder_weights():
    col = VectorCollection([(hit("a.md", "low"), 0.30), (hit("b.md", "high"), 0.31)])
    out = search_docs(col, FakeProvider(), "anything", authority_weights={"high": 0.1, "low": 0.0})
    assert [r["file_path"] for r in out] == ["b.md", "a.md"]
    out = search_docs(col, FakeProvider(), "anything", authority_weights={"high": 0.0, "low": 0.1})
    assert [r["file_path"] for r in out] == ["a.md", "b.md"]


def test_search_docs_carries_retraction_kind_and_record_id():
    col = VectorCollection([
        (hit("docs/x.md", "architecture", retraction_summary="now LIFO", retraction_decision="q", retraction_date="d"), 0.1),
        (hit("src/a.py", "implementation", file_type="python", chunk_type="python_function"), 0.2),
        (hit("decisions.jsonl", "decision", file_type="decisions", chunk_type="decision", record_id="dec-1"), 0.3),
    ])
    out = {r["file_path"]: r for r in search_docs(col, FakeProvider(), "q", authority_weights={})}
    assert out["docs/x.md"]["retraction_summary"] == "now LIFO" and out["docs/x.md"]["kind"] == "document"
    assert out["src/a.py"]["kind"] == "code"
    assert out["decisions.jsonl"]["kind"] == "decision" and out["decisions.jsonl"]["record_id"] == "dec-1"


def test_search_decisions_filters_on_the_status_property():
    props = {"content": "Decision: d\nRationale: r\nStatus: active", "section_heading": "t",
             "record_id": "dec-1", "decision_status": "superseded"}
    col = VectorCollection([(props, 0.2)])
    (r,) = search_decisions(col, FakeProvider(), "q", status="superseded")
    assert r["id"] == "dec-1" and r["status"] == "superseded"     # the property wins over the text
    assert [f.target for f in col.calls[0]["filters"].filters] == ["chunk_type", "decision_status"]
    search_decisions(col, FakeProvider(), "q", status="all")
    assert col.calls[1]["filters"].target == "chunk_type"
    with pytest.raises(ValueError):
        search_decisions(col, FakeProvider(), "q", status="retired")
