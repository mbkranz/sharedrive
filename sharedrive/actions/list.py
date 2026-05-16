"""Local descriptor listing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sharedrive.models import DriveCatalog, adapter_from_service_type


@dataclass(frozen=True, slots=True)
class ListedEntity:
    name: str
    name_path: str
    json_pointer: str
    entity_type: str
    path: str | None = None
    cache: str | None = None
    access_url: str | None = None
    adapter: str | None = None
    service_type: str | None = None
    drive_entity_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.name_path,
            "jsonPointer": self.json_pointer,
            "type": self.entity_type,
            "resourcePath": self.path,
            "_cache": self.cache,
            "accessURL": self.access_url,
            "adapter": self.adapter,
            "serviceType": self.service_type,
            "entityType": self.drive_entity_type,
        }


def list_descriptor_entities(descriptor: Path | str) -> list[ListedEntity]:
    """List descriptor entities and adapter metadata without remote calls."""
    model = DriveCatalog.from_path(str(descriptor))
    model.assert_valid_entity_paths()
    entities: list[ListedEntity] = []
    for reference in model.iter_entity_paths(include_self=False):
        item = reference.model
        service_type = getattr(item, "serviceType", None)
        entities.append(
            ListedEntity(
                name=reference.name_path.split(".")[-1],
                name_path=reference.name_path,
                json_pointer=reference.json_pointer,
                entity_type=reference.entity_type,
                path=getattr(item, "path", None),
                cache=getattr(item, "cache", None),
                access_url=getattr(item, "accessURL", None),
                adapter=adapter_from_service_type(service_type),
                service_type=service_type,
                drive_entity_type=getattr(item, "entityType", None),
            )
        )
    return entities


__all__ = ["ListedEntity", "list_descriptor_entities"]
