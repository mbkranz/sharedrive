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


def _fetch_from_adapter(resource: Any, source_url: str) -> Any:
    adapter_name = resource_adapter_name(resource, source_url)

    registry = build_service_registry()
    adapter = registry.get(adapter_name)
    if adapter is None or adapter.build_client is None:
        raise NotImplementedError(
            f"fetch is not implemented for adapter '{adapter_name}'."
        )

    client = adapter.build_client()
    return client.get_from_weburl(source_url)


def _sorted_drive_items(items: Iterable[Any]) -> list[Any]:
    return sorted(
        items,
        key=lambda item: (
            str(getattr(item, "path", "") or ""),
            str(getattr(item, "name", "") or ""),
        ),
    )


def _catalog_name_from_item(item: Any) -> str:
    explicit_name = str(getattr(item, "name", "") or "").strip()
    if explicit_name:
        return explicit_name

    item_path = str(getattr(item, "path", "") or "").strip().rstrip("/")
    if item_path:
        return Path(item_path).name or item_path
    return "catalog"


def _catalog_entry_from_item(item: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": _catalog_name_from_item(item),
        "resources": [],
        "catalogs": [],
    }
    source_url = str(getattr(item, "source_url", "") or "").strip()
    if source_url:
        source: dict[str, Any] = {"path": source_url, "entityType": "Directory"}
        service_type = str(getattr(item, "service_type", "") or "").strip()
        if service_type:
            source["serviceType"] = service_type
        entry["sources"] = [source]
    return entry


def _build_catalog_children(
    drive_item: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build direct child resources/catalogs from a runtime item tree."""
    if isinstance(drive_item, DriveFolder):
        direct_children = _sorted_drive_items(
            drive_item.refresh(include_children=True).children
        )
    elif isinstance(drive_item, DriveItem):
        direct_children = [drive_item.refresh(include_children=False)]
    elif getattr(drive_item, "is_directory", False):
        direct_children = _sorted_drive_items(getattr(drive_item, "children", []))
    else:
        direct_children = [drive_item]

    resources: list[dict[str, Any]] = []
    catalogs: list[dict[str, Any]] = []
    for child in direct_children:
        if getattr(child, "is_directory", False):
            catalogs.append(_catalog_entry_from_item(child))
            continue
        resources.append(child.to_dp().to_dict())
    return resources, catalogs


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

    child_resources = _build_child_resources(
        _fetch_from_adapter(resource=package, source_url=source_url)
    )

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


def _fetch_one_catalog(
    catalog: DriveCatalog,
    catalog_name: str,
    *,
    dry_run: bool = False,
    log: LogFn | None = print,
) -> FetchSummary:
    """Fetch direct child metadata into a source-backed catalog."""
    source_url = resource_source_url(catalog)
    if not source_url:
        raise ValueError(f"Catalog '{catalog_name}' has no identifiable source URL.")

    resources, catalogs = _build_catalog_children(
        _fetch_from_adapter(resource=catalog, source_url=source_url)
    )
    generated_entries = len(resources) + len(catalogs)

    if log is not None:
        verb = "Would fetch" if dry_run else "Fetched"
        log(
            f"{verb} metadata for {generated_entries} child entr"
            f"{'y' if generated_entries == 1 else 'ies'} into catalog '{catalog_name}'."
        )

    if not dry_run:
        catalog.resources = [DriveResource.model_validate(item) for item in resources]
        catalog.catalogs = [DriveCatalog.model_validate(item) for item in catalogs]
        catalog.packages = []

    return FetchSummary(
        resource_name=catalog_name,
        generated_resources=generated_entries,
        dry_run=dry_run,
        changed=not dry_run,
    )


def _collect_fetchable_entities_from_catalog(
    catalog: DriveCatalog, catalog_path: str, *, depth: int
) -> list[tuple[str, DrivePackage | DriveCatalog]]:
    """Return fetchable child entities within a catalog.

    With ``depth=0`` (default) only packages at the immediate level of the
    catalog are included, along with immediate source-backed sub-catalogs.
    Increase ``depth`` to recurse into non-source-backed nested catalogs:
    ``depth=1`` includes one level of sub-catalogs, and so on.
    """
    result: list[tuple[str, DrivePackage | DriveCatalog]] = []
    for package in catalog.packages:
        pkg_path = (
            f"{catalog_path}.{package.name}" if catalog_path else str(package.name)
        )
        result.append((pkg_path, package))

    for sub_catalog in catalog.catalogs:
        sub_path = (
            f"{catalog_path}.{sub_catalog.name}"
            if catalog_path
            else str(sub_catalog.name)
        )
        if resource_source_url(sub_catalog):
            result.append((sub_path, sub_catalog))
            continue
        if depth > 0:
            result.extend(
                _collect_fetchable_entities_from_catalog(
                    sub_catalog, sub_path, depth=depth - 1
                )
            )

    return result


def fetch_entity_metadata(
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
    - ``DriveCatalog``: fetch the catalog's own source when present. Otherwise
      fetch immediate child packages and source-backed sub-catalogs. With the
      default ``depth=0`` only the immediate level is considered; increase
      ``depth`` to recurse into non-source-backed nested catalogs. Returns a
      flat list of ``FetchSummary``.
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

    if resource_source_url(entity):
        resolved_name = str(entity.name or entity_selector).strip() or entity_selector
        summary = _fetch_one_catalog(entity, resolved_name, dry_run=dry_run, log=log)
        if not dry_run:
            save_drive_descriptor(descriptor_path, descriptor_model)
        return [summary]

    # DriveCatalog without its own source: collect fetchable descendants.
    fetchable_entities = _collect_fetchable_entities_from_catalog(
        entity, entity_path, depth=depth
    )
    summaries: list[FetchSummary] = []
    for child_path, child_entity in fetchable_entities:
        resolved_name = str(child_entity.name or child_path).strip() or child_path
        if isinstance(child_entity, DrivePackage):
            summary = _fetch_one_package(
                child_entity, resolved_name, dry_run=dry_run, log=log
            )
        else:
            summary = _fetch_one_catalog(
                child_entity, resolved_name, dry_run=dry_run, log=log
            )
        summaries.append(summary)

    if not dry_run and summaries:
        save_drive_descriptor(descriptor_path, descriptor_model)
    return summaries



__all__ = [
    "FetchSummary"
]
