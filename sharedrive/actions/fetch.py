from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from sharedrive.item import DriveItem
from typing import Any, Callable

from sharedrive.actions.download import resource_adapter_name, resource_source_url
from sharedrive.models import (
    DrivePackage,
    DriveResource,
    load_drive_descriptor,
    save_drive_descriptor,
)

LogFn = Callable[[str], None]


def _build_child_resources(drive_item: "DriveItem") -> list[dict[str, Any]]:
    entry = drive_item.to_dp()
    if isinstance(entry, DrivePackage):
        items: list[DriveResource | DrivePackage] = entry.resources
    else:
        items = [entry]
    return [
        item.to_dict()
        for item in sorted(items, key=lambda item: str(item.path or ""))
    ]


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

    if adapter_name == "googledrive":
        if googledrive_client_factory is None:
            from sharedrive.auth.google import default_drive_strategy
            from sharedrive.clients.googledrive import GoogleDriveClient
            client = GoogleDriveClient(credential_strategy=default_drive_strategy())
        else:
            client = googledrive_client_factory()

        drive_item = client.get_from_weburl(source_url)
        return _build_child_resources(drive_item)

    elif adapter_name == "sharepoint":
        if sharepoint_client_factory is None:
            from sharedrive.auth.settings import make_sharepoint_client_from_microsoft_auth
            client = make_sharepoint_client_from_microsoft_auth()
        else:
            client = sharepoint_client_factory()

        drive_item = client.get_from_weburl(source_url)
        return _build_child_resources(drive_item)

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
    descriptor_path = Path(descriptor)
    normalized_name = resource_name.strip().lower()
    if not normalized_name:
        raise ValueError("resource_name must be a non-empty string")

    descriptor_model = load_drive_descriptor(descriptor_path)
    resolved_reference = descriptor_model.get_resource_reference(resource_name)
    if resolved_reference is None:
        raise ValueError(f"Resource '{resource_name}' was not found.")

    _, resource = resolved_reference
    resolved_name = str(resource.name or resource_name).strip() or resource_name
    if not isinstance(resource, DrivePackage):
        raise ValueError(
            f"Resource '{resolved_name}' is not a package resource."
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

    resource.resources = [
        DrivePackage.model_validate(item)
        if isinstance(item.get("resources"), list)
        else DriveResource.model_validate(item)
        for item in child_resources
    ]
    save_drive_descriptor(descriptor_path, descriptor_model)
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
