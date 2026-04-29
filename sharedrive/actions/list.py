"""Local descriptor listing helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sharedrive.models import iter_source_refs, load_drive_descriptor


@dataclass(frozen=True, slots=True)
class ListedSource:
    index: int
    key: str
    path: str
    adapter: str
    service_type: str | None
    entity_type: str | None
    title: str | None = None
    target: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "key": self.key,
            "title": self.title,
            "path": self.path,
            "adapter": self.adapter,
            "serviceType": self.service_type,
            "entityType": self.entity_type,
            "target": self.target,
        }


@dataclass(frozen=True, slots=True)
class ListedEntity:
    name: str
    name_path: str
    json_pointer: str
    entity_type: str
    sources: list[ListedSource] = field(default_factory=list)
    source_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.name_path,
            "jsonPointer": self.json_pointer,
            "type": self.entity_type,
            "sources": [source.to_dict() for source in self.sources],
            "sourceError": self.source_error,
        }


def list_descriptor_entities(descriptor: Path | str) -> list[ListedEntity]:
    """List descriptor entities and source metadata without remote calls."""
    model = load_drive_descriptor(descriptor)
    model.assert_valid_entity_paths()
    entities: list[ListedEntity] = []
    for reference in model.iter_entity_paths(include_self=False):
        source_error = None
        sources: list[ListedSource] = []
        try:
            source_refs = iter_source_refs(reference.model)
        except ValueError as exc:
            source_refs = []
            source_error = str(exc)

        source_documents = reference.model.to_dict().get("sources")
        if not isinstance(source_documents, list):
            source_documents = []

        for source_ref in source_refs:
            source_document = (
                source_documents[source_ref.index]
                if source_ref.index < len(source_documents)
                and isinstance(source_documents[source_ref.index], dict)
                else {}
            )
            title = source_document.get("title")
            sources.append(
                ListedSource(
                    index=source_ref.index,
                    key=source_ref.key,
                    title=title.strip() if isinstance(title, str) and title.strip() else None,
                    path=source_ref.path,
                    adapter=source_ref.adapter,
                    service_type=source_ref.service_type,
                    entity_type=source_ref.entity_type,
                    target=source_ref.target,
                )
            )

        entities.append(
            ListedEntity(
                name=reference.name_path.split(".")[-1],
                name_path=reference.name_path,
                json_pointer=reference.json_pointer,
                entity_type=reference.entity_type,
                sources=sources,
                source_error=source_error,
            )
        )
    return entities


__all__ = ["ListedEntity", "ListedSource", "list_descriptor_entities"]
