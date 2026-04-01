from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import pydantic
import yaml
from dplib.models.catalog import Catalog
from dplib.models.package import Package
from dplib.models.resource import Resource
from dplib.models.source import Source
from dplib.system import Model


CATALOG_PROFILE = "data-package-catalog"


SERVICE_TYPE_ALIASES = {
    "googledrive": "GoogleDrive",
    "google-drive": "GoogleDrive",
    "google drive": "GoogleDrive",
    "sharepoint": "SharePoint",
    "share-point": "SharePoint",
    "s3": "S3",
}

ENTITY_TYPE_ALIASES = {
    "file": "File",
    "directory": "Directory",
    "folder": "Directory",
    "container": "Container",
}

SYNC_TARGET_ALIASES = {
    "path": "path",
    "resource": "resources",
    "resources": "resources",
}


def normalize_service_type(service_type: str) -> str:
    normalized = service_type.strip()
    if not normalized:
        raise ValueError("serviceType must be a non-empty string")

    alias = SERVICE_TYPE_ALIASES.get(normalized.lower())
    if alias is not None:
        return alias
    if normalized in set(SERVICE_TYPE_ALIASES.values()):
        return normalized
    raise NotImplementedError(f"Service type '{service_type}' is not implemented.")


def normalize_entity_type(entity_type: str) -> str:
    """Normalize source entity type to OpenMetadata-style class naming.

    Known aliases (e.g. ``"file"`` → ``"File"``, ``"folder"`` → ``"Directory"``)
    are canonicalized.  Unknown values are returned as-is to preserve
    forward compatibility with service-specific types that are not yet
    enumerated here (e.g. ``"Bundle"``, ``"Container"``, vendor extensions).
    Callers that need strict validation should check the returned value against
    their own allow-list.
    """
    normalized = entity_type.strip()
    if not normalized:
        raise ValueError("entityType must be a non-empty string")

    alias = ENTITY_TYPE_ALIASES.get(normalized.lower())
    if alias is not None:
        return alias
    if normalized in set(ENTITY_TYPE_ALIASES.values()):
        return normalized
    # Accept unknown entity types as-is for forward compatibility with
    # service-specific types (e.g. "Container", "Bundle", etc.)
    return normalized


def normalize_sync_target(sync_target: str) -> str:
    """Normalize syncTarget to the sharedrive descriptor contract."""
    normalized = sync_target.strip()
    if not normalized:
        raise ValueError("syncTarget must be a non-empty string")

    alias = SYNC_TARGET_ALIASES.get(normalized.lower())
    if alias is not None:
        return alias

    raise ValueError(f"Unsupported syncTarget '{sync_target}'.")


def service_type_adapter_name(service_type: str) -> str:
    """Return the runtime adapter name for a canonical service type."""
    normalized = normalize_service_type(service_type)
    return {
        "GoogleDrive": "googledrive",
        "SharePoint": "sharepoint",
        "S3": "s3",
    }[normalized]


def _resolve_entity_reference[T: Model](
    model: Model,
    selector: str,
    entity_types: tuple[type[T], ...],
) -> tuple[str, T] | None:
    normalized_selector = selector.strip()
    if not normalized_selector:
        return None

    lowered_selector = normalized_selector.lower()
    matches = [
        (path, item)
        for path, item in model.iter_entity_references()
        if isinstance(item, entity_types)
        and (
            path.strip().lower() == lowered_selector
            or path.strip().lower().split(".")[-1] == lowered_selector
        )
    ]
    if not matches:
        return None
    if len(matches) > 1 and "." not in normalized_selector:
        raise ValueError(
            f'Resource selector "{selector}" is ambiguous. Use the full dot-path selector.'
        )
    return matches[0]


def _empty_catalog_document() -> dict[str, Any]:
    return {
        "$schema": CATALOG_PROFILE,
        "resources": [],
        "packages": [],
        "catalogs": [],
    }


def _legacy_descriptor_message(descriptor_path: Path) -> str:
    return (
        f"Descriptor '{descriptor_path}' must use a catalog root with '$schema: {CATALOG_PROFILE}'. "
        "Legacy package-root descriptors are no longer supported. "
        "Wrap top-level package entries under 'packages:' (or standalone assets under 'resources:') "
        "and set '$schema: data-package-catalog' at the root."
    )


