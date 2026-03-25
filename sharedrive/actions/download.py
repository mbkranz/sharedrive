from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

from sharedrive.clients.aws import check_s3_credentials, download_s3_url
from sharedrive.models import (
    load_drive_descriptor,
    normalize_entity_type,
    normalize_service_type,
)

LogFn = Callable[[str], None]


def ensure_descriptor_exists(path: Path | str) -> Path:
    descriptor_path = Path(path)
    if not descriptor_path.exists():
        raise FileNotFoundError(f"Descriptor '{descriptor_path}' does not exist.")
    return descriptor_path


def resolve_default_descriptor() -> Path:
    for candidate in (
        Path("resources/descriptor.yaml"),
        Path("resources/descriptor.yml"),
        Path("resources/descriptor.json"),
    ):
        if candidate.exists():
            return candidate
    return Path("resources/descriptor.yaml")


def load_descriptor(path: Path | str) -> list[dict[str, Any]]:
    descriptor = load_drive_descriptor(path)
    return descriptor.to_dict().get("resources", [])


def get_package_resources(
    resource: dict[str, Any],
    *,
    create: bool = False,
) -> list[dict[str, Any]]:
    resources = resource.get("resources")
    if resources is None:
        if create:
            resource["resources"] = []
            return resource["resources"]
        return []
    if not isinstance(resources, list):
        raise ValueError("Resource must contain a 'resources' array")
    return resources


def get_primary_source(
    resource: dict[str, Any],
    *,
    create: bool = False,
) -> dict[str, Any] | None:
    sources = resource.get("sources")
    if sources is None:
        if create:
            resource["sources"] = [{}]
            return resource["sources"][0]
        return None
    if not isinstance(sources, list):
        raise ValueError("Resource must contain a 'sources' array")
    if not sources:
        if create:
            sources.append({})
            return sources[0]
        return None
    primary = sources[0]
    if not isinstance(primary, dict):
        raise ValueError("Resource source entries must be objects")
    return primary


def service_type_adapter_name(service_type: str) -> str:
    normalized = normalize_service_type(service_type)
    return {
        "GoogleDrive": "googledrive",
        "SharePoint": "sharepoint",
        "S3": "s3",
    }[normalized]


def source_path(resource: Any) -> str | None:
    source_value = getattr(resource, "source_path", None)
    if isinstance(source_value, str) and source_value.strip():
        return source_value.strip()

    primary = get_primary_source(resource)
    if primary is None:
        return None
    value = primary.get("path")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def source_service_type(resource: Any) -> str | None:
    service_value = getattr(resource, "source_service_type", None)
    if isinstance(service_value, str) and service_value.strip():
        return normalize_service_type(service_value)

    primary = get_primary_source(resource)
    if primary is None:
        return None
    value = primary.get("serviceType")
    if isinstance(value, str) and value.strip():
        return normalize_service_type(value)
    return None


def source_entity_type(resource: Any) -> str | None:
    entity_value = getattr(resource, "source_entity_type", None)
    if isinstance(entity_value, str) and entity_value.strip():
        return normalize_entity_type(entity_value)

    primary = get_primary_source(resource)
    if primary is None:
        return None
    value = primary.get("entityType")
    if isinstance(value, str) and value.strip():
        return normalize_entity_type(value)
    return None


def resource_sync_target(resource: dict[str, Any]) -> str:
    declared = resource.get("syncTarget")
    if declared == "resources":
        return "resources"
    return "resources" if isinstance(resource.get("resources"), list) else "path"


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
        return {
            "adapter": self.adapter,
            "ok": self.ok,
            "message": self.message,
        }


def resource_source_url(resource: Any) -> str | None:
    """Resolve the primary source locator for a resource."""
    return source_path(resource)


def resource_output_path(resource: dict[str, Any], output_dir: Path) -> Path:
    """Resolve resource.path against output_dir unless path is absolute."""
    path_value = resource.get("path")
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValueError("Resource is missing required string field 'path'")

    path = Path(path_value.strip())
    if path.is_absolute():
        return path
    return output_dir / path


