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


def _source_path_from_dict(item_dict: dict[str, Any]) -> str | None:
    """Extract the primary source path URL from a fetched resource dict.

    Returns ``None`` when the dict has no ``sources`` list, an empty sources
    list, or a sources entry that lacks a non-empty ``path`` value.
    """
    sources = item_dict.get("sources")
    if not isinstance(sources, list) or not sources:
        return None
    primary = sources[0]
    if not isinstance(primary, dict):
        return None
    path = primary.get("path")
    if isinstance(path, str) and path.strip():
        return path.strip()
    return None


def _merge_fetched_into_existing(
    existing: list[DriveResource | DrivePackage],
    fetched: list[dict[str, Any]],
) -> list[DriveResource | DrivePackage]:
    """Reconcile freshly fetched drive items with existing descriptor resources.

    Matching is keyed on the primary source path (``sources[0].path``).  For
    each fetched item:

    - **Matched** – an existing resource whose primary source path equals the
      fetched item's source path.  The *existing* object is kept as-is so that
      any user-added metadata (titles, descriptions, custom local paths, etc.)
      is preserved.
    - **New** – no existing resource matches the fetched source path.  The
      item is added directly from the fetched data.

    Items present in ``existing`` but *absent* from ``fetched`` are dropped;
    they no longer exist in the remote source.
    """
    existing_by_source: dict[str, DriveResource | DrivePackage] = {}
    for item in existing:
        sp = item.source_path
        if sp:
            existing_by_source[sp] = item

    result: list[DriveResource | DrivePackage] = []
    for fetched_dict in fetched:
        source_url = _source_path_from_dict(fetched_dict)
        if source_url and source_url in existing_by_source:
            result.append(existing_by_source[source_url])
        else:
            result.append(
                DrivePackage.model_validate(fetched_dict)
                if isinstance(fetched_dict.get("resources"), list)
                else DriveResource.model_validate(fetched_dict)
            )
    return result


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
    Freshly fetched items are **merged** with any existing child resources:
    items matched by primary source path retain their existing descriptor
    metadata (titles, descriptions, custom local paths, etc.); new items are
    appended; items no longer present in the remote source are dropped.
    The caller is responsible for saving the descriptor afterwards.
    """
    source_url = resource_source_url(package)
    if not source_url:
        raise ValueError(f"Package '{package_name}' has no identifiable source URL.")

    fetched_items = _fetch_from_adapter(resource=package, source_url=source_url)

    if log is not None:
        verb = "Would fetch" if dry_run else "Fetched"
        log(
            f"{verb} metadata for {len(fetched_items)} resource(s) into package '{package_name}'."
        )

    if not dry_run:
        package.resources = _merge_fetched_into_existing(package.resources, fetched_items)

    return FetchSummary(
        resource_name=package_name,
        generated_resources=len(fetched_items),
        dry_run=dry_run,
        changed=not dry_run,
    )


def _collect_packages_from_catalog(
    catalog: DriveCatalog, catalog_path: str, *, depth: int | None = None
) -> list[tuple[str, DrivePackage]]:
    """Return (dot_path, package) pairs for packages within a catalog.

    With ``depth=None`` (the default) **all** packages at every level of nested
    catalogs are included – this is the "maximum depth" traversal that ensures
    the deepest packages with sources are always reached.  Pass an integer to
    limit the recursion: ``depth=0`` collects only packages at the immediate
    level of the catalog; ``depth=1`` also includes packages in direct
    sub-catalogs; and so on.
    """
    result: list[tuple[str, DrivePackage]] = []
    for package in catalog.packages:
        pkg_path = (
            f"{catalog_path}.{package.name}" if catalog_path else str(package.name)
        )
        result.append((pkg_path, package))

    should_recurse = depth is None or depth > 0
    if should_recurse:
        for sub_catalog in catalog.catalogs:
            sub_path = (
                f"{catalog_path}.{sub_catalog.name}"
                if catalog_path
                else str(sub_catalog.name)
            )
            next_depth = None if depth is None else depth - 1
            result.extend(
                _collect_packages_from_catalog(sub_catalog, sub_path, depth=next_depth)
            )

    return result


def fetch_entity_metadata_in_descriptor(
    descriptor: Path | str,
    entity_selector: str | None,
    *,
    dry_run: bool = False,
    depth: int | None = None,
    log: LogFn | None = print,
) -> list[FetchSummary]:
    """Fetch remote metadata for one entity (package or catalog) in a descriptor.

    Dispatches based on the resolved entity type:

    - ``DrivePackage``: fetch the remote folder's file listing into the
      package's nested resources and merge with any existing children.
      Returns a list with one ``FetchSummary``.
    - ``DriveCatalog``: iterate over **all** packages within the catalog at
      every depth level and fetch each one.  Pass an integer ``depth`` to
      restrict the recursion: ``depth=0`` fetches only packages at the
      immediate level; ``depth=1`` also fetches packages in direct
      sub-catalogs; and so on.  The default (``depth=None``) traverses to the
      maximum depth, reaching every nested package that has a source URL.
      Returns a flat list of ``FetchSummary``, one per package fetched.
    - Standalone ``DriveResource``: raises ``ValueError`` (leaf resources do
      not have a remote listing to fetch).

    Freshly fetched resources are **merged** with existing child entries: items
    whose primary source path matches an existing resource keep the existing
    descriptor metadata; new items are appended; items absent from the remote
    source are dropped.

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

    # DriveCatalog: collect and fetch all packages within it (maximum depth by default)
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
