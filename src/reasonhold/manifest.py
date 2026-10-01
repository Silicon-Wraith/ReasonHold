"""Manifest parsing for docs-rag corpus scope and area inference."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

import yaml

from reasonhold.errors import ManifestInvalid


@dataclass(frozen=True)
class CheckSpec:
    name: str
    description: str
    mode: str  # "index" or "fs"
    reads: tuple[str, ...]
    validates_against: tuple[str, ...]


@dataclass(frozen=True)
class AreaManifest:
    name: str
    description: str
    projects: tuple[str, ...]
    docs: tuple[str, ...]
    index: tuple[str, ...]
    checks: tuple[str, ...] = ()


@dataclass(frozen=True)
class Manifest:
    global_index: tuple[str, ...]
    areas: tuple[AreaManifest, ...]
    global_docs: tuple[str, ...] = ()
    global_archival: tuple[str, ...] = ()
    global_checks: tuple[str, ...] = ()
    checks: tuple[CheckSpec, ...] = ()
    project_raw: dict = field(default_factory=dict)
    authority_raw: object = None

    def iter_corpus_globs(self, area_names: set[str] | None = None, extra: Sequence[str] = ()) -> list[str]:
        selected_areas = self._select_areas(area_names)
        globs = [*self.global_index, *self.global_docs]
        for area in selected_areas:
            globs.extend(area.docs)
            globs.extend(area.index)
        globs.extend(extra)
        return _dedupe(globs)

    def check(self, name: str) -> CheckSpec | None:
        return next((c for c in self.checks if c.name == name), None)

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
            raise ManifestInvalid(f"Unknown manifest areas: {', '.join(missing)}")
        return selected


def load_manifest(path: Path) -> Manifest:
    if not path.exists():
        raise ManifestInvalid(f"Retrieval manifest not found: {path}")
    name = path.name
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ManifestInvalid(f"{name}: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestInvalid(f"{name} must contain a mapping")

    global_section = data.get("global")
    if not isinstance(global_section, dict):
        raise ManifestInvalid(f"{name} must contain a 'global' mapping")

    global_index = _require_string_list(global_section, "global.index")
    areas_raw = data.get("areas")
    if not isinstance(areas_raw, dict):
        raise ManifestInvalid(f"{name} must contain an 'areas' mapping")

    areas: list[AreaManifest] = []
    for area_name, raw in areas_raw.items():
        if not isinstance(raw, dict):
            raise ManifestInvalid(f"Area '{area_name}' must be a mapping")
        areas.append(
            AreaManifest(
                name=area_name,
                description=str(raw.get("description", "")),
                projects=tuple(_require_string_list(raw, f"areas.{area_name}.projects")),
                docs=tuple(_require_string_list(raw, f"areas.{area_name}.docs")),
                index=tuple(_require_string_list(raw, f"areas.{area_name}.index")),
                checks=_optional_string_list(raw, "checks", f"areas.{area_name}.checks", paths=False),
            )
        )

    project_raw = data.get("project") or {}
    if not isinstance(project_raw, dict):
        raise ManifestInvalid("'project' must be a mapping")

    return Manifest(
        global_index=tuple(global_index),
        areas=tuple(areas),
        global_docs=_optional_string_list(global_section, "docs", "global.docs"),
        global_archival=_optional_string_list(global_section, "archival", "global.archival"),
        global_checks=_optional_string_list(global_section, "checks", "global.checks", paths=False),
        checks=_parse_checks(data.get("checks"), name),
        project_raw=project_raw,
        authority_raw=data.get("authority"),
    )


def _safe(value: str, label: str) -> str:
    if value.startswith("/") or value.startswith("..") or "/../" in value or value.endswith("/.."):
        raise ManifestInvalid(f"{label}: path {value!r} must be relative to the repository and stay inside it")
    return value


def _optional_string_list(section: dict, key: str, label: str, *, paths: bool = True) -> tuple[str, ...]:
    value = section.get(key)
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise ManifestInvalid(f"{label} must be a list of non-empty strings")
    return tuple(_safe(v, label) for v in value) if paths else tuple(value)


def _parse_checks(raw: object, name: str) -> tuple[CheckSpec, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        raise ManifestInvalid(f"{name}: 'checks' must be a mapping")
    checks = []
    for check_name, body in raw.items():
        label = f"checks.{check_name}"
        if not isinstance(body, dict):
            raise ManifestInvalid(f"{label} must be a mapping")
        mode = body.get("mode", "index")
        if mode not in ("index", "fs"):
            raise ManifestInvalid(f"{label}.mode must be 'index' or 'fs'")
        checks.append(
            CheckSpec(
                name=str(check_name),
                description=str(body.get("description", "")),
                mode=mode,
                reads=_optional_string_list(body, "reads", f"{label}.reads"),
                validates_against=_optional_string_list(body, "validates_against", f"{label}.validates_against"),
            )
        )
    return tuple(checks)


def _require_string_list(section: dict, label: str) -> list[str]:
    key = label.rsplit(".", 1)[-1]
    value = section.get(key)
    if not isinstance(value, list) or not value:
        raise ManifestInvalid(f"{label} must be a non-empty list")
    if not all(isinstance(item, str) and item for item in value):
        raise ManifestInvalid(f"{label} must contain only non-empty strings")
    return [_safe(item, label) for item in value]


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
