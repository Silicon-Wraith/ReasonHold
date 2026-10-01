"""The project ReasonHold answers about: one repository root and its manifest."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from reasonhold.authority import DEFAULT_LADDER, AuthorityRule, parse_ladder
from reasonhold.errors import ManifestInvalid
from reasonhold.manifest import Manifest, load_manifest

MANIFEST_NAMES = ("reasonhold.yaml", "sync-doc.yaml")
LEGACY_DECISIONS = "docs-rag/decisions.jsonl"


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str = "ollama"
    model: str = "qwen3-embedding:0.6b"
    base_url: str = "http://localhost:11434"
    api_key_env: str | None = None


@dataclass(frozen=True)
class Project:
    root: Path
    manifest_path: Path
    manifest: Manifest
    id: str
    decisions_path: Path
    pending_path: Path
    embedding: EmbeddingConfig
    branch_isolation: bool
    ladder: tuple[AuthorityRule, ...]

    @property
    def manifest_rel(self) -> str:
        return self.rel(self.manifest_path)

    @property
    def decisions_rel(self) -> str:
        return self.rel(self.decisions_path)

    @property
    def pending_rel(self) -> str:
        return self.rel(self.pending_path)

    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def corpus_globs(self, area_names: set[str] | None = None) -> list[str]:
        return self.manifest.iter_corpus_globs(area_names, extra=[self.decisions_rel])

    @classmethod
    def load(cls, root: Path | str | None = None) -> "Project":
        base = Path(root or Path.cwd()).resolve()
        manifest_path = next((base / n for n in MANIFEST_NAMES if (base / n).is_file()), None)
        if manifest_path is None:
            raise ManifestInvalid(f"no reasonhold.yaml or sync-doc.yaml in {base}")
        manifest = load_manifest(manifest_path)
        raw = manifest.project_raw
        if not isinstance(raw, dict):
            raise ManifestInvalid("'project' must be a mapping")

        project_id = slug(str(raw.get("id") or base.name))
        decisions_rel = raw.get("decisions")
        if not decisions_rel:
            legacy = manifest_path.name == "sync-doc.yaml" and (base / LEGACY_DECISIONS).is_file()
            decisions_rel = LEGACY_DECISIONS if legacy else "decisions.jsonl"
        pending_rel = raw.get("pending") or (manifest_path.parent / "reasonhold.pending.jsonl").relative_to(base).as_posix()
        for label, value in (("project.decisions", decisions_rel), ("project.pending", pending_rel)):
            if not isinstance(value, str) or value.startswith("/") or ".." in Path(value).parts:
                raise ManifestInvalid(f"{label} must be a relative path inside the repository")

        emb = raw.get("embedding") or {}
        if not isinstance(emb, dict):
            raise ManifestInvalid("project.embedding must be a mapping")
        defaults = EmbeddingConfig()
        embedding = EmbeddingConfig(
            provider=str(emb.get("provider", defaults.provider)),
            model=str(emb.get("model", defaults.model)),
            base_url=str(emb.get("base_url", defaults.base_url)),
            api_key_env=emb.get("api_key_env"),
        )
        if embedding.provider not in ("ollama", "openai_compatible"):
            raise ManifestInvalid("project.embedding.provider must be 'ollama' or 'openai_compatible'")

        index_cfg = raw.get("index") or {}
        ladder = DEFAULT_LADDER if manifest.authority_raw is None else parse_ladder(manifest.authority_raw)
        return cls(
            root=base,
            manifest_path=manifest_path,
            manifest=manifest,
            id=project_id,
            decisions_path=base / decisions_rel,
            pending_path=base / pending_rel,
            embedding=embedding,
            branch_isolation=bool(index_cfg.get("branch_isolation", True)),
            ladder=ladder,
        )


def slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise ManifestInvalid("project id is empty after normalization")
    return slug
