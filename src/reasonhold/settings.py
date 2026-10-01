"""Weaviate connection settings. Environment only: they describe the machine,
not the project, so they never live in the committed manifest."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class WeaviateSettings:
    host: str = "localhost"
    http_port: int = 8081
    grpc_port: int = 50052
    cloud_url: str | None = None
    api_key_env: str = "WEAVIATE_API_KEY"


def _get(env: Mapping[str, str], name: str, default: str | None) -> str | None:
    return env.get(f"REASONHOLD_{name}") or env.get(f"DOCS_RAG_{name}") or default


def weaviate_settings_from_env(environ: Mapping[str, str] | None = None) -> WeaviateSettings:
    env = os.environ if environ is None else environ
    return WeaviateSettings(
        host=_get(env, "WEAVIATE_HOST", "localhost"),
        http_port=int(_get(env, "WEAVIATE_PORT", "8081")),
        grpc_port=int(_get(env, "WEAVIATE_GRPC_PORT", "50052")),
        cloud_url=env.get("REASONHOLD_WEAVIATE_CLOUD_URL") or None,
        api_key_env=env.get("REASONHOLD_WEAVIATE_API_KEY_ENV") or "WEAVIATE_API_KEY",
    )
