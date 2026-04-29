from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Iterable, Optional, TypeVar
from urllib.parse import unquote, urlparse

import pydantic
from pydantic.alias_generators import to_pascal, to_camel
from pydantic import AliasChoices, Field
import yaml
from dplib.models.catalog import Catalog
from dplib.models.package import Package
from dplib.models.resource import Resource
from dplib.models.source import Source
from dplib.system import EntityReference, Model


CATALOG_PROFILE = "data-package-catalog"
T = TypeVar("T", bound=Model)
Entry = Model | dict[str, Any]


SYNC_TARGET_ALIASES = {
    "path": "path",
    "resource": "resources",
    "resources": "resources",
}


def normalize_sync_target(sync_target: str) -> str:
    """Normalize syncTarget to the sharedrive descriptor contract."""
    normalized = sync_target.strip()
    if not normalized:
        raise ValueError("syncTarget must be a non-empty string")

    alias = SYNC_TARGET_ALIASES.get(normalized.lower())
    if alias is not None:
        return alias

    raise ValueError(f"Unsupported syncTarget '{sync_target}'.")


# ---------------------------------------------------------------------------
# Service / entity type normalisation
# ---------------------------------------------------------------------------

_SERVICE_TYPE_ALIASES: dict[str, str] = {
    "googledrive": "GoogleDrive",
    "google_drive": "GoogleDrive",
    "google": "GoogleDrive",
    "sharepoint": "SharePoint",
    "share_point": "SharePoint",
    "s3": "S3",
    "aws_s3": "S3",
}


def normalize_service_type(service_type: str) -> str:
    """Return the canonical capitalization for *service_type*.

    Recognises common aliases and falls back to PascalCase conversion:

    >>> normalize_service_type("googledrive")
    'GoogleDrive'
    >>> normalize_service_type("sharepoint")
    'SharePoint'
    >>> normalize_service_type("s3")
    'S3'
    """
    key = service_type.strip().lower().replace("-", "_").replace(" ", "_")
    canonical = _SERVICE_TYPE_ALIASES.get(key)
    if canonical is not None:
        return canonical
    return to_pascal(service_type.strip())


def normalize_entity_type(entity_type: str) -> str:
    """Return the canonical PascalCase form of *entity_type*.

    >>> normalize_entity_type("file")
    'File'
    >>> normalize_entity_type("directory")
    'Directory'
    """
    return to_pascal(entity_type.strip())


# ---------------------------------------------------------------------------
# Descriptor I/O
# ---------------------------------------------------------------------------


def _empty_catalog_document() -> dict[str, Any]:
    return {
        "$schema": CATALOG_PROFILE,
        "resources": [],
        "packages": [],
        "catalogs": [],
    }


def load_drive_descriptor(
    path: Path | str,
    *,
    create_if_missing: bool = False,
) -> "DriveCatalog":
    """Load a YAML/JSON descriptor from *path* and return a :class:`DriveCatalog`.

    When *create_if_missing* is ``True`` an empty catalog is returned for a
    missing file; otherwise :exc:`FileNotFoundError` is raised.
    """
    file = Path(path)
    if not file.exists():
        if create_if_missing:
            return DriveCatalog.model_validate(_empty_catalog_document())
        raise FileNotFoundError(f"Descriptor '{file}' does not exist.")
    text = file.read_text(encoding="utf-8")
    document = yaml.safe_load(text)
    if document is None:
        document = _empty_catalog_document()
    return DriveCatalog.model_validate(document)


def _catalog_to_serializable(catalog: "DriveCatalog") -> dict[str, Any]:
    """Recursively convert a :class:`DriveCatalog` to a plain dict for YAML output."""
    result: dict[str, Any] = {}
    if getattr(catalog, "name", None):
        result["name"] = catalog.name
    if getattr(catalog, "title", None):
        result["title"] = catalog.title
    sources_list = getattr(catalog, "sources", None)
    if sources_list:
        result["sources"] = [
            s if isinstance(s, dict) else s.to_dict() for s in sources_list
        ]
    result["resources"] = [
        r if isinstance(r, dict) else r.to_dict() for r in (catalog.resources or [])
    ]
    result["packages"] = [
        p if isinstance(p, dict) else p.to_dict() for p in (catalog.packages or [])
    ]
    result["catalogs"] = [
        _catalog_to_serializable(c) if isinstance(c, DriveCatalog) else c
        for c in (catalog.catalogs or [])
    ]
    return result


