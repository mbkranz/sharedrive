from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sharedrive.descriptor import (
    ensure_descriptor_exists,
    get_descriptor_resources,
    load_descriptor_document,
    save_descriptor_document,
)

SUPPORTED_DRIVE_SERVICES = {"sharepoint", "googledrive", "s3"}


def _require_non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def infer_drive_service(source: str) -> str:
    """Infer the implemented drive service from a source URL/URI."""
    normalized_source = _require_non_empty(source, "source")
    parsed = urlparse(normalized_source)
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()

    if scheme == "s3":
        return "s3"
    if "sharepoint.com" in host:
        return "sharepoint"
    if "google.com" in host:
        return "googledrive"

    raise NotImplementedError(
        f"Could not infer drive service from source '{normalized_source}'. "
        "Pass --drive-service explicitly."
    )


def normalize_drive_service(source: str, drive_service: str | None = None) -> str:
    """Return a supported drive service, inferring it from source if omitted."""
    if drive_service is None:
        return infer_drive_service(source)

    normalized_service = _require_non_empty(drive_service, "drive_service").lower()
    if normalized_service not in SUPPORTED_DRIVE_SERVICES:
        raise NotImplementedError(
            f"Drive service '{normalized_service}' is not implemented."
        )
    return normalized_service


def add_resource_to_descriptor(
    descriptor: Path | str,
    *,
    name: str,
    path: str,
    source: str,
    title: str | None = None,
    description: str | None = None,
    drive_service: str | None = None,
    package: bool = False,
    profile: str | None = None,
    create_if_missing: bool = False,
) -> dict[str, Any]:
    """Append a resource entry to a descriptor and return the created resource."""
    descriptor_path = Path(descriptor)
    if not create_if_missing:
        ensure_descriptor_exists(descriptor_path)

    resource_name = _require_non_empty(name, "name")
    resource_path = _require_non_empty(path, "path")
    resource_source = _require_non_empty(source, "source")
    resource_drive_service = normalize_drive_service(resource_source, drive_service)
    resource_profile = None
    if profile is not None:
        resource_profile = _require_non_empty(profile, "profile")
    if resource_profile is not None and not package:
        raise ValueError("profile can only be provided when package=True")

    document = load_descriptor_document(descriptor_path)
    resources = get_descriptor_resources(document, create=True)

    normalized_names = {
        str(existing.get("name", "")).strip().lower()
        for existing in resources
        if isinstance(existing, dict)
    }
    if resource_name.lower() in normalized_names:
        raise ValueError(f"Resource '{resource_name}' already exists in the descriptor")

    resource: dict[str, Any] = {
        "name": resource_name,
        "path": resource_path,
        "driveService": resource_drive_service,
        "sources": [{"path": resource_source}],
    }
    if title is not None and title.strip():
        resource["title"] = title.strip()
    if description is not None and description.strip():
        resource["description"] = description.strip()
    if package:
        resource["profile"] = resource_profile or "data-package"
        resource["resources"] = []

    resources.append(resource)
    save_descriptor_document(descriptor_path, document)
    return resource


__all__ = [
    "SUPPORTED_DRIVE_SERVICES",
    "add_resource_to_descriptor",
    "infer_drive_service",
    "normalize_drive_service",
]