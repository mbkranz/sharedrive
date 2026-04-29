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


class DrivePackage(Package):
    path: Optional[str] = None
    sources: list[DriveSource] = pydantic.Field(default_factory=list)
    resources: list["DriveResource | DrivePackage"] = pydantic.Field(default_factory=list)
    profile: Optional[str] = None

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



class DriveCatalog(Catalog,json_schema_extra={"$schema": CATALOG_PROFILE}):
    profile: str = pydantic.Field(default=CATALOG_PROFILE, alias="$schema")
    resources: list[DriveResource] = pydantic.Field(default_factory=list)
    packages: list[DrivePackage] = pydantic.Field(default_factory=list)
    catalogs: list["DriveCatalog"] = pydantic.Field(default_factory=list)


DriveResource.model_rebuild()
DrivePackage.model_rebuild()
DriveCatalog.model_rebuild()


__all__ = [
    "DriveCatalog",
    "DrivePackage",
    "DriveResource",
    "DriveSource",

]
