from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from sharedrive.models import CATALOG_PROFILE, DriveCatalog


def _load_document(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"Descriptor '{path}' must contain an object.")
    return data


def _first_source(entry: dict[str, Any]) -> dict[str, Any]:
    sources = entry.get("sources")
    if isinstance(sources, list) and sources and isinstance(sources[0], dict):
        return sources[0]
    return {}


def _resource(entry: dict[str, Any]) -> dict[str, Any]:
    source = _first_source(entry)
    remote_path = source.get("path") or entry.get("path")
    cache = entry.get("_cache") or entry.get("path")
    migrated = {
        key: value
        for key, value in entry.items()
        if key not in {"sources", "syncTarget", "targets", "target", "resources"}
    }
    migrated["path"] = remote_path
    if cache:
        migrated["_cache"] = cache
    migrated["serviceType"] = entry.get("serviceType") or source.get("serviceType")
    migrated["entityType"] = entry.get("entityType") or source.get("entityType") or "File"
    return {key: value for key, value in migrated.items() if value is not None}


def _catalog(entry: dict[str, Any]) -> dict[str, Any]:
    source = _first_source(entry)
    access_url = entry.get("accessURL") or source.get("path") or entry.get("path")
    migrated = {
        key: value
        for key, value in entry.items()
        if key
        not in {
            "accessUrl",
            "sources",
            "syncTarget",
            "targets",
            "target",
            "path",
            "resources",
            "packages",
            "catalogs",
        }
    }
    migrated["accessURL"] = access_url
    migrated["serviceType"] = entry.get("serviceType") or source.get("serviceType")
    migrated["entityType"] = entry.get("entityType") or source.get("entityType") or "Directory"
    migrated["resources"] = [_resource(item) for item in entry.get("resources", []) if isinstance(item, dict)]
    migrated["catalogs"] = [
        _catalog(item)
        for item in [*entry.get("catalogs", []), *entry.get("packages", [])]
        if isinstance(item, dict)
    ]
    return {key: value for key, value in migrated.items() if value is not None}


def migrate_descriptor(
    descriptor: Path | str,
    *,
    output: Path | str | None = None,
    dry_run: bool = False,
) -> DriveCatalog:
    """Migrate a legacy source/path descriptor to path/_cache/accessURL."""
    descriptor_path = Path(descriptor)
    document = _load_document(descriptor_path)
    migrated = {
        "$schema": document.get("$schema", CATALOG_PROFILE),
        "resources": [
            _resource(item) for item in document.get("resources", []) if isinstance(item, dict)
        ],
        "packages": [],
        "catalogs": [
            _catalog(item)
            for item in [*document.get("catalogs", []), *document.get("packages", [])]
            if isinstance(item, dict)
        ],
    }
    for key in ("name", "title", "description"):
        if key in document:
            migrated[key] = document[key]

    catalog = DriveCatalog.model_validate(migrated)
    if not dry_run:
        catalog.to_path(str(Path(output) if output is not None else descriptor_path))
    return catalog


__all__ = ["migrate_descriptor"]
