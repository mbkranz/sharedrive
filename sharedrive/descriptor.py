from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def load_descriptor_document(path: Path | str) -> dict[str, Any]:
    """Load a JSON/YAML descriptor and return the full top-level document."""
    descriptor_path = Path(path)
    if not descriptor_path.exists():
        return {"resources": []}

    descriptor_text = descriptor_path.read_text(encoding="utf-8")
    if not descriptor_text.strip():
        return {"resources": []}

    suffix = descriptor_path.suffix.lower()
    if suffix == ".json":
        data = json.loads(descriptor_text)
    elif suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(descriptor_text)
    else:
        try:
            data = json.loads(descriptor_text)
        except json.JSONDecodeError:
            data = yaml.safe_load(descriptor_text)

    if data is None:
        return {"resources": []}
    if not isinstance(data, dict):
        raise ValueError("Descriptor must be a top-level JSON/YAML object")
    return data


def get_descriptor_resources(
    document: dict[str, Any], *, create: bool = False
) -> list[dict[str, Any]]:
    """Return the top-level resources list, optionally initializing it."""
    resources = document.get("resources")
    if resources is None and create:
        document["resources"] = []
        resources = document["resources"]

    if not isinstance(resources, list):
        raise ValueError("Descriptor must contain a top-level 'resources' array")
    return resources


def load_descriptor(path: Path | str) -> list[dict[str, Any]]:
    """Load a JSON/YAML descriptor and return the top-level resources list."""
    return get_descriptor_resources(load_descriptor_document(path))


def save_descriptor_document(path: Path | str, document: dict[str, Any]) -> None:
    """Persist a descriptor document as JSON or YAML based on file suffix."""
    descriptor_path = Path(path)
    descriptor_path.parent.mkdir(parents=True, exist_ok=True)

    suffix = descriptor_path.suffix.lower()
    if suffix == ".json":
        descriptor_path.write_text(
            json.dumps(document, indent=2) + "\n",
            encoding="utf-8",
        )
        return

    descriptor_path.write_text(
        yaml.safe_dump(document, sort_keys=False),
        encoding="utf-8",
    )


def resolve_default_descriptor() -> Path:
    """Return the first existing default descriptor path."""
    for candidate in (
        Path("resources/descriptor.yaml"),
        Path("resources/descriptor.yml"),
        Path("resources/descriptor.json"),
    ):
        if candidate.exists():
            return candidate
    return Path("resources/descriptor.yaml")


__all__ = [
    "get_descriptor_resources",
    "load_descriptor",
    "load_descriptor_document",
    "resolve_default_descriptor",
    "save_descriptor_document",
]