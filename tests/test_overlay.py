import json

from reasonhold.overlay import load_retraction_overlay, retraction_for_chunk


def dump(path, *records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


RETRACT = {"topic": "a", "decision": "d", "rationale": "r", "datetime": "t1",
           "supersedes": [{"path": "docs/old.md#Queue", "retraction_summary": "LIFO now"}]}


def test_overlay_follows_path_alias(tmp_path):
    overlay = load_retraction_overlay(dump(tmp_path / "d.jsonl", RETRACT), {"docs/old.md": "docs/new.md"})
    chunk = {"file_path": "docs/new.md", "section_heading": "Queue rules"}
    assert retraction_for_chunk(chunk, overlay)["retraction_summary"] == "LIFO now"
    assert retraction_for_chunk({"file_path": "docs/old.md", "section_heading": "Queue"}, overlay)


def test_overlay_ignores_records_retired_by_supersedes_records(tmp_path):
    from reasonhold.decisions import decision_id

    retire = {"topic": "b", "decision": "d", "rationale": "r", "datetime": "t2",
              "supersedes_records": [decision_id("a", "t1")]}
    assert load_retraction_overlay(dump(tmp_path / "d.jsonl", RETRACT, retire)) == {}
