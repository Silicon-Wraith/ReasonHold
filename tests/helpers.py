"""Test doubles and repository builders shared by the unit tests. No network."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path
from types import SimpleNamespace

from reasonhold.errors import StoreUnavailable
from reasonhold.schema import EXPECTED_PROPERTIES

MINIMAL_MANIFEST = """\
global:
  docs: [docs/architecture/overview.md]
  index: [AGENTS.md]
areas:
  worker:
    description: Worker
    projects: [worker]
    docs: [docs/specs/worker.md]
    index: ["docs/specs/*.md", "src/worker/*.py"]
    checks: [worker-contract]
checks:
  worker-contract:
    description: Worker follows its spec
    mode: index
    reads: [docs/specs/worker.md]
    validates_against: [src/worker/]
"""


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))
    return path


def git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL
    )
    return done.stdout.strip()


def make_repo(root: Path, manifest: str = MINIMAL_MANIFEST, *, commit: bool = True) -> Path:
    write(root, "sync-doc.yaml", manifest)
    write(root, "AGENTS.md", "# Agents\n")
    write(root, "docs/architecture/overview.md", "# Overview\n\n## Queue\n\nThe queue is FIFO.\n")
    write(root, "docs/specs/worker.md", "# Worker\n\n## Retries\n\nRetry three times.\n")
    write(root, "src/worker/main.py", "def run():\n    return 1\n")
    write(root, "decisions.jsonl", "")
    if commit:
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.email", "t@example.com")
        git(root, "config", "user.name", "t")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "initial")
    return root


class FakeProvider:
    model_id = "ollama:fake"

    def __init__(self, dims: int = 4, fail: bool = False):
        self._dims, self.fail, self.calls = dims, fail, []

    @property
    def dims(self) -> int:
        return self._dims

    def embed(self, texts):
        self.calls.append(list(texts))
        if self.fail:
            raise StoreUnavailable("embedding request to http://fake/api/embed failed: connection refused")
        return [[0.1] * self._dims for _ in texts]


class _Obj(SimpleNamespace):
    pass


class _Data:
    def __init__(self, owner):
        self.owner = owner

    def insert(self, properties, vector=None, uuid=None):
        if self.owner.fail_inserts:
            raise RuntimeError("insert failed")
        self.owner.objects[str(uuid)] = _Obj(uuid=str(uuid), properties=dict(properties), vector=vector)
        return uuid

    def insert_many(self, objects):
        for obj in objects:
            self.insert(obj.properties, obj.vector, obj.uuid)
        return SimpleNamespace(has_errors=False, errors={})

    def update(self, uuid, properties):
        self.owner.objects[str(uuid)].properties.update(properties)

    def delete_by_id(self, uuid):
        self.owner.objects.pop(str(uuid), None)


class _Config:
    def __init__(self, owner):
        self.owner = owner

    def get(self, simple=True):
        props = [SimpleNamespace(name=n) for n in sorted(EXPECTED_PROPERTIES)]
        return SimpleNamespace(description=self.owner.description, properties=props)

    def update(self, description=None):
        self.owner.description = description


class FakeCollection:
    def __init__(self, name="RH_T__main", description=None):
        self.name, self.description = name, description
        self.objects: dict[str, _Obj] = {}
        self.fail_inserts = False
        self.data = _Data(self)
        self.config = _Config(self)
        self.aggregate = SimpleNamespace(over_all=lambda total_count=True: SimpleNamespace(total_count=len(self.objects)))
        # Filters are ignored: every seed caller of fetch_objects re-checks the exact
        # file_path itself, so returning everything is a faithful double.
        self.query = SimpleNamespace(fetch_objects=lambda **kw: SimpleNamespace(objects=list(self.objects.values())))

    def iterator(self, include_vector=False, return_properties=None):
        return iter(list(self.objects.values()))

    def add(self, uuid, **properties):
        self.objects[uuid] = _Obj(uuid=uuid, properties=properties, vector=None)


class _Collections:
    def __init__(self, owner):
        self.owner = owner

    def exists(self, name):
        return name in self.owner.store

    def get(self, name):
        return self.owner.store[name]

    def create(self, name, description=None, **_):
        self.owner.store[name] = FakeCollection(name, description)
        self.owner.created.append(name)

    def delete(self, name):
        self.owner.store.pop(name, None)
        self.owner.deleted.append(name)

    def list_all(self, simple=True):
        return {name: None for name in self.owner.store}


class FakeClient:
    def __init__(self, *collections: FakeCollection):
        self.store = {c.name: c for c in collections}
        self.created: list[str] = []
        self.deleted: list[str] = []
        self.collections = _Collections(self)
        self.closed = False

    def close(self):
        self.closed = True
