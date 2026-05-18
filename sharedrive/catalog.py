from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema

from dplib.models.resource import Resource

from sharedrive.clients.base import AdapterCapabilities, BaseClient
from sharedrive.clients.aws import S3Client
from sharedrive.models import (
    DriveCatalog,
    DriveResource,
    adapter_from_service_type,
    resolve_cache_path,
)
from sharedrive.registry import get_client, get_provider

LogFn = Callable[[str], None]


class CatalogSelector:
    """Normalised selector for catalog entities.

    Accepts a single string (optionally comma-separated), an iterable of
    strings, or ``None``.  Normalises at construction time.

    A ``None`` raw value, an empty input, or the special token ``"all"``
    (case-insensitive) all produce a "select-everything" selector (falsy).
    Any other input yields a truthy selector containing the parsed tokens.

    Designed as a Pydantic-compatible type so it can be used directly as an
    annotation in Pydantic models or with ``validate_call``.  When used in
    plain Python code, construct directly — e.g. ``CatalogSelector(raw_value)``
    — and the normalisation is applied automatically.
    """

    __slots__ = ("_tokens",)

    def __init__(self, raw: "CatalogSelector | str | Iterable[str] | None" = None) -> None:
        if isinstance(raw, CatalogSelector):
            self._tokens = raw.tokens
            return
        if raw is None:
            self._tokens: frozenset[str] | None = None
        else:
            raw_values = [raw] if isinstance(raw, str) else list(raw)
            if not all(isinstance(value, str) for value in raw_values):
                raise TypeError(
                    "selector values must be strings, an iterable of strings, or None"
                )
            values = frozenset(
                stripped
                for raw_value in raw_values
                for part in raw_value.split(",")
                if (stripped := part.strip())
            )
            if not values or "all" in {v.lower() for v in values}:
                self._tokens = None
            else:
                self._tokens = values

    @property
    def tokens(self) -> frozenset[str] | None:
        """The normalised set of filter tokens, or ``None`` for "select all"."""
        return self._tokens

    def __bool__(self) -> bool:
        """False when this is a "select all" selector; True when filtering."""
        return self._tokens is not None

    def __repr__(self) -> str:
        return (
            f"CatalogSelector({sorted(self._tokens)!r})"
            if self._tokens
            else "CatalogSelector()"
        )

    def matches(self, ref: Any) -> bool:
        """Return True if *ref* matches any selector token.

        Always returns True for a "select all" selector.  Otherwise checks
        the ref's ``name_path``, model ``name``, ``entity_type``, and adapter
        name against the stored token set (case-insensitive).
        """
        if self._tokens is None:
            return True
        adapter = adapter_from_service_type(getattr(ref.model, "serviceType", None))
        name = str(getattr(ref.model, "name", "") or "")
        candidates = {ref.name_path, name, ref.entity_type}
        if adapter:
            candidates.add(adapter)
        lower_tokens = {t.lower() for t in self._tokens}
        return any(c.lower() in lower_tokens for c in candidates)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            lambda v: v if isinstance(v, cls) else cls(v),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda s: sorted(s.tokens) if s.tokens is not None else None
            ),
        )


@dataclass(slots=True)
class FetchSummary:
    resource_name: str
    generated_resources: int
    dry_run: bool = False
    changed: bool = False
    failures: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.failures == 0


@dataclass(slots=True)
class DownloadSummary:
    total_resources: int = 0
    downloaded: int = 0
    skipped: int = 0
    dry_run_actions: int = 0
    failures: int = 0

    @property
    def ok(self) -> bool:
        return self.failures == 0


@dataclass(slots=True)
class AuthCheckResult:
    adapter: str
    ok: bool
    message: str

    def to_dict(self) -> dict[str, str | bool]:
        return {"adapter": self.adapter, "ok": self.ok, "message": self.message}


