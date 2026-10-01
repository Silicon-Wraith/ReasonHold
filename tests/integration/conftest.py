import socket
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tests/helpers.py

from helpers import MINIMAL_MANIFEST, make_repo  # noqa: E402
from reasonhold.store import connect, drop_collection, list_collections  # noqa: E402

pytestmark = pytest.mark.integration


def _up(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session", autouse=True)
def services():
    missing = [name for name, port in (("Weaviate", 8081), ("Ollama", 11434)) if not _up("localhost", port)]
    if missing:
        pytest.skip(f"integration services not reachable: {', '.join(missing)}")


@pytest.fixture(autouse=True)
def cleanup(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    yield
    client = connect()
    try:
        for name in list_collections(client, "RH_Test_"):
            drop_collection(client, name)
    finally:
        client.close()


@pytest.fixture
def live_repo(tmp_path):
    project_id = f"test-{uuid.uuid4().hex[:8]}"
    return make_repo(tmp_path / "repo", MINIMAL_MANIFEST + f"project:\n  id: {project_id}\n")
