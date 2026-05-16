from __future__ import annotations

from pathlib import Path
from typing import Any

from dplib.error import Error

from sharedrive.models import (
    DriveCatalog,
    DriveResource,
    infer_entity_type,
    infer_service_type,
    resolve_entity_type,
    resolve_service_type,
)


def _require_non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _load_descriptor(path: Path, *, create_if_missing: bool) -> DriveCatalog:
    if path.exists():
        return DriveCatalog.from_path(str(path))
    if not create_if_missing:
        raise FileNotFoundError(f"Descriptor '{path}' does not exist.")
    return DriveCatalog.empty()


def _assert_unique_top_level_name(document: DriveCatalog, name: str) -> None:
    normalized_name = name.strip().lower()
    top_level_entries = [*document.resources, *document.packages, *document.catalogs]
    if any(
        str(getattr(entry, "name", "") or "").strip().lower() == normalized_name
        for entry in top_level_entries
    ):
        raise ValueError(f"Entity '{name}' already exists in the descriptor")


def add_resource_to_descriptor(
    descriptor: Path | str,
    *,
    name: str,
    path: str | None = None,
    cache: str | None = None,
    source: str | None = None,
    access_url: str | None = None,
    title: str | None = None,
    description: str | None = None,
    service_type: str | None = None,
    entity_type: str | None = None,
    drive_service: str | None = None,
    catalog: bool = False,
    package: bool = False,
    sync_target: str | None = None,
    profile: str | None = None,
    create_if_missing: bool = False,
) -> dict[str, Any]:
    """Append a standards-aligned resource or catalog entry to a descriptor.

    File resources use ``path`` as the canonical remote data locator and
    ``_cache`` as the local materialized copy. Remote folders are represented
    as catalogs and use ``accessURL`` for discovery.
    """
    descriptor_path = Path(descriptor)
    entity_name = _require_non_empty(name, "name")
    document = _load_descriptor(descriptor_path, create_if_missing=create_if_missing)
    _assert_unique_top_level_name(document, entity_name)

    if source is not None and path is not None and cache is None and not catalog:
        cache = path
        path = source
    as_catalog = catalog or (sync_target == "resources")
    if source is not None and access_url is None and as_catalog:
        access_url = source
    if package:
        raise ValueError(
            "Remote folders are now catalogs. Use catalog=True/--catalog instead of package=True/--package."
        )

    if as_catalog:
        folder_url = _require_non_empty(access_url or path or "", "accessURL")
        resolved_service_type = resolve_service_type(
            folder_url, service_type=service_type or drive_service
        )
        resolved_entity_type = resolve_entity_type(
            folder_url,
            service_type=resolved_service_type,
            entity_type=entity_type or "Directory",
        )
        if resolved_entity_type not in {"Directory", "Container"}:
            raise ValueError("Catalog entries must use entityType Directory or Container.")

        catalog_payload: dict[str, Any] = {
            "name": entity_name,
            "accessURL": folder_url,
            "serviceType": resolved_service_type,
            "entityType": resolved_entity_type,
            "resources": [],
            "catalogs": [],
        }
        if title is not None and title.strip():
            catalog_payload["title"] = title.strip()
        if description is not None and description.strip():
            catalog_payload["description"] = description.strip()
        if profile is not None and profile.strip():
            catalog_payload["profile"] = profile.strip()

        entry = DriveCatalog.model_validate(catalog_payload)
        document.catalogs.append(entry)
        descriptor_path.parent.mkdir(parents=True, exist_ok=True)
        document.to_path(str(descriptor_path))
        return entry.to_dict()

    resource_path = _require_non_empty(path or "", "path")
    resource_cache = _require_non_empty(cache or "", "cache")
    resolved_service_type = resolve_service_type(
        resource_path, service_type=service_type or drive_service
    )
    resolved_entity_type = resolve_entity_type(
        resource_path,
        service_type=resolved_service_type,
        entity_type=entity_type or "File",
    )
    if resolved_entity_type != "File":
        raise ValueError(
            "Non-file drive entries should be added as catalogs with accessURL."
        )

    resource_payload: dict[str, Any] = {
        "name": entity_name,
        "path": resource_path,
        "_cache": resource_cache,
        "serviceType": resolved_service_type,
        "entityType": resolved_entity_type,
    }
    if title is not None and title.strip():
        resource_payload["title"] = title.strip()
    if description is not None and description.strip():
        resource_payload["description"] = description.strip()
    if profile is not None and profile.strip():
        resource_payload["profile"] = profile.strip()

    entry = DriveResource.model_validate(resource_payload)
    document.resources.append(entry)
    descriptor_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        document.to_path(str(descriptor_path))
    except Error:
        raise
    return entry.to_dict()


def infer_drive_service(source: str) -> str:
    """Backward-compatible alias for inferring canonical serviceType."""
    return infer_service_type(source)


__all__ = [
    "add_resource_to_descriptor",
    "infer_drive_service",
    "infer_entity_type",
    "infer_service_type",
    "resolve_entity_type",
    "resolve_service_type",
]