def resource_output_paths(resource: dict[str, Any], output_dir: Path) -> list[Path]:
    """Resolve primary resource.path plus optional targets[] into local output paths."""

    def _resolve_local_path(path_value: str) -> Path:
        path = Path(path_value.strip())
        if path.is_absolute():
            return path
        return output_dir / path

    paths: list[Path] = [resource_output_path(resource, output_dir)]
    targets = resource.get("targets")
    if targets is None:
        return paths

    target_values: list[str] = []
    if isinstance(targets, str):
        target_values.append(targets)
    elif isinstance(targets, dict):
        target_path = targets.get("path")
        if isinstance(target_path, str) and target_path.strip():
            target_values.append(target_path)
        else:
            raise ValueError("Target object must include a non-empty string 'path'")
    elif isinstance(targets, list):
        for idx, target in enumerate(targets):
            if isinstance(target, str) and target.strip():
                target_values.append(target)
            elif isinstance(target, dict):
                target_path = target.get("path")
                if isinstance(target_path, str) and target_path.strip():
                    target_values.append(target_path)
                else:
                    raise ValueError(
                        f"Target at index {idx} must include a non-empty string 'path'"
                    )
            else:
                raise ValueError(
                    "targets must contain strings or objects with 'path' values"
                )
    else:
        raise ValueError(
            "targets must be a string, object with 'path', or list of target entries"
        )

    deduped: dict[str, Path] = {str(paths[0]): paths[0]}
    for target_value in target_values:
        resolved = _resolve_local_path(target_value)
        deduped.setdefault(str(resolved), resolved)
    return list(deduped.values())


def resource_adapter_name(resource: Any, source_url: str | None) -> str:
    """Resolve runtime adapter name from source serviceType or fallback inference."""
    service_type = source_service_type(resource)
    if service_type is not None:
        return service_type_adapter_name(service_type)

    adapter = resource.get("driveService")
    if isinstance(adapter, str) and adapter.strip():
        return service_type_adapter_name(adapter.strip())

    legacy_adapter = resource.get("x-adapter")
    if isinstance(legacy_adapter, str) and legacy_adapter.strip():
        return legacy_adapter.strip().lower()

    if not source_url:
        return "unknown"

    if urlparse(source_url).scheme.lower() == "s3":
        return "s3"

    host = urlparse(source_url).netloc.lower()
    if "sharepoint.com" in host:
        return "sharepoint"
    if "google.com" in host:
        return "googledrive"
    if host.startswith("www."):
        host = host[4:]
    return host.split(".")[0] if host else "unknown"


def _normalize_include(include: str | Iterable[str]) -> set[str]:
    if isinstance(include, str):
        include_items = [include]
    else:
        include_items = list(include)
    flattened: list[str] = []
    for item in include_items:
        if not item:
            continue
        flattened.extend(part.strip() for part in str(item).split(","))
    normalized = {item.lower() for item in flattened if item}
    return normalized or {"all"}


def _default_sharepoint_client_factory() -> Any:
    from sharedrive.auth.settings import make_sharepoint_client_from_microsoft_auth

    return make_sharepoint_client_from_microsoft_auth()


def _default_googledrive_client_factory() -> Any:
    from sharedrive.auth.google import default_drive_strategy
    from sharedrive.clients.googledrive import GoogleDriveClient

    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    return GoogleDriveClient(
        credential_strategy=default_drive_strategy(credentials_path=credentials_path)
    )


def _resource_selector_path(
    resource: dict[str, Any],
    parent_selector_path: str | None = None,
) -> str:
    resource_name = str(resource.get("name", "")).strip() or "resource"
    if parent_selector_path is None:
        return resource_name
    return f"{parent_selector_path}.{resource_name}"


