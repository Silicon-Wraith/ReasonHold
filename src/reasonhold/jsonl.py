"""The one writer for append-only JSONL logs. No code path rewrites a line."""

from __future__ import annotations

import json
import os
from pathlib import Path


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with open(path, "a+b") as fh:
        fh.seek(0, os.SEEK_END)
        if fh.tell() > 0:
            fh.seek(-1, os.SEEK_END)
            if fh.read(1) != b"\n":
                fh.write(b"\n")  # a hand edit left no trailing newline; never glue two records
        fh.write(line.encode())
        fh.flush()
        os.fsync(fh.fileno())