class SharedriveCatalog:
    """Python workflow API for one shared-drive descriptor catalog.

    The object keeps the descriptor model, source path, and adapter client
    cache together.  This makes the Python API mirror the CLI workflow while
    still allowing callers to inspect or modify the loaded catalog before
    saving it.
    """

    def __init__(
        self,
        catalog: DriveCatalog,
        *,
        descriptor_path: Path | str | None = None,
        client_factory: Callable[[str], Any] | None = None,
        provider_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.catalog = catalog
        self.descriptor_path = (
            Path(descriptor_path) if descriptor_path is not None else None
        )
        self.client_factory = client_factory or get_client
        self.provider_factory = provider_factory or get_provider
        self.clients: dict[str, Any] = {}

    @classmethod
    def from_path(cls, path: Path | str) -> "SharedriveCatalog":
        descriptor = Path(path)
        if not descriptor.exists():
            raise FileNotFoundError(f"Descriptor '{descriptor}' does not exist.")
        return cls(DriveCatalog.from_path(str(descriptor)), descriptor_path=descriptor)

    def save(self, path: Path | str | None = None) -> Path:
        """Write the loaded descriptor model to disk.

        ``from_path()`` records the descriptor path, so callers can usually use
        ``save()`` without arguments.  Passing ``path`` supports "save as"
        flows without changing the loaded model.
        """
        target = Path(path) if path is not None else self.descriptor_path
        if target is None:
            raise ValueError(
                "No descriptor path is known. Use SharedriveCatalog.from_path() "
                "or pass an explicit path to save()."
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        self.catalog.to_path(str(target))
        self.descriptor_path = target
        return target

    def client(self, adapter: str) -> Any:
        if adapter not in self.clients:
            self.clients[adapter] = self.client_factory(adapter)
        return self.clients[adapter]

    def _provider_capabilities(self, adapter: str) -> AdapterCapabilities | None:
        provider = self.provider_factory(adapter)
        if provider is None:
            return None
        if isinstance(provider, type) and issubclass(provider, BaseClient):
            return provider.capabilities
        capabilities = getattr(provider, "capabilities", None)
        if isinstance(capabilities, AdapterCapabilities):
            return capabilities
        return AdapterCapabilities()

    @staticmethod
    def _normalize_selector(
        selector: CatalogSelector | str | Iterable[str] | None,
    ) -> CatalogSelector:
        return selector if isinstance(selector, CatalogSelector) else CatalogSelector(selector)

    def references(
        self, selector: CatalogSelector | str | Iterable[str] | None = None
    ) -> list[Any]:
        sel = self._normalize_selector(selector)
        refs = self.catalog.iter_entity_paths(include_self=False)
        if not sel:
            return refs

        selected: list[Any] = []
        selected_prefixes: list[str] = []
        for ref in refs:
            if any(
                ref.name_path.startswith(f"{prefix}.") for prefix in selected_prefixes
            ):
                selected.append(ref)
            elif sel.matches(ref):
                selected.append(ref)
                selected_prefixes.append(ref.name_path)
        return selected

    def resources(
        self, selector: CatalogSelector | str | Iterable[str] | None = None
    ) -> list[DriveResource]:
        sel = self._normalize_selector(selector)
        result: list[DriveResource] = []
        for ref in self.references(sel):
            if isinstance(ref.model, DriveResource):
                result.append(ref.model)
            elif isinstance(ref.model, Resource) and not isinstance(
                ref.model, DriveCatalog
            ):
                result.append(DriveResource.model_validate(ref.model.to_dict()))
        return result

    def adapter_names(
        self, selector: CatalogSelector | str | Iterable[str] | None = None
    ) -> list[str]:
        sel = self._normalize_selector(selector)
        adapters: list[str] = []
        for ref in self.references(sel):
            adapter = adapter_from_service_type(getattr(ref.model, "serviceType", None))
            if adapter and adapter not in adapters:
                adapters.append(adapter)
        return adapters

    def check_auth(
        self,
        selector: CatalogSelector | str | Iterable[str] | None = None,
        *,
        adapters: Iterable[str] | None = None,
    ) -> list[AuthCheckResult]:
        sel = self._normalize_selector(selector)
        names = (
            list(dict.fromkeys(adapter.strip().lower() for adapter in adapters))
            if adapters is not None
            else self.adapter_names(sel)
        )
        return [self._check_one_adapter(adapter) for adapter in names]

    def fetch(
        self,
        selector: CatalogSelector | str | Iterable[str] | None = None,
        *,
        dry_run: bool = False,
        depth: int = -1,
        log: LogFn | None = print,
        persist: bool | Path | str = False,
    ) -> list[FetchSummary]:
        sel = self._normalize_selector(selector)
        catalogs = self._catalogs_to_fetch(sel, depth=depth)
        summaries = [
            self._fetch_one_catalog(catalog, name, dry_run=dry_run, log=log)
            for name, catalog in catalogs
        ]
        if persist and not dry_run and any(summary.changed for summary in summaries):
            self.save(None if persist is True else persist)
        return summaries

    def download(
        self,
        selector: CatalogSelector | str | Iterable[str] | None = None,
        *,
        output_dir: Path | str = Path("resources"),
        dry_run: bool = False,
        check_auth: bool = False,
        log: LogFn | None = print,
        use_cloudpathlib: bool = True,
    ) -> DownloadSummary:
        """Download selected resources into `output_dir / _cache` destinations."""
        sel = self._normalize_selector(selector)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        resources = self.resources(sel)
        summary = DownloadSummary(total_resources=len(resources))
        seen_destinations: dict[str, str] = {}

        if check_auth:
            auth_results = self.check_auth(sel)
            for result in auth_results:
                self._emit(
                    log,
                    f"Auth check {'ready' if result.ok else 'failed'} for {result.adapter}: {result.message}",
                )
            if any(not result.ok for result in auth_results):
                summary.failures += sum(not result.ok for result in auth_results)
                return summary

        for resource in resources:
            try:
                self._download_resource(
                    resource,
                    output_dir=output_dir,
                    dry_run=dry_run,
                    log=log,
                    seen_destinations=seen_destinations,
                    summary=summary,
                    use_cloudpathlib=use_cloudpathlib,
                )
            except Exception as exc:
                if isinstance(exc, ValueError) and "Output collision" in str(exc):
                    raise
                self._emit(
                    log,
                    f"Warning, {resource.name or resource.path or 'resource'} failed: {exc}",
                )
                summary.failures += 1
        return summary

    @staticmethod
    def _emit(log: LogFn | None, message: str) -> None:
        if log is not None:
            log(message)

    def _catalogs_to_fetch(
        self, selector: CatalogSelector, *, depth: int
    ) -> list[tuple[str, DriveCatalog]]:
        if selector.tokens:
            catalogs: list[tuple[str, DriveCatalog]] = []
            for token in sorted(selector.tokens):
                entity = self.catalog.get_entity(token)
                if entity is None:
                    raise ValueError(f"Entity '{token}' was not found in descriptor.")
                if isinstance(entity, DriveResource):
                    raise ValueError(
                        f"Entity '{token}' is a standalone resource. "
                        "Only catalogs with accessURL support fetch."
                    )
                if not isinstance(entity, DriveCatalog):
                    raise ValueError(f"Entity '{token}' is not a fetchable catalog.")
                catalogs.append((str(entity.name or token), entity))
            return catalogs

        catalogs: list[tuple[str, DriveCatalog]] = []
        for ref in self.catalog.iter_entity_paths(include_self=bool(self.catalog.name)):
            if not isinstance(ref.model, DriveCatalog) or not ref.model.accessURL:
                continue
            if (
                depth >= 0
                and ref.name_path.count(".") > depth
                and not self.catalog.name
            ):
                continue
            catalogs.append((ref.name_path, ref.model))
        if self.catalog.accessURL and not catalogs:
            catalogs.append((str(self.catalog.name or "catalog"), self.catalog))
        return catalogs

    def _fetch_one_catalog(
        self, catalog: DriveCatalog, name: str, *, dry_run: bool, log: LogFn | None
    ) -> FetchSummary:
        errors: list[str] = []
        resources: list[DriveResource] = []
        catalogs: list[DriveCatalog] = []

        try:
            if not catalog.accessURL:
                raise ValueError(f"Catalog '{catalog.name}' has no accessURL.")
            capabilities = self._provider_capabilities(catalog.adapter_name)
            if capabilities is not None and not capabilities.supports_fetch:
                raise ValueError(
                    f"Adapter '{catalog.adapter_name}' does not support fetch operations."
                )
            root = self.client(catalog.adapter_name).get_from_weburl(catalog.accessURL)
            children = (
                sorted(
                    root.refresh(include_children=True).children,
                    key=lambda item: (item.path, item.name),
                )
                if root.is_directory
                else [root.refresh(include_children=False)]
            )
            for child in children:
                entry = child.to_resource()
                if isinstance(entry, DriveCatalog):
                    catalogs.append(entry)
                elif isinstance(entry, DriveResource):
                    resources.append(entry)
        except Exception as exc:
            errors.append(f"catalog {name} ({catalog.accessURL}): {exc}")

        count = len(resources) + len(catalogs)
        self._emit(
            log,
            f"{'Would fetch' if dry_run else 'Fetched'} metadata for {count} "
            f"child entr{'y' if count == 1 else 'ies'} into catalog '{name}'.",
        )
        for error in errors:
            self._emit(log, f"Warning, {error}")

        if not dry_run and count:
            catalog.resources = resources
            catalog.catalogs = catalogs
            catalog.packages = []

        return FetchSummary(
            resource_name=name,
            generated_resources=count,
            dry_run=dry_run,
            changed=not dry_run and bool(count),
            failures=len(errors),
            errors=errors,
        )

    def _download_resource(
        self,
        resource: DriveResource,
        *,
        output_dir: Path,
        dry_run: bool,
        log: LogFn | None,
        seen_destinations: dict[str, str],
        summary: DownloadSummary,
        use_cloudpathlib: bool,
    ) -> None:
        if not isinstance(resource.path, str) or not resource.path.strip():
            raise ValueError(f"Resource '{resource.name}' is missing required path.")
        destination = resolve_cache_path(resource, output_dir)
        adapter = resource.adapter_name
        capabilities = self._provider_capabilities(adapter)
        if capabilities is not None and not capabilities.supports_download:
            raise ValueError(
                f"Adapter '{adapter}' does not support download operations."
            )
        self._reserve_destination(
            destination,
            seen=seen_destinations,
            label=f"{adapter}:{resource.name or resource.path}",
        )

        if dry_run:
            self._emit(log, f"Would fetch {resource.path} to {destination}")
            summary.dry_run_actions += 1
            return

        destination.parent.mkdir(parents=True, exist_ok=True)
        if adapter == "s3":
            output_path = self._download_s3_resource(
                resource.path, destination, use_cloudpathlib=use_cloudpathlib
            )
            if output_path is None:
                raise RuntimeError("S3 download returned no output path")
        else:
            item = self.client(adapter).get_from_weburl(resource.path)
            item.download(str(destination))
        summary.downloaded += 1

    def _download_s3_resource(
        self, resource_path: str, destination: Path, *, use_cloudpathlib: bool
    ) -> Path | None:
        s3_client = self.client("s3")
        if not isinstance(s3_client, S3Client):
            raise TypeError("S3 adapter must resolve to an S3Client instance.")
        return s3_client.download_from_weburl(
            resource_path, destination, dry_run=False, use_cloudpathlib=use_cloudpathlib
        )

    @staticmethod
    def _reserve_destination(
        destination: Path, *, seen: dict[str, str], label: str
    ) -> None:
        key = str(
            destination.resolve() if destination.exists() else destination.absolute()
        )
        previous = seen.get(key)
        if previous is not None and previous != label:
            raise ValueError(
                f"Output collision for {destination}: both {previous} and {label} map there."
            )
        seen[key] = label

    def _check_one_adapter(self, adapter: str) -> AuthCheckResult:
        provider = self.provider_factory(adapter)
        if provider is None:
            return AuthCheckResult(adapter, False, f"Unsupported adapter '{adapter}'.")
        capabilities = self._provider_capabilities(adapter)
        supports_auth = (
            capabilities.supports_auth_check if capabilities is not None else True
        )
        if not supports_auth:
            return AuthCheckResult(
                adapter, True, f"Adapter '{adapter}' does not require auth checks."
            )
        try:
            provider.check_auth()
            message = {
                "sharepoint": "SharePoint credentials are ready.",
                "googledrive": "Google Drive credentials are ready.",
                "s3": "AWS credentials are ready for S3 operations.",
            }.get(adapter, f"Adapter '{adapter}' is ready.")
            return AuthCheckResult(adapter, True, message)
        except Exception as exc:
            prefix = {
                "sharepoint": "SharePoint authentication failed",
                "googledrive": "Google Drive authentication failed",
            }.get(adapter, f"Adapter '{adapter}' authentication failed")
            return AuthCheckResult(adapter, False, f"{prefix}: {exc}")


__all__ = [
    "AuthCheckResult",
    "CatalogSelector",
    "DownloadSummary",
    "FetchSummary",
    "SharedriveCatalog",
]
