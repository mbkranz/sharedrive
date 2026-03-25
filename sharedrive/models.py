from typing import List, Optional
from dplib.models.resource import Resource
from dplib.models.source import Source
import pydantic


class DriveSource(Source):
    """
    Extended Source model for drive references.
    Conforms to Frictionless Data but tracks our specialized metadata.
    """
    serviceType: Optional[str] = pydantic.Field(default=None)
    entityType: Optional[str] = pydantic.Field(default=None)


class DriveResource(Resource):
    """
    Extended Frictionless Data Resource model tracking drive items.
    """
    # Override sources to use our specialized source schema
    sources: Optional[List[DriveSource]] = []

    # Optional root-level properties for quick access
    drive_id: Optional[str] = pydantic.Field(default=None, alias="driveId")
    
    @classmethod
    def from_drive_metadata(
        cls,
        name: str,
        path: str,
        service_type: str,
        entity_type: str,
        source_url: str,
        type_str: str = "file",
        format_str: Optional[str] = None,
        drive_id: Optional[str] = None,
    ) -> "DriveResource":
        """Convenience constructor."""
        return cls(
            name=name,
            path=path,
            type=type_str,
            format=format_str,
            drive_id=drive_id,
            sources=[
                DriveSource(
                    path=source_url,
                    serviceType=service_type,
                    entityType=entity_type,
                )
            ]
        )

__all__ = ["DriveResource", "DriveSource"]
