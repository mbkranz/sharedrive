from __future__ import annotations

from typing import Annotated, Any, Optional
from urllib.parse import  urlparse

import pydantic
from pydantic.alias_generators import to_pascal
from pydantic import AliasChoices, Field
# s
from dplib.models.catalog import Catalog
from dplib.models.package import Package
from dplib.models.resource import Resource
from dplib.models.source import Source


CATALOG_PROFILE = "data-package-catalog"



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
    profile: Optional[str] = None


class DrivePackage(Package):
    path: Optional[str] = None
    sources: list[DriveSource] = pydantic.Field(default_factory=list)
    resources: list["DriveResource | DrivePackage"] = pydantic.Field(default_factory=list)
    profile: Optional[str] = None



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
