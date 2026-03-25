from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from sharedrive.item import DriveItem
from typing import Any, Callable

from sharedrive.actions.download import resource_adapter_name, resource_source_url
from sharedrive.descriptor import (
    ensure_descriptor_exists,
    get_descriptor_resources,
    load_descriptor_document,
    resource_syncs_to_resources,
    save_descriptor_document,
    source_entity_type,
)

LogFn = Callable[[str], None]


def _build_child_resources(drive_item: "DriveItem", entity_type: str) -> list[dict]:
    """Recursively collect active drive items into passive descriptor metadata blocks."""
    resources = []
    
    if entity_type == "Directory":
        items = drive_item.children
    else:
        items = [drive_item]
        
    for item in items:
        # Convert Pydantic dplib object to serializable dict
        dp_resource = item.to_dp().model_dump(exclude_unset=True, exclude_none=True)
        # Required descriptor structure mappings that don't match frictionless directly 
        # (if any, like serviceType in sources instead of generic dicts, and nested components)
        res_dict = {
            "name": dp_resource.get("name"),
            "path": dp_resource.get("path"),
            "sources": dp_resource.get("sources", [])
        }
        resources.append(res_dict)
    
    return sorted(resources, key=lambda i: str(i.get("path", "")))


@dataclass(slots=True)
class FetchSummary:
    resource_name: str
    generated_resources: int
    dry_run: bool = False
    changed: bool = False


def _fetch_from_adapter(
    resource: dict[str, Any],
    source_url: str,
    googledrive_client_factory: Callable[[], Any] | None,
    sharepoint_client_factory: Callable[[], Any] | None,
) -> list[dict[str, Any]]:
    adapter_name = resource_adapter_name(resource, source_url)
    entity_type = source_entity_type(resource)
    
    if adapter_name == "googledrive":
        if googledrive_client_factory is None:
            from sharedrive.auth.google import default_drive_strategy
            from sharedrive.clients.googledrive import GoogleDriveClient
            client = GoogleDriveClient(credential_strategy=default_drive_strategy())
        else:
            client = googledrive_client_factory()
            
        drive_item = client.get_from_weburl(source_url)
        return _build_child_resources(drive_item, entity_type)

    elif adapter_name == "sharepoint":
        if sharepoint_client_factory is None:
            from sharedrive.auth.settings import make_sharepoint_client_from_microsoft_auth
            client = make_sharepoint_client_from_microsoft_auth()
        else:
            client = sharepoint_client_factory()
            
        drive_item = client.get_from_weburl(source_url)
        return _build_child_resources(drive_item, entity_type)

    else:
        raise NotImplementedError(
            f"fetch is not implemented for adapter '{adapter_name}'."
        )


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
        raise ValueError(f"Resource '{resolved_name}' has no identifiable source URL.")

    child_resources = _fetch_from_adapter(
        resource=resource,
        source_url=source_url,
        googledrive_client_factory=googledrive_client_factory,
        sharepoint_client_factory=sharepoint_client_factory,
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
