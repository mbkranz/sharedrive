"""Configuration and defaults management for descriptor files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DESCRIPTOR_DEFAULTS_FILE = Path(".sharedrive/sharedrive_set.json")


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


def get_saved_params_for_descriptor(
    descriptor: Path | str | None = None,
) -> dict[str, Any]:
    """Return merged global and descriptor-scoped saved params."""
    store = load_descriptor_defaults_store()
    merged: dict[str, Any] = {}

    global_params = store.get("global", {})
    if isinstance(global_params, dict):
        merged.update(global_params)

    if descriptor is None:
        return merged

    descriptor_params = store.get("descriptors", {}).get(
        descriptor_scope_key(descriptor), {}
    )
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
    "get_saved_params_for_descriptor",
    "load_descriptor_defaults_store",
    "resolve_default_descriptor",
    "resolve_descriptor_path",
    "resolve_output_dir",
    "save_descriptor_defaults_store",
]
