from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


DESCRIPTOR_DEFAULTS_FILE = Path(".sharedrive/sharedrive_set.json")

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

SYNC_TARGET_ALIASES = {
    "path": "path",
    "resource": "resources",
    "resources": "resources",
}


def check_descriptor_exists(path: Path | str) -> bool:
    """Return True when a descriptor file exists on disk."""
    return Path(path).exists()


def ensure_descriptor_exists(path: Path | str) -> Path:
    """Return descriptor path when it exists, else raise FileNotFoundError."""
    descriptor_path = Path(path)
    if not check_descriptor_exists(descriptor_path):
        raise FileNotFoundError(f"Descriptor '{descriptor_path}' does not exist.")
    return descriptor_path


def load_descriptor_document(path: Path | str) -> dict[str, Any]:
    """Load a JSON/YAML descriptor and return the full top-level document."""
    # TODO: Option #2 - enforce ensure_descriptor_exists() in descriptor utility
    # load entry points when we decide to make strict existence universal here.
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


def get_package_resources(
    resource: dict[str, Any], *, create: bool = False
) -> list[dict[str, Any]]:
    """Return nested resources for a resource, optionally initializing them."""
    resources = resource.get("resources")
    if resources is None:
        if create:
            resource["resources"] = []
            return resource["resources"]
        return []

    if not isinstance(resources, list):
        raise ValueError("Resource must contain a 'resources' array")
    return resources


def get_resource_sources(
    resource: dict[str, Any], *, create: bool = False
) -> list[dict[str, Any]]:
    """Return normalized source entries for a resource.

    Sharedrive keeps execution metadata at the resource level while each source
    entry carries OpenMetadata-aligned source typing such as `serviceType` and
    `entityType`.
    """
    sources = resource.get("sources")
    if sources is None:
        if create:
            resource["sources"] = []
            return resource["sources"]
        return []

    if not isinstance(sources, list):
        raise ValueError("Resource must contain a 'sources' array")
    return sources


def get_primary_source(
    resource: dict[str, Any], *, create: bool = False
) -> dict[str, Any] | None:
    """Return the first source entry for a resource.

    The current descriptor model still treats the first source as the primary
    execution target while leaving room for future multi-source strategies.
    """
    sources = get_resource_sources(resource, create=create)
    if not sources:
        if create:
            source: dict[str, Any] = {}
            sources.append(source)
            return source
        return None

    primary = sources[0]
    if not isinstance(primary, dict):
        raise ValueError("Resource source entries must be objects")
    return primary


def normalize_service_type(service_type: str) -> str:
    """Normalize source service type to OpenMetadata enum spelling."""
    normalized = service_type.strip()
    if not normalized:
        raise ValueError("serviceType must be a non-empty string")

    alias = SERVICE_TYPE_ALIASES.get(normalized.lower())
    if alias is not None:
        return alias

    known_values = set(SERVICE_TYPE_ALIASES.values())
    if normalized in known_values:
        return normalized

    raise NotImplementedError(f"Service type '{service_type}' is not implemented.")


def normalize_entity_type(entity_type: str) -> str:
    """Normalize source entity type to OpenMetadata-style class naming."""
    normalized = entity_type.strip()
    if not normalized:
        raise ValueError("entityType must be a non-empty string")

    alias = ENTITY_TYPE_ALIASES.get(normalized.lower())
    if alias is not None:
        return alias

    known_values = set(ENTITY_TYPE_ALIASES.values())
    if normalized in known_values:
        return normalized

    raise ValueError(f"Unsupported entityType '{entity_type}'.")


def normalize_sync_target(sync_target: str) -> str:
    """Normalize syncTarget to the sharedrive descriptor contract."""
    normalized = sync_target.strip()
    if not normalized:
        raise ValueError("syncTarget must be a non-empty string")

    alias = SYNC_TARGET_ALIASES.get(normalized.lower())
    if alias is not None:
        return alias

    raise ValueError(f"Unsupported syncTarget '{sync_target}'.")


def resource_profile(resource: dict[str, Any]) -> str | None:
    """Return the metadata profile declared for a resource, if any."""
    profile = resource.get("profile")
    if isinstance(profile, str) and profile.strip():
        return profile.strip()
    return None


def resource_sync_target(resource: dict[str, Any]) -> str:
    """Return the declared sync target for a resource.

    `syncTarget` is a sharedrive authoring field. When omitted, resources with
    nested `resources` default to `resources`; everything else defaults to
    `path`.
    """
    declared = resource.get("syncTarget")
    if isinstance(declared, str) and declared.strip():
        return normalize_sync_target(declared)
    return "resources" if isinstance(resource.get("resources"), list) else "path"


def resource_syncs_to_resources(resource: dict[str, Any]) -> bool:
    """Return whether a resource syncs into nested resources."""
    return resource_sync_target(resource) == "resources"


def source_path(resource: dict[str, Any]) -> str | None:
    """Return the primary source locator path for a resource."""
    primary = get_primary_source(resource)
    if primary is not None:
        path = primary.get("path")
        if isinstance(path, str) and path.strip():
            return path.strip()

    legacy_source = resource.get("source")
    if isinstance(legacy_source, str) and legacy_source.strip():
        return legacy_source.strip()
    return None


def source_service_type(resource: dict[str, Any]) -> str | None:
    """Return the canonical service type for a resource source."""
    primary = get_primary_source(resource)
    if primary is not None:
        service_type = primary.get("serviceType")
        if isinstance(service_type, str) and service_type.strip():
            return normalize_service_type(service_type)

    legacy_service_type = resource.get("serviceType")
    if isinstance(legacy_service_type, str) and legacy_service_type.strip():
        return normalize_service_type(legacy_service_type)

    legacy_drive_service = resource.get("driveService")
    if isinstance(legacy_drive_service, str) and legacy_drive_service.strip():
        return normalize_service_type(legacy_drive_service)
    return None


def source_entity_type(resource: dict[str, Any]) -> str | None:
    """Return the canonical entity type for a resource source, if declared."""
    primary = get_primary_source(resource)
    if primary is None:
        return None

    entity_type = primary.get("entityType")
    if isinstance(entity_type, str) and entity_type.strip():
        return normalize_entity_type(entity_type)
    return None


def service_type_adapter_name(service_type: str) -> str:
    """Return the runtime adapter name for a canonical service type."""
    normalized = normalize_service_type(service_type)
    return {
        "GoogleDrive": "googledrive",
        "SharePoint": "sharepoint",
        "S3": "s3",
    }[normalized]


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
    "ENTITY_TYPE_ALIASES",
    "SERVICE_TYPE_ALIASES",
    "SYNC_TARGET_ALIASES",
    "check_descriptor_exists",
    "get_primary_source",
    "ensure_descriptor_exists",
    "descriptor_scope_key",
    "get_descriptor_resources",
    "get_resource_sources",
    "get_package_resources",
    "get_saved_params_for_descriptor",
    "load_descriptor",
    "load_descriptor_defaults_store",
    "load_descriptor_document",
    "normalize_entity_type",
    "normalize_service_type",
    "normalize_sync_target",
    "resolve_descriptor_path",
    "resolve_default_descriptor",
    "resolve_output_dir",
    "save_descriptor_document",
    "save_descriptor_defaults_store",
    "resource_profile",
    "resource_sync_target",
    "resource_syncs_to_resources",
    "service_type_adapter_name",
    "source_entity_type",
    "source_path",
    "source_service_type",
]