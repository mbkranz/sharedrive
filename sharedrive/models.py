from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Optional
from urllib.parse import urlparse

import pydantic
from pydantic import AliasChoices, BeforeValidator, Field

from dplib.models import Catalog
from dplib.models import Package
from dplib.models import Resource


CATALOG_PROFILE = "data-package-catalog"

SERVICE_TYPE_ALIASES = {
    "google": "GoogleDrive",
    "googledrive": "GoogleDrive",
    "google_drive": "GoogleDrive",
    "google-drive": "GoogleDrive",
    "drive": "GoogleDrive",
    "sharepoint": "SharePoint",
    "share_point": "SharePoint",
    "share-point": "SharePoint",
    "s3": "S3",
}
SUPPORTED_SERVICE_TYPES = {"GoogleDrive", "SharePoint", "S3"}

ENTITY_TYPE_ALIASES = {
    "file": "File",
    "object": "File",
    "blob": "File",
    "document": "File",
    "spreadsheet": "File",
    "directory": "Directory",
    "folder": "Directory",
    "container": "Container",
    "bucket": "Container",
}


def _empty_catalog_document() -> dict[str, Any]:
    return {"$schema": CATALOG_PROFILE, "resources": [], "packages": [], "catalogs": []}


def _require_non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def normalize_service_type(value: str | None) -> str | None:
    """Normalize OpenMetadata-style drive/storage service names."""
    if value is None:
        return None
    normalized = _require_non_empty(value, "serviceType")
    key = normalized.replace(" ", "").replace(".", "").lower()
    return SERVICE_TYPE_ALIASES.get(key, normalized)


def normalize_entity_type(value: str | None) -> str | None:
    """Normalize OpenMetadata-style drive/storage entity names."""
    if value is None:
        return None
    normalized = _require_non_empty(value, "entityType")
    key = normalized.replace(" ", "").replace(".", "").lower()
    return ENTITY_TYPE_ALIASES.get(key, normalized[:1].upper() + normalized[1:])


def infer_service_type(locator: str) -> str:
    """Infer a supported serviceType from a remote locator."""
    normalized = _require_non_empty(locator, "locator")
    parsed = urlparse(normalized)
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()

    if scheme == "s3":
        return "S3"
    if "sharepoint.com" in host:
        return "SharePoint"
    if "drive.google.com" in host or "docs.google.com" in host:
        return "GoogleDrive"

    raise NotImplementedError(
        f"Could not infer serviceType from '{normalized}'. "
        "Pass service_type explicitly."
    )


def infer_entity_type(locator: str, *, service_type: str) -> str:
    """Infer whether a locator points at a file, directory, or container."""
    normalized = _require_non_empty(locator, "locator")
    canonical_service_type = normalize_service_type(service_type)
    parsed = urlparse(normalized)
    path = parsed.path or ""
    last_segment = path.rstrip("/").split("/")[-1] if path else ""

    if canonical_service_type == "GoogleDrive":
        return "Directory" if "/folders/" in normalized else "File"
    if canonical_service_type == "S3":
        object_path = parsed.path.lstrip("/")
        if not object_path:
            return "Container"
        return "Directory" if object_path.endswith("/") else "File"
    if canonical_service_type == "SharePoint":
        if normalized.rstrip("/") != normalized:
            return "Directory"
        return "File" if "." in last_segment else "Directory"
    return "File"


def resolve_service_type(locator: str, service_type: str | None = None) -> str:
    """Return a supported canonical serviceType, inferring it when omitted."""
    normalized = (
        infer_service_type(locator)
        if service_type is None
        else normalize_service_type(service_type)
    )
    if normalized not in SUPPORTED_SERVICE_TYPES:
        raise NotImplementedError(f"Service type '{normalized}' is not implemented.")
    return normalized


def resolve_entity_type(
    locator: str, *, service_type: str, entity_type: str | None = None
) -> str:
    """Return the declared or inferred entity type."""
    if entity_type is None:
        return infer_entity_type(locator, service_type=service_type)
    return normalize_entity_type(entity_type) or "File"


