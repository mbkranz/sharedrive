from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from sharedrive.models import (
    CATALOG_PROFILE,
    normalize_entity_type,
    normalize_service_type,
    load_drive_descriptor,
)

SUPPORTED_SERVICE_TYPES = {"GoogleDrive", "SharePoint", "S3"}


def _require_non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def infer_service_type(source: str) -> str:
    """Infer canonical serviceType from a source URL/URI."""
    normalized_source = _require_non_empty(source, "source")
    parsed = urlparse(normalized_source)
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()

    if scheme == "s3":
        return "S3"
    if "sharepoint.com" in host:
        return "SharePoint"
    if "google.com" in host:
        return "GoogleDrive"

    raise NotImplementedError(
        f"Could not infer drive service from source '{normalized_source}'. "
        "Pass --service-type explicitly."
    )


def infer_entity_type(source: str, *, service_type: str) -> str:
    """Infer OpenMetadata-style entityType from the source locator.

    The value is intentionally coarse because it drives fetch and sync planning,
    not full catalog modeling.
    """
    normalized_source = _require_non_empty(source, "source")
    canonical_service_type = normalize_service_type(service_type)
    parsed = urlparse(normalized_source)
    path = parsed.path or ""
    last_segment = path.rstrip("/").split("/")[-1] if path else ""

    if canonical_service_type == "GoogleDrive":
        if "/folders/" in normalized_source:
            return "Directory"
        return "File"

    if canonical_service_type == "S3":
        object_path = parsed.path.lstrip("/")
        if not object_path:
            return "Container"
        if object_path.endswith("/"):
            return "Directory"
        return "File"

    if canonical_service_type == "SharePoint":
        if normalized_source.rstrip("/") != normalized_source:
            return "Directory"
        return "File" if "." in last_segment else "Directory"

    return "File"


def resolve_service_type(source: str, service_type: str | None = None) -> str:
    """Return a supported canonical serviceType, inferring it when omitted."""
    if service_type is None:
        return infer_service_type(source)
    normalized = normalize_service_type(_require_non_empty(service_type, "service_type"))
    if normalized not in SUPPORTED_SERVICE_TYPES:
        raise NotImplementedError(f"Service type '{normalized}' is not implemented.")
    return normalized


def resolve_entity_type(
    source: str,
    *,
    service_type: str,
    entity_type: str | None = None,
) -> str:
    """Return the declared or inferred source entity type."""
    if entity_type is None:
        return infer_entity_type(source, service_type=service_type)
    return normalize_entity_type(_require_non_empty(entity_type, "entity_type"))


def infer_drive_service(source: str) -> str:
    """Backward-compatible alias for inferring canonical serviceType."""
    return infer_service_type(source)


def add_resource_to_descriptor(
    descriptor: Path | str,
    *,
    name: str,
    path: str,
    source: str,
    title: str | None = None,
    description: str | None = None,
    service_type: str | None = None,
    entity_type: str | None = None,
    sync_target: str | None = None,
    drive_service: str | None = None,
    package: bool = False,
    profile: str | None = None,
    create_if_missing: bool = False,
) -> dict[str, Any]:
    """Append a resource entry to a descriptor and return the created resource.

    The returned dict is a raw descriptor resource object that includes
    ``syncTarget`` and, for package resources, an empty ``resources`` list.
    Both fields survive the YAML round-trip because the descriptor is written
    directly via ``save_drive_descriptor`` rather than through the dplib
    model serializer (which strips empty lists via ``clean_dict``).

    .. note::
        When the resolved ``entityType`` is ``"Directory"``, ``sync_target``
        **must** be supplied explicitly (either ``"path"`` or ``"resources"``).
        Omitting it raises :class:`ValueError` because the caller must decide
        whether directory contents are downloaded as individual files
        (``syncTarget: path``) or indexed as nested descriptor resources
        (``syncTarget: resources``).
    """
    descriptor_path = Path(descriptor)

    if not create_if_missing and not descriptor_path.exists():
        raise FileNotFoundError(f"Descriptor '{descriptor_path}' does not exist.")

    resource_name = _require_non_empty(name, "name")
    resource_path = _require_non_empty(path, "path")
    resource_source = _require_non_empty(source, "source")
    resolved_service_type = resolve_service_type(
        resource_source,
        service_type=service_type or drive_service,
    )
    resolved_entity_type = resolve_entity_type(
        resource_source,
        service_type=resolved_service_type,
        entity_type=entity_type,
    )
    resource_profile = None
    if profile is not None:
        resource_profile = _require_non_empty(profile, "profile")

    as_package = package
    if sync_target is not None:
        normalized_legacy_target = sync_target.strip().lower()
        if normalized_legacy_target in {"resources", "resource"}:
            as_package = True
        elif normalized_legacy_target == "path":
            as_package = False
        else:
            raise ValueError(f"Unsupported legacy sync_target '{sync_target}'.")

    # Directories must explicitly declare a syncTarget so the caller decides
    # whether files are synced individually (path) or as nested resources.
    if resolved_entity_type == "Directory" and sync_target is None:
        raise ValueError(
            "syncTarget is required when entityType is 'Directory'. "
            "Pass sync_target='resources' or sync_target='path'."
        )

    document = load_drive_descriptor(descriptor_path, create_if_missing=create_if_missing)
    target_collection = document.packages if as_package else document.resources
    top_level_entries = [*document.resources, *document.packages, *document.catalogs]

    normalized_name = resource_name.strip().lower()
    if any(
        str(getattr(entry, "name", "") or "").strip().lower() == normalized_name
        for entry in top_level_entries
    ):
        raise ValueError(f"Resource '{resource_name}' already exists in the descriptor")

    resource_payload: dict[str, Any] = {
        "name": resource_name,
        "path": resource_path,
        "syncTarget": "resources" if as_package else "path",
        "sources": [
            {
                "path": resource_source,
                "serviceType": resolved_service_type,
                "entityType": resolved_entity_type,
            }
        ],
    }
    if title is not None and title.strip():
        resource_payload["title"] = title.strip()
    if description is not None and description.strip():
        resource_payload["description"] = description.strip()
    if resource_profile is not None:
        resource_payload["profile"] = resource_profile
    if as_package:
        resource_payload["resources"] = []

    target_collection.append(resource_payload)

    # Save descriptor as YAML/JSON, preserving the raw resource structures (including empty resources lists)
    descriptor_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor_dict = {
        "$schema": CATALOG_PROFILE,
        "resources": [
            resource if isinstance(resource, dict) else resource.to_dict()
            for resource in document.resources
        ],
        "packages": [
            package_entry if isinstance(package_entry, dict) else package_entry.to_dict()
            for package_entry in document.packages
        ],
        "catalogs": [
            catalog if isinstance(catalog, dict) else catalog.to_dict()
            for catalog in document.catalogs
        ],
    }

    suffix = descriptor_path.suffix.lower()
    if suffix == ".json":
        descriptor_path.write_text(
            json.dumps(descriptor_dict, indent=2) + "\n",
            encoding="utf-8",
        )
    else:
        # YAML (default for .yaml, .yml, or unknown extensions)
        descriptor_path.write_text(
            yaml.dump(descriptor_dict, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )
    return resource_payload


__all__ = [
    "SUPPORTED_SERVICE_TYPES",
    "add_resource_to_descriptor",
    "infer_entity_type",
    "infer_drive_service",
    "infer_service_type",
    "resolve_entity_type",
    "resolve_service_type",
]

