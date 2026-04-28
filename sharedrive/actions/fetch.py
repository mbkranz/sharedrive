from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from sharedrive.actions.download import resource_adapter_name, resource_source_url
from sharedrive.item import DriveFile, DriveFolder, DriveItem
from sharedrive.models import (
    DriveCatalog,
    DrivePackage,
    DriveResource,
    load_drive_descriptor,
    save_drive_descriptor,
)
from sharedrive.registry import get_provider

LogFn = Callable[[str], None]


def _item_to_resource_dict(item: Any) -> dict[str, Any]:
    """Convert a drive item to a :class:`~sharedrive.models.DriveResource` dict.

    Calls ``item.to_dp().to_dict()`` when available.  Falls back to duck-typing
    for lightweight test doubles that expose ``name``, ``path``,
    ``source_url``, and ``service_type`` attributes without subclassing
    :class:`~sharedrive.clients.base.DriveItem`.
    """
    if hasattr(item, "to_dp"):
        return item.to_dp().to_dict()
    name = str(getattr(item, "name", "") or "")
    path_str = str(getattr(item, "path", "") or name)
    source_url_str = str(getattr(item, "source_url", "") or "")
    service_type_str = str(getattr(item, "service_type", "") or "")
    suffix = Path(path_str).suffix.lstrip(".") if path_str else ""
    return DriveResource.from_drive_metadata(
        name=name,
        path=path_str,
        service_type=service_type_str,
        entity_type="File",
        source_url=source_url_str,
        format_str=suffix or None,
    ).to_dict()


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
            _item_to_resource_dict(item)
            for item in sorted(
                leaf_items, key=lambda i: str(getattr(i, "path", "") or "")
            )
        ]

    if isinstance(drive_item, DriveFolder):
        leaf_items = list(drive_item.iter_files())
    else:
        leaf_items = list(_iter_drive_leaf_items(drive_item))
    return [
        _item_to_resource_dict(item)
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

    provider_cls = get_provider(adapter_name)
    if provider_cls is None or not hasattr(provider_cls, "build_default"):
        raise NotImplementedError(
            f"fetch is not implemented for adapter '{adapter_name}'."
        )

    client = provider_cls.build_default()
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
    elif isinstance(drive_item, DriveFile):
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
        resources.append(_item_to_resource_dict(child))
    return resources, catalogs



def _fetch_entity(
    entity,
    catalog,
    *,
    dry_run: bool = False,
    log: LogFn | None = print,
) -> FetchSummary:
    """Fetch direct child metadata into a source-backed catalog."""
    
    sources = getattr(entity, "sources", [])
    for source in sources:
        source_url = resource_source_url(source)
        if source_url:
            break

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


def _fetch_one_package(
    entity: DrivePackage,
    resolved_name: str,
    *,
    dry_run: bool,
    log: LogFn | None,
) -> "FetchSummary":
    """Fetch the remote file listing for a source-backed package.

    Populates ``entity.resources`` with one :class:`~sharedrive.models.DriveResource`
    per remote file (unless *dry_run* is ``True``).
    """
    source_url = resource_source_url(entity)
    if not source_url:
        raise ValueError(f"Package '{resolved_name}' has no identifiable source URL.")

    drive_item = _fetch_from_adapter(resource=entity, source_url=source_url)
    resources = _build_child_resources(drive_item)
    generated_resources = len(resources)

    if log is not None:
        verb = "Would fetch" if dry_run else "Fetched"
        noun = "resource" if generated_resources == 1 else "resources"
        log(f"{verb} metadata for {generated_resources} {noun} into package '{resolved_name}'.")

    if not dry_run:
        entity.resources = [DriveResource.model_validate(r) for r in resources]

    return FetchSummary(
        resource_name=resolved_name,
        generated_resources=generated_resources,
        dry_run=dry_run,
        changed=not dry_run,
    )


def _fetch_one_catalog(
    entity: DriveCatalog,
    resolved_name: str,
    *,
    dry_run: bool,
    log: LogFn | None,
) -> "FetchSummary":
    """Fetch the remote directory listing for a source-backed catalog.

    Populates ``entity.resources`` and ``entity.catalogs`` (unless *dry_run*
    is ``True``).
    """
    source_url = resource_source_url(entity)
    if not source_url:
        raise ValueError(f"Catalog '{resolved_name}' has no identifiable source URL.")

    drive_item = _fetch_from_adapter(resource=entity, source_url=source_url)
    resources, catalogs = _build_catalog_children(drive_item)
    generated_entries = len(resources) + len(catalogs)

    if log is not None:
        verb = "Would fetch" if dry_run else "Fetched"
        noun = "entry" if generated_entries == 1 else "entries"
        log(f"{verb} metadata for {generated_entries} child {noun} into catalog '{resolved_name}'.")

    if not dry_run:
        entity.resources = [DriveResource.model_validate(item) for item in resources]
        entity.catalogs = [DriveCatalog.model_validate(item) for item in catalogs]
        entity.packages = []

    return FetchSummary(
        resource_name=resolved_name,
        generated_resources=generated_entries,
        dry_run=dry_run,
        changed=not dry_run,
    )


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
    entity_selector = entity_selector or ""
    entity = descriptor_model.get_entity_reference(entity_selector)

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
        entity, entity_selector, depth=depth
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



# ---------------------------------------------------------------------------
# Public API aliases
# ---------------------------------------------------------------------------

fetch_entity_metadata_in_descriptor = fetch_entity_metadata
"""Preferred name for :func:`fetch_entity_metadata`.  Returns ``list[FetchSummary]``."""


def fetch_resource_metadata_in_descriptor(
    descriptor: Path | str,
    resource_name: str,
    *,
    dry_run: bool = False,
    log: LogFn | None = print,
) -> FetchSummary:
    """Fetch remote metadata for a single named package in *descriptor*.

    This is a convenience wrapper around :func:`fetch_entity_metadata_in_descriptor`
    that accepts a ``resource_name`` positional argument and returns a single
    :class:`FetchSummary` rather than a list.

    Raises :class:`ValueError` if the entity named *resource_name* is not found
    or if *descriptor* does not exist.
    """
    summaries = fetch_entity_metadata(
        descriptor,
        resource_name,
        dry_run=dry_run,
        log=log,
    )
    return summaries[0]


__all__ = [
    "FetchSummary",
    "fetch_entity_metadata",
    "fetch_entity_metadata_in_descriptor",
    "fetch_resource_metadata_in_descriptor",
]
