"""The embedding spike's 40 questions as a benchmark (spec section 8). It informs; it does not gate."""

import re
import subprocess
from pathlib import Path

import pytest

from reasonhold.api import ReasonHold

pytestmark = pytest.mark.integration
SPIKE = Path(__file__).resolve().parents[2] / "docs/reviews/2026-10-01-embedding-spike.md"
ROW = re.compile(r"^\| (\d+) \| (.+?) \| `([^`]+)` \S+ \|")


def questions() -> list[tuple[str, str]]:
    rows = [ROW.match(line) for line in SPIKE.read_text().splitlines()]
    return [(m.group(2), m.group(3)) for m in rows if m]


def test_question_table_parses():
    assert len(questions()) == 40


def test_retrieval_benchmark(tmp_path, capsys):
    root = tmp_path / "test-ariadne"
    root.mkdir()
    archive = subprocess.run(["git", "-C", "/mnt/ml_storage/dev/projects/Ariadne", "archive", "8c5c451"],
                             check=True, capture_output=True, stdin=subprocess.DEVNULL).stdout
    subprocess.run(["tar", "-x", "-C", str(root)], input=archive, check=True)
    with ReasonHold(root) as rh:
        rh.index(out=lambda *a: None)
        ranks = []
        for question, target in questions():
            hits = rh.search_docs(question, top_k=10)["results"]
            paths = [h["file_path"] for h in hits]
            ranks.append(paths.index(target) + 1 if target in paths else None)
    hit5 = sum(1 for r in ranks if r and r <= 5) / len(ranks)
    mrr = sum(1 / r for r in ranks if r) / len(ranks)
    with capsys.disabled():
        print(f"\nretrieval benchmark: hit@5 {hit5:.1%}, MRR@10 {mrr:.2f} over {len(ranks)} questions "
              f"(spike, qwen3-embedding:0.6b: hit@5 75.0%, MRR 0.64)")
    assert len(ranks) == 40
