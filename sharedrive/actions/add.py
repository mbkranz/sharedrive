from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sharedrive.models import (
    DrivePackage,
    DriveResource,
    DriveSource,
    load_drive_descriptor,
    normalize_entity_type,
    normalize_service_type,
    save_drive_descriptor,
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
    """Append a resource entry to a descriptor and return the created resource."""
    descriptor_path = Path(descriptor)

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

    descriptor_model = load_drive_descriptor(
        descriptor_path,
        create_if_missing=create_if_missing,
    )

    existing_reference = descriptor_model.get_resource_reference(resource_name)
    if existing_reference is not None:
        raise ValueError(f"Resource '{resource_name}' already exists in the descriptor")

    resource_cls = DrivePackage if as_package else DriveResource
    resource = resource_cls(
        name=resource_name,
        path=resource_path,
        title=title.strip() if title is not None and title.strip() else None,
        description=description.strip() if description is not None and description.strip() else None,
        profile=resource_profile,
        sources=[
            DriveSource(
                path=resource_source,
                serviceType=resolved_service_type,
                entityType=resolved_entity_type,
            )
        ],
        resources=[] if as_package else None,
    )
    descriptor_model.add_resource(resource)
    save_drive_descriptor(descriptor_path, descriptor_model)
    return resource.to_dict()


__all__ = [
    "SUPPORTED_SERVICE_TYPES",
    "add_resource_to_descriptor",
    "infer_entity_type",
    "infer_drive_service",
    "infer_service_type",
    "resolve_entity_type",
    "resolve_service_type",
]