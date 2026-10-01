from reasonhold.schema import EXPECTED_PROPERTIES
from reasonhold.store import CollectionMeta, ensure_collection


def test_meta_round_trip():
    meta = CollectionMeta("ariadne", "main", "ollama:m", 1024, "a", "b", "c", "deadbeef", "2026-10-01T00:00:00+00:00")
    assert CollectionMeta.from_description(meta.to_description()) == meta
    assert CollectionMeta.from_description("Some human description") is None
    assert CollectionMeta.from_description(None) is None


def test_record_id_property_added():
    assert "record_id" in EXPECTED_PROPERTIES and "file_path" in EXPECTED_PROPERTIES


class FakeCollections:
    def __init__(self, existing):
        self.names = set(existing)
        self.calls = []

    def exists(self, name):
        return name in self.names


class FakeClient:
    def __init__(self, existing=()):
        self.collections = FakeCollections(existing)


def test_ensure_creates_missing(monkeypatch):
    import reasonhold.store as store

    calls = []
    monkeypatch.setattr(store, "create_collection", lambda c, n, m: calls.append(("create", n)))
    ensure_collection(FakeClient(), "RH_X__main", CollectionMeta("x", "main", "ollama:m", 4))
    assert calls == [("create", "RH_X__main")]


def test_ensure_recreate_drops_then_creates(monkeypatch):
    import reasonhold.store as store

    calls = []
    monkeypatch.setattr(store, "drop_collection", lambda c, n: calls.append(("drop", n)))
    monkeypatch.setattr(store, "create_collection", lambda c, n, m: calls.append(("create", n)))
    ensure_collection(FakeClient({"RH_X__main"}), "RH_X__main", CollectionMeta("x", "main", "ollama:m", 4), recreate=True)
    assert calls == [("drop", "RH_X__main"), ("create", "RH_X__main")]
