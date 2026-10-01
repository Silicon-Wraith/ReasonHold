import json

from helpers import FakeCollection, FakeProvider, write
from reasonhold.chunkers import chunk_pending
from reasonhold.indexer import gather_files, index_file
from reasonhold.manifest import AreaManifest, Manifest
from reasonhold.pending import make_record

MANIFEST = Manifest(global_index=(), areas=(AreaManifest(name="w", description="w", projects=("w",), docs=("a.md",), index=("*.md",)),))
AGENT = {"kind": "agent"}


def test_gather_files_excludes_only_parts_inside_the_root(tmp_path):
    root = tmp_path / "node_modules" / "repo"          # an excluded name ABOVE the root must not hide the repo
    write(root, "docs/a.md", "# A\n")
    write(root, ".worktrees/feat/docs/a.md", "# other worktree\n")
    write(root, "decisions.jsonl", "")
    files = gather_files(root, ["docs/*.md", "**/*.md", "missing.md", "decisions.jsonl"],
                         decisions_path=root / "decisions.jsonl")
    assert [(t, p.relative_to(root).as_posix()) for t, p in files] == [
        ("markdown", "docs/a.md"),
        ("decisions", "decisions.jsonl"),
    ]


def test_index_file_writes_record_id_and_relative_path(tmp_path):
    path = write(tmp_path, "decisions.jsonl",
                 json.dumps({"topic": "a", "decision": "d", "rationale": "r", "datetime": "t1"}) + "\n")
    col = FakeCollection()
    assert index_file(col, FakeProvider(), MANIFEST, "decisions", path, root=tmp_path) == 1
    (obj,) = col.objects.values()
    assert obj.properties["file_path"] == "decisions.jsonl"
    assert obj.properties["record_id"].startswith("dec-")


def test_pending_file_chunks_only_open_records():
    cand = make_record("candidate_binding", {"target": "t", "reads": ["a.md"], "validates_against": ["src/"],
                                             "reason": "r"}, AGENT, datetime_="t1")
    closed = make_record("conflict", {"doc_a": "a.md", "doc_b": "b.md", "paths": [], "claim": "c",
                                      "evidence_a": "x", "evidence_b": "y"}, AGENT, datetime_="t2")
    res = make_record("resolution", {"resolves": [closed["id"]], "outcome": "resolved"}, AGENT, datetime_="t3")
    alias = make_record("path_alias", {"old_path": "a.md", "new_path": "b.md"}, AGENT, datetime_="t4")
    text = "".join(json.dumps(r) + "\n" for r in (cand, closed, res, alias))
    chunks = chunk_pending(text, "reasonhold.pending.jsonl")
    assert [c["record_id"] for c in chunks] == [cand["id"]]
    assert chunks[0]["authority_level"] == "pending" and "Candidate binding: t" in chunks[0]["content"]
