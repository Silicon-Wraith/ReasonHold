import pytest

from reasonhold.embedding import OllamaProvider, OpenAICompatibleProvider, check_model, make_provider
from reasonhold.errors import ModelMismatch, StoreUnavailable
from reasonhold.project import EmbeddingConfig
from reasonhold.store import CollectionMeta


class FakePost:
    def __init__(self, dims=4, fail=False):
        self.dims, self.fail, self.calls = dims, fail, []

    def __call__(self, url, payload):
        self.calls.append((url, payload))
        if self.fail:
            raise StoreUnavailable(f"cannot reach {url}")
        texts = payload.get("input")
        if "/api/embed" in url:
            return {"embeddings": [[0.1] * self.dims for _ in texts]}
        return {"data": [{"embedding": [0.1] * self.dims, "index": i} for i, _ in enumerate(texts)]}


def test_ollama_batches_and_truncates():
    post = FakePost()
    p = OllamaProvider("qwen3-embedding:0.6b", "http://h:11434", batch_size=2, char_budget=5, post=post)
    out = p.embed(["abcdefgh", "b", "c"])
    assert len(out) == 3 and len(post.calls) == 2
    assert post.calls[0][0] == "http://h:11434/api/embed"
    assert post.calls[0][1]["input"] == ["abcde", "b"]
    assert p.model_id == "ollama:qwen3-embedding:0.6b"


def test_openai_compatible_shape():
    post = FakePost(dims=3)
    p = OpenAICompatibleProvider("m", "http://h/v1", post=post)
    assert p.embed(["x"]) == [[0.1, 0.1, 0.1]] and post.calls[0][0] == "http://h/v1/embeddings"
    assert p.model_id == "openai_compatible:http://h/v1|m"


def test_dims_probed_once():
    post = FakePost(dims=7)
    p = OllamaProvider("m", "http://h", post=post)
    assert p.dims == 7 and p.dims == 7 and len(post.calls) == 1


def test_unreachable_provider_is_store_unavailable():
    with pytest.raises(StoreUnavailable):
        OllamaProvider("m", "http://h", post=FakePost(fail=True)).embed(["x"])


def test_make_provider():
    assert isinstance(make_provider(EmbeddingConfig()), OllamaProvider)
    assert isinstance(make_provider(EmbeddingConfig("openai_compatible", "m", "http://h/v1")), OpenAICompatibleProvider)


def test_model_guard():
    p = OllamaProvider("m", "http://h", post=FakePost(dims=4))
    check_model(None, p)
    check_model(CollectionMeta("p", "main", "ollama:m", 4), p)
    with pytest.raises(ModelMismatch, match="index --full"):
        check_model(CollectionMeta("p", "main", "ollama:other", 4), p)
    with pytest.raises(ModelMismatch):
        check_model(CollectionMeta("p", "main", "ollama:m", 8), p)
