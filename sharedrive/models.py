from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Iterable, Optional, TypeVar
from urllib.parse import unquote, urlparse

import pydantic
from pydantic.alias_generators import to_pascal,to_camel
from pydantic import AliasChoices, Field
import yaml
from dplib.models.catalog import Catalog
from dplib.models.package import Package
from dplib.models.resource import Resource
from dplib.models.source import Source
from dplib.system import EntityReference, Model


CATALOG_PROFILE = "data-package-catalog"
T = TypeVar("T", bound=Model)
Entry = Model | dict[str, Any]


SYNC_TARGET_ALIASES = {
    "path": "path",
    "resource": "resources",
    "resources": "resources",
}

def normalize_sync_target(sync_target: str) -> str:
    """Normalize syncTarget to the sharedrive descriptor contract."""
    normalized = sync_target.strip()
    if not normalized:
        raise ValueError("syncTarget must be a non-empty string")

    alias = SYNC_TARGET_ALIASES.get(normalized.lower())
    if alias is not None:
        return alias

    raise ValueError(f"Unsupported syncTarget '{sync_target}'.")


def _empty_catalog_document() -> dict[str, Any]:
    return {
        "$schema": CATALOG_PROFILE,
        "resources": [],
        "packages": [],
        "catalogs": [],
    }


class DriveSource(Source):
    path: Annotated[str|None,Field(AliasChoices("path", "url","uri"))] = None
    serviceType: Annotated[str, pydantic.BeforeValidator(to_pascal)]
    entityType: Annotated[str, pydantic.BeforeValidator(to_pascal)]

    @property
    def adapter_name(self) -> str:
        if self.serviceType is not None:
            return self.serviceType.lower()
        elif self.path is not None:
            source_path = self.path or ""
            parsed = urlparse(source_path)
            host = parsed.netloc.lower()
            if parsed.scheme.lower() == "s3":
                return "s3"
            elif "sharepoint.com" in host:
                return "sharepoint"
            elif "drive.google.com" in host:
                return "googledrive"
            else:
                raise ValueError("Source must declare a serviceType or a path with a recognizable host")
        else:
            raise ValueError("Source must declare a serviceType or a path with a recognizable host")

        



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

    def to_dict(self):
        return Model.to_dict(self)

    @property
    def sync_target(self) -> str:
        """Return the declared sync target for a package-like resource."""
        declared = getattr(self, "syncTarget", None)
        if isinstance(declared, str) and declared.strip():
            return normalize_sync_target(declared)
        return "resources"

    @property
    def is_package(self) -> bool:
        return True

    def get_resource_reference(
        self,
        resource_selector: str,
    ) -> tuple[str, DriveResource | DrivePackage] | None:
        reference = _resolve_entity_reference(
            self,
            resource_selector,
            (DriveResource, DrivePackage),
        )
        if reference is None:
            return None
        return reference.name_path, reference.model


class DriveCatalog(Catalog,json_schema_extra={"$schema": CATALOG_PROFILE}):
    profile: str = pydantic.Field(default=CATALOG_PROFILE, alias="$schema")
    resources: list[DriveResource] = pydantic.Field(default_factory=list)
    packages: list[DrivePackage] = pydantic.Field(default_factory=list)
    catalogs: list["DriveCatalog"] = pydantic.Field(default_factory=list)

    @classmethod
    def from_descriptor(cls, path: Path | str) -> dict[str, Any]:
        """Load a sharedrive descriptor as a mutable document."""
        descriptor = yaml.safe_load(Path(path).read_text())
        return cls.model_validate(descriptor)
    
    def save_descriptor(self, path: Path | str, serialization_config) -> None:
        """Save the catalog as a sharedrive descriptor."""
        descriptor = self.model_dump()
        Path(path).write_text(yaml.safe_dump(descriptor, sort_keys=False))
        return self


DriveResource.model_rebuild()
DrivePackage.model_rebuild()
DriveCatalog.model_rebuild()


__all__ = [
    "DriveCatalog",
    "DrivePackage",
    "DriveResource",
    "DriveSource",

]
