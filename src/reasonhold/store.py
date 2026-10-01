"""Weaviate access: one connection factory (local or Cloud), collection
lifecycle, and per-collection metadata kept in the collection description."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

import weaviate
import weaviate.classes.config as wvc

from reasonhold.errors import ReasonHoldError, StoreUnavailable
from reasonhold.schema import collection_matches_expected_schema, collection_properties
from reasonhold.settings import WeaviateSettings, weaviate_settings_from_env

META_PREFIX = "reasonhold-meta:"


@dataclass
class CollectionMeta:
    project: str
    branch: str
    model_id: str
    dims: int
    manifest_sha256: str = ""
    authority_sha256: str = ""
    retraction_sha256: str = ""
    indexed_commit: str | None = None
    last_full_index: str | None = None

    def to_description(self) -> str:
        return META_PREFIX + json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_description(cls, text: str | None) -> "CollectionMeta | None":
        if not text or not text.startswith(META_PREFIX):
            return None
        try:
            return cls(**json.loads(text[len(META_PREFIX):]))
        except (ValueError, TypeError):
            return None


def connect(settings: WeaviateSettings | None = None) -> weaviate.WeaviateClient:
    s = settings or weaviate_settings_from_env()
    try:
        if s.cloud_url:
            key = os.environ.get(s.api_key_env, "")
            return weaviate.connect_to_weaviate_cloud(
                cluster_url=s.cloud_url, auth_credentials=weaviate.auth.AuthApiKey(key)
            )
        return weaviate.connect_to_custom(
            http_host=s.host, http_port=s.http_port, http_secure=False,
            grpc_host=s.host, grpc_port=s.grpc_port, grpc_secure=False,
        )
    except Exception as exc:  # the client raises several unrelated types on connect
        where = s.cloud_url or f"{s.host}:{s.http_port}"
        raise StoreUnavailable(f"cannot reach Weaviate at {where}: {exc}") from exc


def read_meta(client, name: str) -> CollectionMeta | None:
    if not client.collections.exists(name):
        return None
    return CollectionMeta.from_description(client.collections.get(name).config.get().description)


def write_meta(client, name: str, meta: CollectionMeta) -> None:
    client.collections.get(name).config.update(description=meta.to_description())


def create_collection(client, name: str, meta: CollectionMeta) -> None:
    client.collections.create(
        name=name,
        description=meta.to_description(),
        vectorizer_config=wvc.Configure.Vectorizer.none(),
        vector_index_config=wvc.Configure.VectorIndex.hnsw(distance_metric=wvc.VectorDistances.COSINE),
        properties=collection_properties(),
    )


def drop_collection(client, name: str) -> None:
    if client.collections.exists(name):
        client.collections.delete(name)


def ensure_collection(client, name: str, meta: CollectionMeta, recreate: bool = False) -> None:
    if not client.collections.exists(name):
        create_collection(client, name, meta)
        return
    if recreate:
        # Recreate, never reuse: delete-then-insert on the same deterministic
        # UUIDs raced Weaviate's asynchronous deletes in the seed.
        drop_collection(client, name)
        create_collection(client, name, meta)
        return
    if not collection_matches_expected_schema(client, name):
        # Drift on an incremental run is never silently repaired (R-17).
        raise ReasonHoldError(f"{name}: schema drift detected; run `reasonhold index --full` to recreate it")


def list_collections(client, prefix: str) -> list[str]:
    return sorted(n for n in client.collections.list_all(simple=True) if n.startswith(prefix))