def _selected_adapter_names(
    resources: Iterable[dict[str, Any]],
    include: str | Iterable[str] = "all",
) -> list[str]:
    include_set = _normalize_include(include)
    selected: list[str] = []
    seen: set[str] = set()

    def collect(
        resource: dict[str, Any],
        parent: dict[str, Any] | None = None,
        parent_selector_path: str | None = None,
    ) -> None:
        normalized = _inherit_resource_defaults(resource, parent=parent)
        selector_path = _resource_selector_path(normalized, parent_selector_path)
        children = get_package_resources(normalized)

        if children:
            parent_selected = _resource_matches_include(
                normalized,
                include_set,
                selector_path=selector_path,
            )
            for child in children:
                if isinstance(child, dict):
                    child_resource = _inherit_resource_defaults(child, parent=normalized)
                    if parent_selected or _resource_or_descendant_matches_include(
                        child_resource,
                        include_set,
                        parent_selector_path=selector_path,
                    ):
                        collect(child, parent=normalized, parent_selector_path=selector_path)
            return

        source_url = resource_source_url(normalized)
        adapter_name = resource_adapter_name(normalized, source_url)

        if not _resource_matches_include(
            normalized,
            include_set,
            selector_path=selector_path,
        ):
            return

        if adapter_name not in seen:
            seen.add(adapter_name)
            selected.append(adapter_name)

    for index, resource in enumerate(resources):
        if not isinstance(resource, dict):
            continue
        normalized = dict(resource)
        normalized.setdefault("name", f"resource[{index}]")
        collect(normalized)

    return selected


