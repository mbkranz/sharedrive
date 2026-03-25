from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pydantic
from dplib.models.package import Package
from dplib.models.resource import Resource
from dplib.models.source import Source
from dplib.system import Model


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
    normalized = entity_type.strip()
    if not normalized:
        raise ValueError("entityType must be a non-empty string")

    alias = ENTITY_TYPE_ALIASES.get(normalized.lower())
    if alias is not None:
        return alias
    if normalized in set(ENTITY_TYPE_ALIASES.values()):
        return normalized
    raise ValueError(f"Unsupported entityType '{entity_type}'.")


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
    if isinstance(value, (DriveResource, DrivePackage)):
        return value
    if not isinstance(value, dict):
        raise ValueError("Drive descriptor resources must be objects")

    if isinstance(value.get("resources"), list):
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
        normalized_selector = resource_selector.strip()
        if not normalized_selector:
            return None

        if "." not in normalized_selector:
            direct_match = self.get_resource(name=normalized_selector)
            if isinstance(direct_match, (DriveResource, DrivePackage)):
                return normalized_selector, direct_match

        references: list[tuple[str, DriveResource | DrivePackage]] = []

        def walk(resources: list[DriveResource | DrivePackage], parent_path: str | None = None) -> None:
            for resource in resources:
                name = (resource.name or "").strip()
                if not name:
                    continue
                selector_path = name if parent_path is None else f"{parent_path}.{name}"
                references.append((selector_path, resource))
                if isinstance(resource, DrivePackage) and resource.resources:
                    walk(resource.resources, selector_path)

        walk(self.resources)
        lowered_selector = normalized_selector.lower()
        matches = [
            (path, resource)
            for path, resource in references
            if path.lower() == lowered_selector or path.split(".")[-1].lower() == lowered_selector
        ]
        if not matches:
            return None
        if len(matches) > 1 and "." not in normalized_selector:
            raise ValueError(
                f'Resource selector "{resource_selector}" is ambiguous. Use the full dot-path selector.'
            )
        return matches[0]

DriveDescriptor = DrivePackage


def load_drive_descriptor(
    path: Path | str,
    *,
    create_if_missing: bool = False,
) -> DrivePackage:
    descriptor_path = Path(path)
    if not descriptor_path.exists():
        if create_if_missing:
            return DrivePackage(resources=[])
        raise FileNotFoundError(f"Descriptor '{descriptor_path}' does not exist.")
    return DrivePackage.from_path(str(descriptor_path), basepath=None)


def save_drive_descriptor(path: Path | str, descriptor: DrivePackage) -> None:
    descriptor_path = Path(path)
    descriptor_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor.to_path(str(descriptor_path))


DrivePackage.model_rebuild()


__all__ = [
    "DriveDescriptor",
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
