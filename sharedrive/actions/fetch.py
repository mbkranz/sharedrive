from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from sharedrive.actions.download import resource_adapter_name, resource_source_url
from sharedrive.item import DriveFolder, DriveItem
from sharedrive.models import (
    DriveCatalog,
    DrivePackage,
    DriveResource,
    load_drive_descriptor,
    save_drive_descriptor,
)
from sharedrive.registry import build_service_registry

LogFn = Callable[[str], None]


def _iter_drive_leaf_items(item: Any) -> Iterable[Any]:
    """Recursively yield non-directory children from a drive item tree.

    Works with any object that exposes ``is_directory`` and ``children``
    attributes, including concrete ``DriveFolder`` subclasses and lightweight
    test doubles without the ``iter_files`` method.
    """
    if getattr(item, "is_directory", False):
        for child in item.children:
            yield from _iter_drive_leaf_items(child)
    else:
        yield item


def _build_child_resources(drive_item: Any) -> list[dict[str, Any]]:
    """Build sorted resource dicts from runtime leaf file items.

    Runtime ``DriveItem`` instances are refreshed before traversal. Lightweight
    test doubles that do not inherit from ``DriveItem`` are traversed
    structurally without refresh support.
    """
    if isinstance(drive_item, DriveItem):
        refreshed_item = drive_item.refresh_tree()
        if isinstance(refreshed_item, DriveFolder):
            leaf_items = list(refreshed_item.iter_files())
        elif getattr(refreshed_item, "is_directory", False):
            leaf_items = list(_iter_drive_leaf_items(refreshed_item))
        else:
            leaf_items = [refreshed_item]
        return [
            item.to_dp().to_dict()
            for item in sorted(
                leaf_items, key=lambda i: str(getattr(i, "path", "") or "")
            )
        ]

    if isinstance(drive_item, DriveFolder):
        leaf_items = list(drive_item.iter_files())
    else:
        leaf_items = list(_iter_drive_leaf_items(drive_item))
    return [
        item.to_dp().to_dict()
        for item in sorted(leaf_items, key=lambda i: str(getattr(i, "path", "") or ""))
    ]


@dataclass(slots=True)
class FetchSummary:
    resource_name: str
    generated_resources: int
    dry_run: bool = False
    changed: bool = False


def _fetch_from_adapter(resource: Any, source_url: str) -> list[dict[str, Any]]:
    adapter_name = resource_adapter_name(resource, source_url)

    registry = build_service_registry()
    adapter = registry.get(adapter_name)
    if adapter is None or adapter.build_client is None:
        raise NotImplementedError(
            f"fetch is not implemented for adapter '{adapter_name}'."
        )

    client = adapter.build_client()
    drive_item = client.get_from_weburl(source_url)
    return _build_child_resources(drive_item)


def _fetch_one_package(
    package: DrivePackage,
    package_name: str,
    *,
    dry_run: bool = False,
    log: LogFn | None = print,
) -> FetchSummary:
    """Fetch remote folder metadata into a package's resources list.

    Mutates ``package.resources`` in-place when ``dry_run`` is ``False``.
    The caller is responsible for saving the descriptor afterwards.
    """
    source_url = resource_source_url(package)
    if not source_url:
        raise ValueError(f"Package '{package_name}' has no identifiable source URL.")

    child_resources = _fetch_from_adapter(resource=package, source_url=source_url)

    if log is not None:
        verb = "Would fetch" if dry_run else "Fetched"
        log(
            f"{verb} metadata for {len(child_resources)} resource(s) into package '{package_name}'."
        )

    if not dry_run:
        package.resources = [
            DrivePackage.model_validate(item)
            if isinstance(item.get("resources"), list)
            else DriveResource.model_validate(item)
            for item in child_resources
        ]

    return FetchSummary(
        resource_name=package_name,
        generated_resources=len(child_resources),
        dry_run=dry_run,
        changed=not dry_run,
    )


def _collect_packages_from_catalog(
    catalog: DriveCatalog, catalog_path: str, *, depth: int
) -> list[tuple[str, DrivePackage]]:
    """Return (dot_path, package) pairs for packages within a catalog.

    With ``depth=0`` (default) only packages at the immediate level of the
    catalog are included.  Increase ``depth`` to also collect packages from
    nested catalogs: ``depth=1`` includes one level of sub-catalogs, and so on.
    """
    result: list[tuple[str, DrivePackage]] = []
    for package in catalog.packages:
        pkg_path = (
            f"{catalog_path}.{package.name}" if catalog_path else str(package.name)
        )
        result.append((pkg_path, package))

    if depth > 0:
        for sub_catalog in catalog.catalogs:
            sub_path = (
                f"{catalog_path}.{sub_catalog.name}"
                if catalog_path
                else str(sub_catalog.name)
            )
            result.extend(
                _collect_packages_from_catalog(sub_catalog, sub_path, depth=depth - 1)
            )

    return result


