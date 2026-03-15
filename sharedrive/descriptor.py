from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


DESCRIPTOR_DEFAULTS_FILE = Path(".sharedrive/sharedrive_set.json")


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


def load_descriptor_defaults_store() -> dict[str, Any]:
    """Load persisted descriptor defaults for global and descriptor scopes."""
    if not DESCRIPTOR_DEFAULTS_FILE.exists():
        return {"global": {}, "descriptors": {}}

    try:
        data = json.loads(DESCRIPTOR_DEFAULTS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"global": {}, "descriptors": {}}

    if not isinstance(data, dict):
        return {"global": {}, "descriptors": {}}
    if not isinstance(data.get("global"), dict):
        data["global"] = {}
    if not isinstance(data.get("descriptors"), dict):
        data["descriptors"] = {}
    return data


def save_descriptor_defaults_store(data: dict[str, Any]) -> None:
    """Persist descriptor defaults store to disk."""
    DESCRIPTOR_DEFAULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    DESCRIPTOR_DEFAULTS_FILE.write_text(
        json.dumps(data, indent=4) + "\n", encoding="utf-8"
    )


def descriptor_scope_key(descriptor: Path | str) -> str:
    """Return the stable key used for descriptor-scoped defaults."""
    return str(Path(descriptor))


def get_saved_params_for_descriptor(descriptor: Path | str | None = None) -> dict[str, Any]:
    """Return merged global and descriptor-scoped saved params."""
    store = load_descriptor_defaults_store()
    merged: dict[str, Any] = {}

    global_params = store.get("global", {})
    if isinstance(global_params, dict):
        merged.update(global_params)

    if descriptor is None:
        return merged

    descriptor_params = store.get("descriptors", {}).get(descriptor_scope_key(descriptor), {})
    if isinstance(descriptor_params, dict):
        merged.update(descriptor_params)
    return merged


def resolve_descriptor_path(descriptor: Path | str | None = None) -> Path:
    """Resolve descriptor path from explicit input, saved defaults, or standard locations."""
    if descriptor is not None:
        return Path(descriptor)

    saved_descriptor = get_saved_params_for_descriptor().get("descriptor")
    if isinstance(saved_descriptor, str) and saved_descriptor.strip():
        return Path(saved_descriptor.strip())

    return resolve_default_descriptor()


def resolve_output_dir(
    output_dir: Path | str | None = None,
    *,
    descriptor: Path | str | None = None,
) -> Path:
    """Resolve output_dir from explicit input, saved defaults, or the standard path."""
    if output_dir is not None:
        return Path(output_dir)

    saved_output_dir = get_saved_params_for_descriptor(descriptor).get("output_dir")
    if isinstance(saved_output_dir, str) and saved_output_dir.strip():
        return Path(saved_output_dir.strip())

    return Path("resources")


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
    "DESCRIPTOR_DEFAULTS_FILE",
    "descriptor_scope_key",
    "load_descriptor_defaults_store",
    "get_saved_params_for_descriptor",
    "get_descriptor_resources",
    "load_descriptor",
    "load_descriptor_document",
    "resolve_descriptor_path",
    "resolve_default_descriptor",
    "resolve_output_dir",
    "save_descriptor_document",
    "save_descriptor_defaults_store",
]