"""Embedding providers (R-15) and the model guard (R-16). Plain HTTP, no SDKs."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Protocol

from reasonhold.errors import ModelMismatch, StoreUnavailable
from reasonhold.project import EmbeddingConfig
from reasonhold.store import CollectionMeta

Post = Callable[[str, dict], dict]


def _http_post(timeout: float, headers: dict[str, str] | None = None) -> Post:
    def post(url: str, payload: dict) -> dict:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", **(headers or {})}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise StoreUnavailable(f"embedding request to {url} failed: {exc}") from exc

    return post


class EmbeddingProvider(Protocol):
    model_id: str

    @property
    def dims(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class _Base:
    batch_size: int
    char_budget: int
    _dims: int | None = None

    def _batch_embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            out.extend(self._batch_embed([t[: self.char_budget] for t in texts[i : i + self.batch_size]]))
        return out

    @property
    def dims(self) -> int:
        if self._dims is None:
            self._dims = len(self.embed(["dimension probe"])[0])
        return self._dims


class OllamaProvider(_Base):
    def __init__(self, model, base_url, batch_size=8, char_budget=12000, timeout=120.0, post=None):
        self.model, self.base_url = model, base_url.rstrip("/")
        self.batch_size, self.char_budget = batch_size, char_budget
        self.model_id = f"ollama:{model}"
        self._post = post or _http_post(timeout)

    def _batch_embed(self, texts):
        return self._post(f"{self.base_url}/api/embed", {"model": self.model, "input": texts, "truncate": True})["embeddings"]


class OpenAICompatibleProvider(_Base):
    def __init__(self, model, base_url, api_key_env=None, batch_size=32, char_budget=12000, timeout=120.0, post=None):
        self.model, self.base_url = model, base_url.rstrip("/")
        self.batch_size, self.char_budget = batch_size, char_budget
        self.model_id = f"openai_compatible:{self.base_url}|{model}"
        headers = {"Authorization": f"Bearer {os.environ[api_key_env]}"} if api_key_env and os.environ.get(api_key_env) else None
        self._post = post or _http_post(timeout, headers)

    def _batch_embed(self, texts):
        data = self._post(f"{self.base_url}/embeddings", {"model": self.model, "input": texts})["data"]
        return [row["embedding"] for row in sorted(data, key=lambda r: r["index"])]


def make_provider(config: EmbeddingConfig) -> EmbeddingProvider:
    if config.provider == "openai_compatible":
        return OpenAICompatibleProvider(config.model, config.base_url, config.api_key_env)
    return OllamaProvider(config.model, config.base_url)


def check_model(meta: CollectionMeta | None, provider: EmbeddingProvider) -> None:
    if meta is None:
        return
    if meta.model_id != provider.model_id or meta.dims != provider.dims:
        raise ModelMismatch(
            f"index built with {meta.model_id} ({meta.dims} dims) but the project is configured for "
            f"{provider.model_id} ({provider.dims} dims); run `reasonhold index --full`"
        )