def adapter_from_service_type(service_type: str | None) -> str | None:
    """Map supported serviceType values to registry adapter names."""
    normalized = normalize_service_type(service_type)
    if normalized == "GoogleDrive":
        return "googledrive"
    if normalized == "SharePoint":
        return "sharepoint"
    if normalized == "S3":
        return "s3"
    return None


def adapter_from_locator(locator: str) -> str:
    """Infer a registry adapter name from a remote locator."""
    return adapter_from_service_type(infer_service_type(locator)) or ""


def resolve_cache_path(resource: "DriveResource", output_dir: Path) -> Path:
    """Resolve a resource's `_cache` path under the requested output directory."""
    if not resource.cache:
        name = resource.name or resource.path or "resource"
        raise ValueError(f"Resource '{name}' is missing required _cache path.")
    cache_path = Path(resource.cache.strip())
    return cache_path if cache_path.is_absolute() else output_dir / cache_path


ServiceTypeValue = Annotated[str, BeforeValidator(normalize_service_type)]
EntityTypeValue = Annotated[str, BeforeValidator(normalize_entity_type)]


class DriveResource(Resource):
    """Data Package resource with shared-drive adapter metadata.

    `path` remains the canonical Data Package data locator. `_cache` follows
    the Data Package caching recipe as the local materialized copy location.
    """

    cache: Annotated[
        Optional[str],
        Field(
            default=None,
            alias="_cache",
            validation_alias=AliasChoices("_cache", "cache"),
        ),
    ] = None
    serviceType: Optional[ServiceTypeValue] = None
    serviceId: Optional[str] = None
    entityType: Optional[EntityTypeValue] = None

    @property
    def adapter_name(self) -> str:
        adapter = adapter_from_service_type(self.serviceType)
        if adapter:
            return adapter
        if isinstance(self.path, str) and self.path.strip():
            return adapter_from_locator(self.path)
        raise ValueError(
            "Resource must declare serviceType or a path with a recognizable host"
        )


class DrivePackage(Package):
    serviceType: Optional[ServiceTypeValue] = None
    serviceId: Optional[str] = None
    entityType: Optional[EntityTypeValue] = None

    @property
    def adapter_name(self) -> str:
        adapter = adapter_from_service_type(self.serviceType)
        if adapter:
            return adapter
        raise ValueError("Package must declare serviceType to determine adapter")


class DriveCatalog(Catalog, json_schema_extra={"$schema": CATALOG_PROFILE}):
    profile: str = pydantic.Field(default=CATALOG_PROFILE, alias="$schema")
    accessURL: Optional[str] = None
    serviceType: Optional[ServiceTypeValue] = None
    serviceId: Optional[str] = None
    entityType: Optional[EntityTypeValue] = None
    resources: list[DriveResource] = pydantic.Field(default_factory=list)
    packages: list[DrivePackage] = pydantic.Field(default_factory=list)
    catalogs: list["DriveCatalog"] = pydantic.Field(default_factory=list)

    @property
    def adapter_name(self) -> str:
        adapter = adapter_from_service_type(self.serviceType)
        if adapter:
            return adapter
        if self.accessURL:
            return adapter_from_locator(self.accessURL)
        raise ValueError(
            "Catalog must declare serviceType or an accessURL with a recognizable host"
        )

    def to_dict(self):
        data = {"$schema": CATALOG_PROFILE}
        data.update(super().to_dict())
        return data

    @classmethod
    def init(cls) -> "DriveCatalog":
        return cls.model_validate(_empty_catalog_document())


DriveResource.model_rebuild()
DrivePackage.model_rebuild()
DriveCatalog.model_rebuild()


__all__ = [
    "CATALOG_PROFILE",
    "DriveCatalog",
    "DrivePackage",
    "DriveResource",
    "SUPPORTED_SERVICE_TYPES",
    "adapter_from_locator",
    "adapter_from_service_type",
    "infer_entity_type",
    "infer_service_type",
    "normalize_entity_type",
    "normalize_service_type",
    "resolve_cache_path",
    "resolve_entity_type",
    "resolve_service_type",
]
