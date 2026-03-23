from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from sharedrive.actions.download import resource_adapter_name, resource_source_url
from sharedrive.descriptor import (
    ensure_descriptor_exists,
    get_descriptor_resources,
    resource_syncs_to_resources,
    source_entity_type,
    load_descriptor_document,
    save_descriptor_document,
)

LogFn = Callable[[str], None]


@dataclass(slots=True)
class FetchSummary:
    resource_name: str
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
        "sources": [
            {
                "path": f"https://drive.google.com/open?id={file_id}",
                "serviceType": "GoogleDrive",
                "entityType": "File",
            }
        ],
    }


def _build_sharepoint_child_resource(entry: dict[str, Any]) -> dict[str, Any]:
    relative_path = str(entry.get("relative_path", "")).strip()
    if not relative_path:
        raise ValueError("SharePoint sync entry is missing relative_path")

    web_url = str(entry.get("webUrl", "")).strip()
    if not web_url:
        raise ValueError("SharePoint sync entry is missing webUrl")

    normalized_path = PurePosixPath(relative_path).as_posix()
    return {
        "name": normalized_path,
        "path": normalized_path,
        "sources": [
            {
                "path": web_url,
                "serviceType": "SharePoint",
                "entityType": "File",
            }
        ],
    }


def fetch_resource_metadata_in_descriptor(
    descriptor: Path | str,
    resource_name: str,
    *,
    dry_run: bool = False,
    log: LogFn | None = print,
    googledrive_client_factory: Callable[[], Any] | None = None,
    sharepoint_client_factory: Callable[[], Any] | None = None,
) -> FetchSummary:
    """Fetch metadata for one top-level resource into nested descriptor resources."""
    # TODO: Consider an explicit bulk mode such as `sharedrive fetch --all`
    # once targeted package sync is stable. Keep it opt-in and limit it to
    # sync-eligible package resources, likely with adapter filtering.
    descriptor_path = ensure_descriptor_exists(descriptor)
    normalized_name = resource_name.strip().lower()
    if not normalized_name:
        raise ValueError("resource_name must be a non-empty string")

    document = load_descriptor_document(descriptor_path)
    resources = get_descriptor_resources(document)
    matches = [
        resource
        for resource in resources
        if isinstance(resource, dict)
        and str(resource.get("name", "")).strip().lower() == normalized_name
    ]

    if not matches:
        raise ValueError(f"Resource '{resource_name}' was not found.")
    if len(matches) > 1:
        raise ValueError(f"Resource '{resource_name}' is ambiguous.")

    resource = matches[0]
    resolved_name = str(resource.get("name", resource_name)).strip() or resource_name
    if not resource_syncs_to_resources(resource):
        raise ValueError(
            f"Resource '{resolved_name}' is not configured with syncTarget 'resources'."
        )

    source_url = resource_source_url(resource)
    if not source_url:
        raise ValueError(f"Resource '{resolved_name}' has no source URL.")

    adapter_name = resource_adapter_name(resource, source_url)
    entity_type = source_entity_type(resource)
    if adapter_name == "googledrive":
        if googledrive_client_factory is None:
            from sharedrive.auth.google import default_drive_strategy
            from sharedrive.clients.googledrive import GoogleDriveClient

            client = GoogleDriveClient(credential_strategy=default_drive_strategy())
        else:
            client = googledrive_client_factory()

        if entity_type == "Directory":
            entries = client.list_folder_files_from_weburl(source_url, recursive=True)
        elif entity_type == "File":
            metadata = client.get_from_weburl(source_url, fields="id, name")
            entries = [
                {
                    "id": metadata["id"],
                    "relative_path": str(metadata.get("name", metadata["id"])).strip() or metadata["id"],
                }
            ]
        else:
            raise NotImplementedError(
                f"fetch is not implemented for entityType '{entity_type or 'unknown'}'."
            )

        child_resources = [
            _build_gdrive_child_resource(entry)
            for entry in sorted(entries, key=lambda item: str(item.get("relative_path", "")))
        ]
    elif adapter_name == "sharepoint":
        if sharepoint_client_factory is None:
            from sharedrive.auth.settings import make_sharepoint_client_from_microsoft_auth

            client = make_sharepoint_client_from_microsoft_auth()
        else:
            client = sharepoint_client_factory()

        if entity_type == "Directory":
            entries = client.list_folder_files_from_weburl(source_url, recursive=True)
        elif entity_type == "File":
            metadata = client.get_from_weburl(source_url)
            entries = [
                {
                    "webUrl": str(metadata.get("webUrl", source_url)).strip() or source_url,
                    "relative_path": str(metadata.get("name", metadata.get("id", "item"))).strip()
                    or str(metadata.get("id", "item")),
                }
            ]
        else:
            raise NotImplementedError(
                f"fetch is not implemented for entityType '{entity_type or 'unknown'}'."
            )

        child_resources = [
            _build_sharepoint_child_resource(entry)
            for entry in sorted(entries, key=lambda item: str(item.get("relative_path", "")))
        ]
    else:
        raise NotImplementedError(
            f"fetch is not implemented for adapter '{adapter_name}'."
        )

    if log is not None:
        verb = "Would fetch" if dry_run else "Fetched"
        log(
            f"{verb} metadata for {len(child_resources)} resource(s) into resource '{resolved_name}'."
        )

    if dry_run:
        return FetchSummary(
            resource_name=resolved_name,
            generated_resources=len(child_resources),
            dry_run=True,
            changed=False,
        )

    resource["resources"] = child_resources
    save_descriptor_document(descriptor_path, document)
    return FetchSummary(
        resource_name=resolved_name,
        generated_resources=len(child_resources),
        dry_run=False,
        changed=True,
    )


def fetch_package_metadata_in_descriptor(
    descriptor: Path | str,
    package_name: str,
    *,
    dry_run: bool = False,
    log: LogFn | None = print,
    googledrive_client_factory: Callable[[], Any] | None = None,
    sharepoint_client_factory: Callable[[], Any] | None = None,
) -> FetchSummary:
    """Fetch metadata for one package resource into nested descriptor resources."""
    return fetch_resource_metadata_in_descriptor(
        descriptor=descriptor,
        resource_name=package_name,
        dry_run=dry_run,
        log=log,
        googledrive_client_factory=googledrive_client_factory,
        sharepoint_client_factory=sharepoint_client_factory,
    )


__all__ = [
    "FetchSummary",
    "fetch_resource_metadata_in_descriptor",
    "fetch_package_metadata_in_descriptor",
]