def _load_raw_descriptor_document(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    raw_text = path.read_text(encoding="utf-8")
    if suffix == ".json":
        data = json.loads(raw_text)
    else:
        data = yaml.safe_load(raw_text)

    if not isinstance(data, dict):
        raise ValueError(
            f"Descriptor '{path}' must be an object at the document root."
        )
    return data


class DriveSource(Source):
    serviceType: Optional[str] = pydantic.Field(default=None)
    entityType: Optional[str] = pydantic.Field(default=None)

    @pydantic.field_validator("serviceType")
    @classmethod
    def _normalize_service_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return normalize_service_type(value)

    @pydantic.field_validator("entityType")
    @classmethod
    def _normalize_entity_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return normalize_entity_type(value)


class DriveResource(Resource):
    sources: list[DriveSource] = pydantic.Field(default_factory=list)
    drive_id: Optional[str] = pydantic.Field(default=None, alias="driveId")
    profile: Optional[str] = None

    @pydantic.field_validator("sources", mode="before")
    @classmethod
    def _coerce_sources(cls, value: Any) -> list[DriveSource]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("sources must be a list")
        return [item if isinstance(item, DriveSource) else DriveSource.model_validate(item) for item in value]

    @property
    def primary_source(self) -> Optional[DriveSource]:
        return self.sources[0] if self.sources else None

    @property
    def source_path(self) -> Optional[str]:
        source = self.primary_source
        return source.path if source is not None else None

    @property
    def source_service_type(self) -> Optional[str]:
        source = self.primary_source
        return source.serviceType if source is not None else None

    @property
    def source_entity_type(self) -> Optional[str]:
        source = self.primary_source
        return source.entityType if source is not None else None

    @property
    def sync_target(self) -> str:
        """Return the declared sync target for a resource.

        `syncTarget` is a sharedrive authoring field. When omitted, resources with
        nested `resources` default to `resources`; everything else defaults to
        `path`.
        """
        declared = getattr(self, "syncTarget", None)
        if isinstance(declared, str) and declared.strip():
            return normalize_sync_target(declared)
        return "resources" if isinstance(self.resources, list) and self.resources else "path"

    @property
    def syncs_to_resources(self) -> bool:
        """Return whether a resource syncs into nested resources."""
        return self.sync_target == "resources"

    @property
    def is_package(self) -> bool:
        return False

    def to_dict(self):
        return Model.to_dict(self)

    @classmethod
    def from_drive_metadata(
        cls,
        *,
        name: str,
        path: str,
        service_type: str,
        entity_type: str,
        source_url: str,
        format_str: Optional[str] = None,
        mediatype: Optional[str] = None,
        drive_id: Optional[str] = None,
        profile: Optional[str] = None,
    ) -> "DriveResource":
        type_str = "table" if format_str in {"csv", "xls", "xlsx"} else "file"
        return cls(
            name=name,
            path=path,
            type=type_str,
            format=format_str,
            mediatype=mediatype,
            driveId=drive_id,
            profile=profile,
            sources=[
                DriveSource(
                    path=source_url,
                    serviceType=service_type,
                    entityType=entity_type,
                )
            ],
        )


def _coerce_drive_entry(value: Any) -> "DriveResource | DrivePackage":
    """Coerce a raw dict into a DriveResource or DrivePackage.

    A dict is treated as a DrivePackage when:
    - it contains a ``resources`` list (populated or empty), OR
    - it declares ``syncTarget: "resources"``

    The second condition handles descriptors whose ``resources: []`` list was
    stripped by ``clean_dict`` during a previous save, ensuring that a
    round-tripped package resource is still recognized as a DrivePackage even
    when its nested resources list is absent from the serialized form.
    """
    if isinstance(value, (DriveResource, DrivePackage)):
        return value
    if not isinstance(value, dict):
        raise ValueError("Drive descriptor resources must be objects")

    # Treat as a package when it has nested resources OR when syncTarget is
    # explicitly set to "resources" (even before any resources are populated).
    if isinstance(value.get("resources"), list) or value.get("syncTarget") == "resources":
        return DrivePackage.model_validate(value)
    return DriveResource.model_validate(value)


class DrivePackage(Package):
    path: Optional[str] = None
    sources: list[DriveSource] = pydantic.Field(default_factory=list)
    drive_id: Optional[str] = pydantic.Field(default=None, alias="driveId")
    resources: list["DriveResource | DrivePackage"] = pydantic.Field(default_factory=list)
    profile: Optional[str] = None

    @pydantic.field_validator("sources", mode="before")
    @classmethod
    def _coerce_sources(cls, value: Any) -> list[DriveSource]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("sources must be a list")
        return [item if isinstance(item, DriveSource) else DriveSource.model_validate(item) for item in value]

    @pydantic.field_validator("resources", mode="before")
    @classmethod
    def _coerce_resources(cls, value: Any) -> list["DriveResource | DrivePackage"]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("resources must be a list")
        return [_coerce_drive_entry(item) for item in value]

    @property
    def primary_source(self) -> Optional[DriveSource]:
        return self.sources[0] if self.sources else None

    @property
    def source_path(self) -> Optional[str]:
        source = self.primary_source
        return source.path if source is not None else None

    @property
    def source_service_type(self) -> Optional[str]:
        source = self.primary_source
        return source.serviceType if source is not None else None

    @property
    def source_entity_type(self) -> Optional[str]:
        source = self.primary_source
        return source.entityType if source is not None else None

    def to_dict(self):
        return Model.to_dict(self)

    @property
    def is_package(self) -> bool:
        return True

    def get_resource_reference(
        self,
        resource_selector: str,
    ) -> tuple[str, DriveResource | DrivePackage] | None:
        return _resolve_entity_reference(
            self,
            resource_selector,
            (DriveResource, DrivePackage),
        )


class DriveCatalog(Catalog):
    profile: str = pydantic.Field(default=CATALOG_PROFILE, alias="$schema")
    resources: list[DriveResource] = pydantic.Field(default_factory=list)
    packages: list[DrivePackage] = pydantic.Field(default_factory=list)
    catalogs: list["DriveCatalog"] = pydantic.Field(default_factory=list)

    @pydantic.field_validator("resources", mode="before")
    @classmethod
    def _coerce_resources(cls, value: Any) -> list[DriveResource]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("resources must be a list")
        return [
            item if isinstance(item, DriveResource) else DriveResource.model_validate(item)
            for item in value
        ]

    @pydantic.field_validator("packages", mode="before")
    @classmethod
    def _coerce_packages(cls, value: Any) -> list[DrivePackage]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("packages must be a list")
        return [
            item if isinstance(item, DrivePackage) else DrivePackage.model_validate(item)
            for item in value
        ]

    @pydantic.field_validator("catalogs", mode="before")
    @classmethod
    def _coerce_catalogs(cls, value: Any) -> list["DriveCatalog"]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("catalogs must be a list")
        return [
            item if isinstance(item, DriveCatalog) else DriveCatalog.model_validate(item)
            for item in value
        ]

    def to_dict(self):
        data = {"$schema": CATALOG_PROFILE}
        data.update(Model.to_dict(self))
        return data

    def get_entity_reference(
        self,
        selector: str,
    ) -> tuple[str, DriveResource | DrivePackage | "DriveCatalog"] | None:
        return _resolve_entity_reference(
            self,
            selector,
            (DriveResource, DrivePackage, DriveCatalog),
        )

    def get_resource_reference(
        self,
        selector: str,
    ) -> tuple[str, DriveResource | DrivePackage] | None:
        resolved = self.get_entity_reference(selector)
        if resolved is None:
            return None
        path, item = resolved
        if isinstance(item, DriveCatalog):
            return None
        return path, item


DriveDescriptor = DriveCatalog


def load_drive_descriptor(
    path: Path | str,
    *,
    create_if_missing: bool = False,
) -> DriveCatalog:
    descriptor_path = Path(path)
    if not descriptor_path.exists():
        if create_if_missing:
            return DriveCatalog.model_validate(_empty_catalog_document())
        raise FileNotFoundError(f"Descriptor '{descriptor_path}' does not exist.")

    document = _load_raw_descriptor_document(descriptor_path)
    if document.get("$schema") != CATALOG_PROFILE:
        raise ValueError(_legacy_descriptor_message(descriptor_path))

    return DriveCatalog.model_validate(document)


def save_drive_descriptor(path: Path | str, descriptor: DriveCatalog) -> None:
    descriptor_path = Path(path)
    descriptor_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor.to_path(str(descriptor_path))


DrivePackage.model_rebuild()
DriveCatalog.model_rebuild()


__all__ = [
    "CATALOG_PROFILE",
    "DriveDescriptor",
    "DriveCatalog",
    "DrivePackage",
    "DriveResource",
    "DriveSource",
    "ENTITY_TYPE_ALIASES",
    "SERVICE_TYPE_ALIASES",
    "load_drive_descriptor",
    "normalize_entity_type",
    "normalize_service_type",
    "save_drive_descriptor",
]
