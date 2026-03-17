from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from sharedrive.actions.fetch import resource_adapter_name, resource_source_url
from sharedrive.descriptor import (
    ensure_descriptor_exists,
    get_descriptor_resources,
    is_package_resource,
    load_descriptor_document,
    save_descriptor_document,
)

LogFn = Callable[[str], None]


@dataclass(slots=True)
class SyncSummary:
    package_name: str
    generated_resources: int
    dry_run: bool = False
    changed: bool = False


def _build_gdrive_child_resource(entry: dict[str, Any]) -> dict[str, Any]:
    # TODO: Evaluate which stable metadata fields are worth persisting for
    # synced file and package resources, such as MIME type, modified time,
    # size, and adapter-specific links.
    relative_path = str(entry.get("relative_path", "")).strip()
    if not relative_path:
        raise ValueError("Google Drive sync entry is missing relative_path")

    file_id = str(entry.get("id", "")).strip()
    if not file_id:
        raise ValueError("Google Drive sync entry is missing id")

    normalized_path = PurePosixPath(relative_path).as_posix()
    return {
        "name": normalized_path,
        "path": normalized_path,
        "sources": [{"path": f"https://drive.google.com/open?id={file_id}"}],
    }


def sync_package_resource_in_descriptor(
    descriptor: Path | str,
    package_name: str,
    *,
    dry_run: bool = False,
    log: LogFn | None = print,
    googledrive_client_factory: Callable[[], Any] | None = None,
) -> SyncSummary:
    """Sync one top-level package resource into nested descriptor resources."""
    # TODO: Consider an explicit bulk mode such as `sharedrive sync --all`
    # once targeted package sync is stable. Keep it opt-in and limit it to
    # sync-eligible package resources, likely with adapter filtering.
    descriptor_path = ensure_descriptor_exists(descriptor)
    normalized_name = package_name.strip().lower()
    if not normalized_name:
        raise ValueError("package_name must be a non-empty string")

    document = load_descriptor_document(descriptor_path)
    resources = get_descriptor_resources(document)
    matches = [
        resource
        for resource in resources
        if isinstance(resource, dict)
        and str(resource.get("name", "")).strip().lower() == normalized_name
    ]

    if not matches:
        raise ValueError(f"Package resource '{package_name}' was not found.")
    if len(matches) > 1:
        raise ValueError(f"Package resource '{package_name}' is ambiguous.")

    resource = matches[0]
    resolved_name = str(resource.get("name", package_name)).strip() or package_name
    if not is_package_resource(resource):
        raise ValueError(f"Resource '{resolved_name}' is not a package resource.")

    source_url = resource_source_url(resource)
    if not source_url:
        raise ValueError(f"Package resource '{resolved_name}' has no source URL.")

    adapter_name = resource_adapter_name(resource, source_url)
    if adapter_name != "googledrive":
        raise NotImplementedError(
            "sync is currently implemented only for Google Drive package resources."
        )

    if googledrive_client_factory is None:
        from sharedrive.auth.google import default_drive_strategy
        from sharedrive.clients.googledrive import GoogleDriveClient

        client = GoogleDriveClient(credential_strategy=default_drive_strategy())
    else:
        client = googledrive_client_factory()

    entries = client.list_folder_files_from_weburl(source_url, recursive=True)
    child_resources = [
        _build_gdrive_child_resource(entry)
        for entry in sorted(entries, key=lambda item: str(item.get("relative_path", "")))
    ]

    if log is not None:
        verb = "Would sync" if dry_run else "Synced"
        log(
            f"{verb} {len(child_resources)} resource(s) for package '{resolved_name}'."
        )

    if dry_run:
        return SyncSummary(
            package_name=resolved_name,
            generated_resources=len(child_resources),
            dry_run=True,
            changed=False,
        )

    resource["resources"] = child_resources
    save_descriptor_document(descriptor_path, document)
    return SyncSummary(
        package_name=resolved_name,
        generated_resources=len(child_resources),
        dry_run=False,
        changed=True,
    )


__all__ = [
    "SyncSummary",
    "sync_package_resource_in_descriptor",
]