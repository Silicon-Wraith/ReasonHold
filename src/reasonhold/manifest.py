"""Manifest parsing for docs-rag corpus scope and area inference."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

import yaml

from config import DECISIONS_FILE, PROJECT_ROOT, SYNC_DOC_PATH


@dataclass(frozen=True)
class AreaManifest:
    name: str
    description: str
    projects: tuple[str, ...]
    docs: tuple[str, ...]
    index: tuple[str, ...]


@dataclass(frozen=True)
class Manifest:
    global_index: tuple[str, ...]
    areas: tuple[AreaManifest, ...]

    def iter_corpus_globs(self, area_names: set[str] | None = None) -> list[str]:
        selected_areas = self._select_areas(area_names)
        globs = list(self.global_index)
        for area in selected_areas:
            globs.extend(area.docs)
            globs.extend(area.index)
        if DECISIONS_FILE.exists():
            globs.append(str(DECISIONS_FILE.relative_to(PROJECT_ROOT)))
        return _dedupe(globs)

    def infer_area(self, file_path: str) -> str | None:
        for area in self.areas:
            if _matches_area(area, file_path):
                return area.name
        return None

    def infer_project(self, file_path: str) -> str | None:
        path = PurePosixPath(file_path)
        parts = path.parts
        if len(parts) >= 2 and parts[0] == "src":
            return parts[1]
        if len(parts) >= 2 and parts[0] == "tests":
            name = parts[1]
            return name[:-6] if name.endswith(".Tests") else name
        for area in self.areas:
            for project in area.projects:
                if fnmatch(file_path, f"src/{project}/**") or fnmatch(file_path, f"tests/{project}.Tests/**"):
                    return project
        return None

    def _select_areas(self, area_names: set[str] | None) -> tuple[AreaManifest, ...]:
        if not area_names:
            return self.areas
        selected = tuple(area for area in self.areas if area.name in area_names)
        missing = sorted(area_names - {area.name for area in selected})
        if missing:
            raise ValueError(f"Unknown manifest areas: {', '.join(missing)}")
        return selected


def load_manifest(path: Path | None = None) -> Manifest:
    manifest_path = path or SYNC_DOC_PATH
    if not manifest_path.exists():
        raise FileNotFoundError(f"Retrieval manifest not found: {manifest_path}")

    data = yaml.safe_load(manifest_path.read_text()) or {}
    global_section = data.get("global")
    if not isinstance(global_section, dict):
        raise ValueError("sync-doc.yaml must contain a 'global' mapping")

    global_index = _require_string_list(global_section, "global.index")
    areas_raw = data.get("areas")
    if not isinstance(areas_raw, dict):
        raise ValueError("sync-doc.yaml must contain an 'areas' mapping")

    areas: list[AreaManifest] = []
    for area_name, raw in areas_raw.items():
        if not isinstance(raw, dict):
            raise ValueError(f"Area '{area_name}' must be a mapping")
        areas.append(
            AreaManifest(
                name=area_name,
                description=str(raw.get("description", "")),
                projects=tuple(_require_string_list(raw, f"areas.{area_name}.projects")),
                docs=tuple(_require_string_list(raw, f"areas.{area_name}.docs")),
                index=tuple(_require_string_list(raw, f"areas.{area_name}.index")),
            )
        )

    return Manifest(global_index=tuple(global_index), areas=tuple(areas))


def _require_string_list(section: dict, label: str) -> list[str]:
    key = label.rsplit(".", 1)[-1]
    value = section.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list")
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{label} must contain only non-empty strings")
    return value


def _matches_area(area: AreaManifest, file_path: str) -> bool:
    for doc_path in area.docs:
        if file_path == doc_path:
            return True
    for pattern in area.index:
        if PurePosixPath(file_path).match(pattern):
            return True
    for project in area.projects:
        if file_path.startswith(f"src/{project}/"):
            return True
        if file_path.startswith(f"tests/{project}.Tests/"):
            return True
    return False


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