def fetch_entity_metadata_in_descriptor(
    descriptor: Path | str,
    entity_selector: str | None,
    *,
    dry_run: bool = False,
    depth: int = 0,
    log: LogFn | None = print,
) -> list[FetchSummary]:
    """Fetch remote metadata for one entity (package or catalog) in a descriptor.

    Dispatches based on the resolved entity type:

    - ``DrivePackage``: fetch the remote folder's file listing into the
      package's nested resources.  Returns a list with one ``FetchSummary``.
    - ``DriveCatalog``: iterate over packages within the catalog and fetch
      each one.  With the default ``depth=0`` only packages at the immediate
      level are fetched; increase ``depth`` to recurse into nested catalogs.
      Returns a flat list of ``FetchSummary``, one per package fetched.
    - Standalone ``DriveResource``: raises ``ValueError`` (leaf resources do
      not have a remote listing to fetch).

    The descriptor is saved once after all updates when ``dry_run`` is ``False``.
    """
    descriptor_path = Path(descriptor)
    descriptor_model = load_drive_descriptor(descriptor_path)

    if entity_selector:
        entity_selector = entity_selector.strip()
    else:
        entity_selector = ""

    if not entity_selector:
        entity_path = ""
        entity: DriveCatalog | DrivePackage | DriveResource = descriptor_model
    else:
        resolved = descriptor_model.get_entity_reference(entity_selector)
        if resolved is None:
            raise ValueError(f"Entity '{entity_selector}' was not found in descriptor.")
        entity_path, entity = resolved

    if isinstance(entity, DriveResource) and not isinstance(entity, DrivePackage):
        raise ValueError(
            f"Entity '{entity_path or entity_selector}' is a standalone resource. "
            "Only packages (syncTarget: resources) and catalogs support fetch."
        )

    if isinstance(entity, DrivePackage):
        resolved_name = str(entity.name or entity_selector).strip() or entity_selector
        summary = _fetch_one_package(entity, resolved_name, dry_run=dry_run, log=log)
        if not dry_run:
            save_drive_descriptor(descriptor_path, descriptor_model)
        return [summary]

    # DriveCatalog: collect and fetch all packages within it (flat by default)
    packages = _collect_packages_from_catalog(entity, entity_path, depth=depth)
    summaries: list[FetchSummary] = []
    for pkg_path, package in packages:
        resolved_name = str(package.name or pkg_path).strip() or pkg_path
        summary = _fetch_one_package(package, resolved_name, dry_run=dry_run, log=log)
        summaries.append(summary)

    if not dry_run and summaries:
        save_drive_descriptor(descriptor_path, descriptor_model)
    return summaries


def fetch_resource_metadata_in_descriptor(
    descriptor: Path | str,
    resource_name: str,
    *,
    dry_run: bool = False,
    log: LogFn | None = print,
) -> FetchSummary:
    """Fetch metadata for one package resource into nested descriptor resources.

    Prefer :func:`fetch_entity_metadata_in_descriptor` which also handles
    ``DriveCatalog`` entities and returns a list of results.
    """
    descriptor_path = Path(descriptor)
    if not resource_name.strip():
        raise ValueError("resource_name must be a non-empty string")

    descriptor_model = load_drive_descriptor(descriptor_path)
    resolved_reference = descriptor_model.get_resource_reference(resource_name)
    if resolved_reference is None:
        raise ValueError(f"Resource '{resource_name}' was not found.")

    _, resource = resolved_reference
    resolved_name = str(resource.name or resource_name).strip() or resource_name
    if not isinstance(resource, DrivePackage):
        raise ValueError(
            f"Resource '{resolved_name}' must have syncTarget 'resources' to use fetch. "
            "Only package resources (syncTarget: resources) can have their remote "
            "metadata fetched into nested descriptor resources."
        )

    summary = _fetch_one_package(resource, resolved_name, dry_run=dry_run, log=log)
    if not dry_run:
        save_drive_descriptor(descriptor_path, descriptor_model)
    return summary


def fetch_package_metadata_in_descriptor(
    descriptor: Path | str,
    package_name: str,
    *,
    dry_run: bool = False,
    log: LogFn | None = print,
) -> FetchSummary:
    return fetch_resource_metadata_in_descriptor(
        descriptor=descriptor, resource_name=package_name, dry_run=dry_run, log=log
    )


__all__ = [
    "FetchSummary",
    "fetch_entity_metadata_in_descriptor",
    "fetch_resource_metadata_in_descriptor",
    "fetch_package_metadata_in_descriptor",
]