def _inherit_resource_defaults(
    resource: dict[str, Any],
    *,
    parent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = dict(resource)
    if parent is None:
        return normalized

    parent_path = parent.get("path")
    resource_path = normalized.get("path")
    if (
        isinstance(parent_path, str)
        and parent_path.strip()
        and isinstance(resource_path, str)
        and resource_path.strip()
    ):
        child_path = Path(resource_path.strip())
        if not child_path.is_absolute():
            normalized["path"] = (Path(parent_path.strip()) / child_path).as_posix()

    parent_source = get_primary_source(parent)
    child_source = get_primary_source(normalized, create=parent_source is not None)
    if parent_source is not None and child_source is not None:
        for field_name in ("serviceType", "entityType"):
            inherited_value = parent_source.get(field_name)
            current_value = child_source.get(field_name)
            if isinstance(inherited_value, str) and inherited_value.strip() and not current_value:
                child_source[field_name] = inherited_value

    for field_name in ("driveService", "x-adapter"):
        inherited_value = parent.get(field_name)
        current_value = normalized.get(field_name)
        if isinstance(inherited_value, str) and inherited_value.strip() and not current_value:
            normalized[field_name] = inherited_value

    return normalized


def _resource_matches_include(
    resource: dict[str, Any],
    include_set: set[str],
    *,
    selector_path: str | None = None,
) -> bool:
    if "all" in include_set:
        return True

    resource_name = str(resource.get("name", "")).strip().lower()
    selector_key = (selector_path or resource_name).strip().lower()
    source_url = resource_source_url(resource)
    adapter_name = resource_adapter_name(resource, source_url)
    return (
        resource_name in include_set
        or selector_key in include_set
        or adapter_name in include_set
    )


def _resource_or_descendant_matches_include(
    resource: dict[str, Any],
    include_set: set[str],
    *,
    parent_selector_path: str | None = None,
) -> bool:
    selector_path = _resource_selector_path(resource, parent_selector_path)
    if _resource_matches_include(resource, include_set, selector_path=selector_path):
        return True

    for child in get_package_resources(resource):
        if not isinstance(child, dict):
            continue
        normalized_child = _inherit_resource_defaults(child, parent=resource)
        if _resource_or_descendant_matches_include(
            normalized_child,
            include_set,
            parent_selector_path=selector_path,
        ):
            return True

    return False


def _iter_drive_item_files(item: Any) -> Iterable[Any]:
    """Recursively yield non-directory children from a drive item tree.

    Works with any object exposing ``is_directory`` and ``children`` attributes,
    including concrete ``DriveFolder`` subclasses and lightweight test doubles
    that do not implement the ``iter_files`` method.
    """
    if getattr(item, "is_directory", False):
        for child in item.children:
            yield from _iter_drive_item_files(child)
    else:
        yield item


def _download_googledrive_directory(
    resource: dict[str, Any],
    *,
    output_roots: list[Path],
    source_url: str,
    client: Any,
    dry_run: bool,
    emit: LogFn,
) -> tuple[int, int]:
    resource_name = str(resource.get("name", "resource")).strip() or "resource"
    folder_item = client.get_from_weburl(source_url)

    downloaded = 0
    dry_run_actions = 0
    for child in _iter_drive_item_files(folder_item):
        relative_path = child.path or child.name or getattr(child, "id", None)
        if not relative_path:
            relative_path = getattr(child, "id", "file")

        destinations = [root / Path(relative_path) for root in output_roots]
        if dry_run:
            for destination in destinations:
                emit(
                    f"Would fetch {resource_name}/{relative_path} from {source_url} to {destination}"
                )
            dry_run_actions += len(destinations)
            continue

        primary_destination = destinations[0]
        primary_destination.parent.mkdir(parents=True, exist_ok=True)
        child.download(str(primary_destination))

        for destination in destinations[1:]:
            destination.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(primary_destination, destination)

        downloaded += len(destinations)

    return downloaded, dry_run_actions


def _download_sharepoint_directory(
    resource: dict[str, Any],
    *,
    output_roots: list[Path],
    source_url: str,
    client: Any,
    dry_run: bool,
    emit: LogFn,
) -> tuple[int, int]:
    resource_name = str(resource.get("name", "resource")).strip() or "resource"
    folder_item = client.get_from_weburl(source_url)

    downloaded = 0
    dry_run_actions = 0
    for child in _iter_drive_item_files(folder_item):
        relative_path = child.path or child.name or getattr(child, "id", None)
        if not relative_path:
            relative_path = getattr(child, "id", "file")

        destinations = [root / Path(relative_path) for root in output_roots]
        if dry_run:
            for destination in destinations:
                emit(
                    f"Would fetch {resource_name}/{relative_path} from {source_url} to {destination}"
                )
            dry_run_actions += len(destinations)
            continue

        primary_destination = destinations[0]
        primary_destination.parent.mkdir(parents=True, exist_ok=True)
        child.download(str(primary_destination))

        for destination in destinations[1:]:
            destination.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(primary_destination, destination)

        downloaded += len(destinations)

    return downloaded, dry_run_actions


def check_auth_for_adapters(
    adapters: Iterable[str],
    *,
    sharepoint_client_factory: Callable[[], Any] | None = None,
    googledrive_client_factory: Callable[[], Any] | None = None,
    s3_auth_checker: Callable[[], None] | None = None,
) -> list[AuthCheckResult]:
    results: list[AuthCheckResult] = []

    for adapter_name in adapters:
        try:
            if adapter_name == "sharepoint":
                factory = sharepoint_client_factory or _default_sharepoint_client_factory
                factory()
                results.append(
                    AuthCheckResult(
                        adapter="sharepoint",
                        ok=True,
                        message="SharePoint credentials are ready.",
                    )
                )
            elif adapter_name == "googledrive":
                factory = googledrive_client_factory or _default_googledrive_client_factory
                client = factory()
                ensure_valid = getattr(client, "_ensure_valid_credentials", None)
                if callable(ensure_valid):
                    ensure_valid()
                else:
                    _ = client._hdrs
                results.append(
                    AuthCheckResult(
                        adapter="googledrive",
                        ok=True,
                        message="Google Drive credentials are ready.",
                    )
                )
            elif adapter_name == "s3":
                checker = s3_auth_checker or check_s3_credentials
                checker()
                results.append(
                    AuthCheckResult(
                        adapter="s3",
                        ok=True,
                        message="AWS credentials are ready for S3 operations.",
                    )
                )
            else:
                results.append(
                    AuthCheckResult(
                        adapter=adapter_name,
                        ok=False,
                        message=f"Unsupported adapter '{adapter_name}'.",
                    )
                )
        except Exception as exc:
            prefix = {
                "sharepoint": "SharePoint authentication failed",
                "googledrive": "Google Drive authentication failed",
                "s3": "S3 credential check failed",
            }.get(adapter_name, f"Adapter '{adapter_name}' authentication failed")
            results.append(
                AuthCheckResult(
                    adapter=adapter_name,
                    ok=False,
                    message=f"{prefix}: {exc}",
                )
            )

    return results


def check_auth_for_descriptor(
    descriptor: Path | str,
    include: str | Iterable[str] = "all",
    *,
    sharepoint_client_factory: Callable[[], Any] | None = None,
    googledrive_client_factory: Callable[[], Any] | None = None,
    s3_auth_checker: Callable[[], None] | None = None,
) -> list[AuthCheckResult]:
    descriptor_path = ensure_descriptor_exists(descriptor)
    resources = load_descriptor(descriptor_path)
    adapters = _selected_adapter_names(resources, include)
    return check_auth_for_adapters(
        adapters,
        sharepoint_client_factory=sharepoint_client_factory,
        googledrive_client_factory=googledrive_client_factory,
        s3_auth_checker=s3_auth_checker,
    )


def download_from_descriptor(
    descriptor: Path | str,
    include: str | Iterable[str] = "all",
    output_dir: Path | str = Path("resources"),
    dry_run: bool = False,
    *,
    check_auth: bool = False,
    log: LogFn | None = print,
    sharepoint_client_factory: Callable[[], Any] | None = None,
    googledrive_client_factory: Callable[[], Any] | None = None,
    use_cloudpathlib: bool = True,
) -> DownloadSummary:
    """Download resources from a descriptor using adapter-specific clients."""
    descriptor_path = ensure_descriptor_exists(descriptor)
    include_set = _normalize_include(include)
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    resources = load_descriptor(descriptor_path)

    summary = DownloadSummary(total_resources=len(resources))
    clients: dict[str, Any] = {}

    def emit(message: str) -> None:
        if log is not None:
            log(message)

    if check_auth:
        auth_results = check_auth_for_adapters(
            _selected_adapter_names(resources, include_set),
            sharepoint_client_factory=sharepoint_client_factory,
            googledrive_client_factory=googledrive_client_factory,
        )
        failed_checks = [result for result in auth_results if not result.ok]
        if not auth_results:
            emit("Auth check skipped; no matching adapters were selected.")
        else:
            for result in auth_results:
                status = "ready" if result.ok else "failed"
                emit(f"Auth check {status} for {result.adapter}: {result.message}")
        if failed_checks:
            summary.failures += len(failed_checks)
            return summary

    def fetch_resource(
        resource: dict[str, Any],
        parent: dict[str, Any] | None = None,
        parent_selector_path: str | None = None,
        selected_by_ancestor: bool = False,
    ) -> None:
        normalized = _inherit_resource_defaults(resource, parent=parent)
        selector_path = _resource_selector_path(normalized, parent_selector_path)
        nested_resources = [
            child for child in get_package_resources(normalized) if isinstance(child, dict)
        ]

        if nested_resources:
            parent_selected = _resource_matches_include(
                normalized,
                include_set,
                selector_path=selector_path,
            )
            for child in nested_resources:
                child_resource = _inherit_resource_defaults(child, parent=normalized)
                if parent_selected or _resource_or_descendant_matches_include(
                    child_resource,
                    include_set,
                    parent_selector_path=selector_path,
                ):
                    fetch_resource(
                        child,
                        parent=normalized,
                        parent_selector_path=selector_path,
                        selected_by_ancestor=selected_by_ancestor or parent_selected,
                    )
            return

        resource_name = normalized.get("name", "resource")
        source_url = resource_source_url(normalized)
        adapter_name = resource_adapter_name(normalized, source_url)

        if not selected_by_ancestor and not _resource_matches_include(
            normalized,
            include_set,
            selector_path=selector_path,
        ):
            return
        if not source_url:
            emit(f"Warning, {resource_name} has no source URL")
            summary.failures += 1
            return

        try:
            output_paths = resource_output_paths(normalized, output_dir_path)
            output_path = output_paths[0]
            sync_target = resource_sync_target(normalized)
            entity_type = source_entity_type(normalized)

            if (
                adapter_name == "googledrive"
                and entity_type in {"Directory", "Container"}
                and not nested_resources
            ):
                if "googledrive" not in clients:
                    factory = googledrive_client_factory or _default_googledrive_client_factory
                    clients["googledrive"] = factory()
                output_roots = output_paths if sync_target == "resources" else [output_path]
                downloaded, dry_run_actions = _download_googledrive_directory(
                    normalized,
                    output_roots=output_roots,
                    source_url=source_url,
                    client=clients["googledrive"],
                    dry_run=dry_run,
                    emit=emit,
                )
                summary.downloaded += downloaded
                summary.dry_run_actions += dry_run_actions
                return

            if (
                adapter_name == "sharepoint"
                and entity_type in {"Directory", "Container"}
                and not nested_resources
            ):
                if "sharepoint" not in clients:
                    factory = sharepoint_client_factory or _default_sharepoint_client_factory
                    clients["sharepoint"] = factory()
                output_roots = output_paths if sync_target == "resources" else [output_path]
                downloaded, dry_run_actions = _download_sharepoint_directory(
                    normalized,
                    output_roots=output_roots,
                    source_url=source_url,
                    client=clients["sharepoint"],
                    dry_run=dry_run,
                    emit=emit,
                )
                summary.downloaded += downloaded
                summary.dry_run_actions += dry_run_actions
                return

            if dry_run:
                for destination in output_paths:
                    emit(f"Would fetch {source_url} to {destination}")
                summary.dry_run_actions += len(output_paths)
                return
            output_path.parent.mkdir(parents=True, exist_ok=True)

            if adapter_name == "sharepoint":
                if "sharepoint" not in clients:
                    factory = sharepoint_client_factory or _default_sharepoint_client_factory
                    clients["sharepoint"] = factory()
                item = clients["sharepoint"].get_from_weburl(source_url)
                item.download(str(output_path))
            elif adapter_name == "s3":
                result = download_s3_url(
                    source_url,
                    output_path,
                    dry_run=False,
                    use_cloudpathlib=use_cloudpathlib,
                )
                if result is None:
                    raise RuntimeError("S3 download returned no output path")
            elif adapter_name == "googledrive":
                if "googledrive" not in clients:
                    factory = googledrive_client_factory or _default_googledrive_client_factory
                    clients["googledrive"] = factory()
                item = clients["googledrive"].get_from_weburl(source_url)
                item.download(str(output_path))
            else:
                emit(
                    f"Warning, {resource_name} has unsupported adapter '{adapter_name}'"
                )
                summary.failures += 1
                return

            for destination in output_paths[1:]:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(output_path, destination)

            summary.downloaded += len(output_paths)
        except Exception as exc:
            emit(f"Warning, {resource_name} failed: {exc}")
            summary.failures += 1

    for index, resource in enumerate(resources):
        if not isinstance(resource, dict):
            emit(f"Warning, resource[{index}] is not an object")
            summary.failures += 1
            continue

        normalized = dict(resource)
        normalized.setdefault("name", f"resource[{index}]")
        if not _resource_or_descendant_matches_include(normalized, include_set):
            resource_name = normalized.get("name", f"resource[{index}]")
            source_url = resource_source_url(normalized)
            adapter_name = resource_adapter_name(normalized, source_url)
            emit(f"Skipping {resource_name}; adapter '{adapter_name}' not selected.")
            summary.skipped += 1
            continue

        fetch_resource(normalized)

    return summary


def download_resources(
    descriptor: Path | str,
    include: str | Iterable[str] = "all",
    output_dir: Path | str = Path("resources"),
    dry_run: bool = False,
    *,
    check_auth: bool = False,
    log: LogFn | None = print,
) -> DownloadSummary:
    """Convenience alias for download_from_descriptor."""
    return download_from_descriptor(
        descriptor=descriptor,
        include=include,
        output_dir=output_dir,
        dry_run=dry_run,
        check_auth=check_auth,
        log=log,
    )
__all__ = [
    "AuthCheckResult",
    "check_auth_for_adapters",
    "check_auth_for_descriptor",
    "DownloadSummary",
    "download_from_descriptor",
    "download_resources",
    "load_descriptor",
    "resolve_default_descriptor",
    "resource_adapter_name",
    "resource_output_path",
    "resource_output_paths",
    "resource_source_url",
]