def save_drive_descriptor(path: Path | str, catalog: "DriveCatalog") -> None:
    """Serialize *catalog* to a YAML descriptor file at *path*."""
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    document = _catalog_to_serializable(catalog)
    document["$schema"] = CATALOG_PROFILE
    # Ensure $schema appears first in the YAML output
    ordered: dict[str, Any] = {"$schema": document.pop("$schema"), **document}
    file.write_text(
        yaml.dump(ordered, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# DriveSourceReference
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DriveSourceReference:
    """A resolved reference to a single source entry on a descriptor resource.

    ``adapter`` is the lower-case registry name (e.g. ``"googledrive"``).
    ``service_type`` is the canonical capitalization (e.g. ``"GoogleDrive"``).
    ``key`` is a URL-safe slug derived from the source ``title``, used to
    namespace generated resources when a descriptor entry has multiple sources
    (design mirrors the way *uv* and *git* use short, stable identifiers for
    remote refs).
    ``target`` carries an optional per-source download-path override.
    """

    adapter: str
    path: str
    entity_type: str
    key: str
    index: int
    service_type: str = ""
    target: str | None = None


def _slugify(text: str) -> str:
    """Return a URL-safe, lower-case slug derived from *text*."""
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug or "source"


def _source_to_ref(source: Any, index: int) -> DriveSourceReference | None:
    """Convert a raw source dict or :class:`DriveSource` model to a reference."""
    if isinstance(source, dict):
        raw_path = source.get("path") or ""
        service_type = source.get("serviceType", "")
        entity_type = source.get("entityType", "File")
        title = source.get("title") or ""
        target = source.get("target") or None
        adapter = service_type.lower() if service_type else ""
    elif isinstance(source, DriveSource):
        raw_path = source.path or ""
        service_type = source.serviceType or ""
        entity_type = source.entityType or "File"
        title = getattr(source, "title", "") or ""
        target = getattr(source, "target", None)
        adapter = source.adapter_name
    else:
        return None

    key = _slugify(title) if title else f"source-{index}"
    return DriveSourceReference(
        adapter=adapter,
        path=raw_path,
        entity_type=entity_type,
        key=key,
        index=index,
        service_type=service_type,
        target=target if isinstance(target, str) else None,
    )


def iter_source_refs(
    entry: Any,
    *,
    parent: Any = None,
) -> list[DriveSourceReference]:
    """Return ordered :class:`DriveSourceReference` objects for *entry*.

    When *entry* carries no ``sources`` the parent's sources are used, enabling
    resources to inherit a parent package's source context (the same pattern
    used by dplib descriptors for path inheritance).
    """
    entry_dict = entry_to_dict(entry)
    sources = entry_dict.get("sources") or []

    if not sources and parent is not None:
        parent_dict = entry_to_dict(parent)
        sources = parent_dict.get("sources") or []

    refs: list[DriveSourceReference] = []
    for index, source in enumerate(sources):
        ref = _source_to_ref(source, index)
        if ref is not None:
            refs.append(ref)
    return refs


# ---------------------------------------------------------------------------
# Descriptor entry helpers
# ---------------------------------------------------------------------------


def entry_to_dict(entry: Any) -> dict[str, Any]:
    """Return *entry* as a plain dict.

    Accepts both pydantic :class:`~dplib.system.Model` instances (calling
    ``to_dict()``) and plain dicts (returned as-is).
    """
    if isinstance(entry, dict):
        return entry
    if isinstance(entry, Model):
        return entry.to_dict()
    return {}


def contained_entries(entry: Any) -> list[Any]:
    """Return the direct child entries of a descriptor entry.

    The hierarchy mirrors the OpenMetadata storage model: catalogs contain
    sub-catalogs, packages, and resources; packages contain resources.
    A leaf resource returns an empty list.
    """
    d = entry_to_dict(entry)
    children: list[Any] = []
    for resource in d.get("resources") or []:
        children.append(resource)
    for package in d.get("packages") or []:
        children.append(package)
    for catalog in d.get("catalogs") or []:
        children.append(catalog)
    return children


def inherited_entry(entry: Any, *, parent: Any = None) -> dict[str, Any]:
    """Return *entry* as a dict with inheritable fields propagated from *parent*.

    Propagates ``path`` by joining the parent's path prefix to the child's
    relative path.  This mirrors the way *dplib* packages declare a ``path``
    root that nested resources are resolved relative to.
    """
    d = dict(entry_to_dict(entry))
    if parent is None:
        return d
    parent_dict = entry_to_dict(parent)
    parent_path = str(parent_dict.get("path") or "").strip()
    if parent_path:
        child_path = str(d.get("path") or "").strip()
        if child_path and not Path(child_path).is_absolute():
            d["path"] = str(Path(parent_path) / child_path)
    return d


def normalize_selector(
    selector: str | Iterable[str] | None,
) -> set[str] | None:
    """Normalise *selector* to a set of stripped name strings, or ``None`` for 'all'.

    A ``None`` return value means every resource is selected; a non-empty set
    means only those names are selected.
    """
    if selector is None:
        return None
    if isinstance(selector, str):
        names = [selector.strip()]
    else:
        names = [name.strip() for name in selector]
    non_empty = [n for n in names if n]
    return set(non_empty) if non_empty else None


def remote_basename(url: str) -> str:
    """Return the last path segment of a URL or path string."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if path:
        return path.split("/")[-1]
    return ""


def resource_selector_path(entry: Any, parent_path: str | None = None) -> str:
    """Return the dot-path selector string for *entry* relative to *parent_path*."""
    d = entry_to_dict(entry)
    name = str(d.get("name") or "").strip()
    if not name:
        return parent_path or ""
    if parent_path:
        return f"{parent_path}.{name}"
    return name


def resource_matches_selector(
    entry: Any,
    selector: set[str] | None,
    *,
    selector_path: str | None = None,
) -> bool:
    """Return ``True`` when *entry* is selected by *selector*.

    ``None`` selects everything.  A non-empty set matches on the entry name,
    the full dot-path selector, or the adapter name of any source.
    """
    if selector is None:
        return True
    d = entry_to_dict(entry)
    name = str(d.get("name") or "").strip()
    if name and name in selector:
        return True
    if selector_path is not None and selector_path in selector:
        return True
    # Also match by adapter / service-type name so callers can select all
    # resources for a given service (e.g. selector="googledrive").
    for ref in iter_source_refs(d):
        if ref.adapter and ref.adapter in selector:
            return True
    return False


def resource_or_descendant_matches_selector(
    entry: Any,
    selector: set[str] | None,
    *,
    parent_selector_path: str | None = None,
) -> bool:
    """Return ``True`` when *entry* or any of its descendants is selected."""
    if selector is None:
        return True
    sel_path = resource_selector_path(entry, parent_selector_path)
    if resource_matches_selector(entry, selector, selector_path=sel_path):
        return True
    for child in contained_entries(entry):
        if resource_or_descendant_matches_selector(
            child, selector, parent_selector_path=sel_path
        ):
            return True
    return False


def sync_target(resource: Any) -> str:
    """Return the normalised sync target for *resource* (``"path"`` or ``"resources"``)."""
    d = entry_to_dict(resource)
    declared = str(d.get("syncTarget") or "").strip()
    if declared:
        return normalize_sync_target(declared)
    nested = d.get("resources")
    if isinstance(nested, list) and nested:
        return "resources"
    return "path"


def selected_adapter_names(
    entries: list[Any],
    selector: str | Iterable[str] | set[str] | None,
) -> list[str]:
    """Return deduplicated adapter names from sources that match *selector*.

    The selector matches on resource name (for download-style selection) *or*
    on adapter name (for auth-check-style selection such as ``selector="sharepoint"``).
    """
    if not isinstance(selector, (set, type(None))):
        selector = normalize_selector(selector)

    adapters: list[str] = []
    seen: set[str] = set()

    def _collect(entry: Any, parent_path: str | None = None) -> None:
        sel_path = resource_selector_path(entry, parent_path)
        by_name = resource_matches_selector(entry, selector, selector_path=sel_path)
        for ref in iter_source_refs(entry):
            by_adapter = selector is not None and ref.adapter in selector
            if (by_name or by_adapter) and ref.adapter and ref.adapter not in seen:
                seen.add(ref.adapter)
                adapters.append(ref.adapter)
        for child in contained_entries(entry):
            _collect(child, sel_path)

    for entry in entries:
        _collect(entry)

    return adapters


def resolve_entity_reference(
    catalog: "DriveCatalog",
    selector: str,
) -> "tuple[str, DriveCatalog | DrivePackage | DriveResource] | None":
    """Find *selector* in *catalog* and return ``(path, entity)`` or ``None``."""
    normalized = selector.strip()
    if not normalized:
        return None
    references = [
        *catalog.iter_entity_paths(include_self=True),
        *catalog.iter_entity_paths(include_self=False),
    ]
    for ref in references:
        if ref.name_path == normalized:
            return ref.name_path, ref.model  # type: ignore[return-value]
    if "." not in normalized:
        for ref in references:
            if ref.name_path.split(".")[-1] == normalized:
                return ref.name_path, ref.model  # type: ignore[return-value]
    return None


class DriveSource(Source):
    path: Annotated[str | None, Field(AliasChoices("path", "url", "uri"))] = None
    serviceType: Annotated[str, pydantic.BeforeValidator(normalize_service_type)]
    entityType: Annotated[str, pydantic.BeforeValidator(normalize_entity_type)]
    title: Optional[str] = None
    target: Optional[str] = None

    @property
    def adapter_name(self) -> str:
        if self.serviceType is not None:
            return self.serviceType.lower()
        elif self.path is not None:
            source_path = self.path or ""
            parsed = urlparse(source_path)
            host = parsed.netloc.lower()
            if parsed.scheme.lower() == "s3":
                return "s3"
            elif "sharepoint.com" in host:
                return "sharepoint"
            elif "drive.google.com" in host:
                return "googledrive"
            else:
                raise ValueError("Source must declare a serviceType or a path with a recognizable host")
        else:
            raise ValueError("Source must declare a serviceType or a path with a recognizable host")

        
    def get_client(self) -> "BaseClient":
        """Build and return a default provider client for this source.

        Lazy import keeps model modules decoupled from provider registry wiring.
        """
        from sharedrive.registry import get_provider

        provider = get_provider(self.adapter_name)
        if provider is None:
            raise NotImplementedError(
                f"No provider registered for '{self.adapter_name}'"
            )
        return provider.build_default()





class DriveResource(Resource):
    sources: list[DriveSource] = pydantic.Field(default_factory=list)
    drive_id: Optional[str] = pydantic.Field(default=None, alias="driveId")
    profile: Optional[str] = None

    @pydantic.field_validator("sources", mode="before")
    @classmethod
    def _coerce_sources(cls, value: Any) -> list[DriveSource]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("sources must be a list")
        return [item if isinstance(item, DriveSource) else DriveSource.model_validate(item) for item in value]

    @property
    def sync_target(self) -> str:
        """Return the declared sync target for a resource.

        `syncTarget` is a sharedrive authoring field. When omitted, resources with
        nested `resources` default to `resources`; everything else defaults to
        `path`.
        """
        declared = getattr(self, "syncTarget", None)
        if isinstance(declared, str) and declared.strip():
            return normalize_sync_target(declared)
        return "resources" if isinstance(self.resources, list) and self.resources else "path"

    @property
    def syncs_to_resources(self) -> bool:
        """Return whether a resource syncs into nested resources."""
        return self.sync_target == "resources"

    @property
    def is_package(self) -> bool:
        return False

    def to_dict(self):
        return Model.to_dict(self)

    @classmethod
    def from_drive_metadata(
        cls,
        *,
        name: str,
        path: str,
        service_type: str,
        entity_type: str,
        source_url: str,
        format_str: Optional[str] = None,
        mediatype: Optional[str] = None,
        drive_id: Optional[str] = None,
        profile: Optional[str] = None,
    ) -> "DriveResource":
        type_str = "table" if format_str in {"csv", "xls", "xlsx"} else "file"
        return cls(
            name=name,
            path=path,
            type=type_str,
            format=format_str,
            mediatype=mediatype,
            driveId=drive_id,
            profile=profile,
            sources=[
                DriveSource(
                    path=source_url,
                    serviceType=service_type,
                    entityType=entity_type,
                )
            ],
        )


def _resolve_entity_reference(
    model: Model,
    name: str,
    entity_types: tuple[type, ...],
) -> EntityReference | None:
    """Find *name* in *model*'s entity tree, restricted to *entity_types*."""
    normalized = name.strip()
    references = [
        *model.iter_entity_paths(include_self=True),
        *model.iter_entity_paths(include_self=False),
    ]
    for ref in references:
        if ref.name_path == normalized and isinstance(ref.model, entity_types):
            return ref
    if "." not in normalized:
        for ref in references:
            if ref.name_path.split(".")[-1] == normalized and isinstance(
                ref.model, entity_types
            ):
                return ref
    return None


def _coerce_drive_entry(value: Any) -> "DriveResource | DrivePackage":
    """Coerce a raw dict into a DriveResource or DrivePackage.

    A dict is treated as a DrivePackage when:
    - it contains a ``resources`` list (populated or empty), OR
    - it declares ``syncTarget: "resources"``

    The second condition handles descriptors whose ``resources: []`` list was
    stripped by ``clean_dict`` during a previous save, ensuring that a
    round-tripped package resource is still recognized as a DrivePackage even
    when its nested resources list is absent from the serialized form.
    """
    if isinstance(value, (DriveResource, DrivePackage)):
        return value
    if not isinstance(value, dict):
        raise ValueError("Drive descriptor resources must be objects")

    # Treat as a package when it has nested resources OR when syncTarget is
    # explicitly set to "resources" (even before any resources are populated).
    if isinstance(value.get("resources"), list) or value.get("syncTarget") == "resources":
        return DrivePackage.model_validate(value)
    return DriveResource.model_validate(value)


class DrivePackage(Package):
    path: Optional[str] = None
    sources: list[DriveSource] = pydantic.Field(default_factory=list)
    drive_id: Optional[str] = pydantic.Field(default=None, alias="driveId")
    resources: list["DriveResource | DrivePackage"] = pydantic.Field(default_factory=list)
    profile: Optional[str] = None

    @pydantic.field_validator("sources", mode="before")
    @classmethod
    def _coerce_sources(cls, value: Any) -> list[DriveSource]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("sources must be a list")
        return [item if isinstance(item, DriveSource) else DriveSource.model_validate(item) for item in value]

    @pydantic.field_validator("resources", mode="before")
    @classmethod
    def _coerce_resources(cls, value: Any) -> list["DriveResource | DrivePackage"]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("resources must be a list")
        return [_coerce_drive_entry(item) for item in value]

    def to_dict(self):
        return Model.to_dict(self)

    @property
    def sync_target(self) -> str:
        """Return the declared sync target for a package-like resource."""
        declared = getattr(self, "syncTarget", None)
        if isinstance(declared, str) and declared.strip():
            return normalize_sync_target(declared)
        return "resources"

    @property
    def is_package(self) -> bool:
        return True

    def get_resource_reference(
        self,
        resource_selector: str,
    ) -> tuple[str, DriveResource | DrivePackage] | None:
        reference = _resolve_entity_reference(
            self,
            resource_selector,
            (DriveResource, DrivePackage),
        )
        if reference is None:
            return None
        return reference.name_path, reference.model


class DriveCatalog(Catalog, json_schema_extra={"$schema": CATALOG_PROFILE}):
    profile: str = pydantic.Field(default=CATALOG_PROFILE, alias="$schema")
    resources: list[DriveResource] = pydantic.Field(default_factory=list)
    packages: list[DrivePackage] = pydantic.Field(default_factory=list)
    catalogs: list["DriveCatalog"] = pydantic.Field(default_factory=list)

    def get_entity_reference(
        self,
        selector: str,
    ) -> "tuple[str, DriveCatalog | DrivePackage | DriveResource] | None":
        """Resolve *selector* to an ``(entity-path, entity)`` pair, or ``None``.

        Accepts both the full dot-path (e.g. ``"research.archive.docs"``) and
        the bare name of the last component when it is unique.
        """
        return resolve_entity_reference(self, selector)


DriveResource.model_rebuild()
DrivePackage.model_rebuild()
DriveCatalog.model_rebuild()


__all__ = [
    # Models
    "DriveCatalog",
    "DrivePackage",
    "DriveResource",
    "DriveSource",
    "DriveSourceReference",
    "Entry",
    # Descriptor I/O
    "load_drive_descriptor",
    "save_drive_descriptor",
    # Normalisation helpers
    "normalize_entity_type",
    "normalize_service_type",
    "normalize_sync_target",
    # Source references
    "iter_source_refs",
    # Entry helpers
    "contained_entries",
    "entry_to_dict",
    "inherited_entry",
    "resolve_entity_reference",
    # Selector helpers
    "normalize_selector",
    "remote_basename",
    "resource_matches_selector",
    "resource_or_descendant_matches_selector",
    "resource_selector_path",
    "selected_adapter_names",
    "sync_target",
    # Constants
    "CATALOG_PROFILE",
]
