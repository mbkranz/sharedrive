from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

from sharedrive.clients.aws import check_s3_credentials, download_s3_url
from sharedrive.descriptor import (
    get_package_resources,
    is_package_resource,
    load_descriptor,
    resolve_default_descriptor,
)

LogFn = Callable[[str], None]


@dataclass(slots=True)
class FetchSummary:
    total_resources: int = 0
    downloaded: int = 0
    skipped: int = 0
    dry_run_actions: int = 0
    failures: int = 0

    @property
    def ok(self) -> bool:
        return self.failures == 0


RetrieveSummary = FetchSummary


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


def resource_source_url(resource: dict[str, Any]) -> str | None:
    """Resolve source URL using sources[].path first, then legacy source."""
    sources = resource.get("sources")
    if isinstance(sources, list):
        for source_obj in sources:
            if isinstance(source_obj, dict):
                source_path = source_obj.get("path")
                if isinstance(source_path, str) and source_path.strip():
                    return source_path.strip()

    legacy_source = resource.get("source")
    if isinstance(legacy_source, str) and legacy_source.strip():
        return legacy_source.strip()
    return None


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


def resource_adapter_name(resource: dict[str, Any], source_url: str | None) -> str:
    """Resolve adapter from driveService/x-adapter override or infer from URL."""
    adapter = resource.get("driveService")
    if isinstance(adapter, str) and adapter.strip():
        return adapter.strip().lower()

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


def _selected_adapter_names(
    resources: Iterable[dict[str, Any]],
    include: str | Iterable[str] = "all",
) -> list[str]:
    include_set = _normalize_include(include)
    selected: list[str] = []
    seen: set[str] = set()

    def collect(resource: dict[str, Any], parent: dict[str, Any] | None = None) -> None:
        normalized = _inherit_resource_defaults(resource, parent=parent)
        children = get_package_resources(normalized)

        if children:
            for child in children:
                if isinstance(child, dict):
                    collect(child, parent=normalized)
            return

        resource_name = normalized.get("name", "resource")
        resource_name_key = str(resource_name).strip().lower()
        source_url = resource_source_url(normalized)
        adapter_name = resource_adapter_name(normalized, source_url)

        if (
            "all" not in include_set
            and adapter_name not in include_set
            and resource_name_key not in include_set
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

    for field_name in ("driveService", "x-adapter"):
        inherited_value = parent.get(field_name)
        current_value = normalized.get(field_name)
        if isinstance(inherited_value, str) and inherited_value.strip() and not current_value:
            normalized[field_name] = inherited_value

    return normalized


def _resource_matches_include(
    resource: dict[str, Any],
    include_set: set[str],
) -> bool:
    if "all" in include_set:
        return True

    resource_name = str(resource.get("name", "")).strip().lower()
    source_url = resource_source_url(resource)
    adapter_name = resource_adapter_name(resource, source_url)
    return resource_name in include_set or adapter_name in include_set


def _resource_or_descendant_matches_include(
    resource: dict[str, Any],
    include_set: set[str],
) -> bool:
    if _resource_matches_include(resource, include_set):
        return True

    for child in get_package_resources(resource):
        if not isinstance(child, dict):
            continue
        normalized_child = _inherit_resource_defaults(child, parent=resource)
        if _resource_or_descendant_matches_include(normalized_child, include_set):
            return True

    return False


def _download_googledrive_package(
    resource: dict[str, Any],
    *,
    output_roots: list[Path],
    source_url: str,
    client: Any,
    dry_run: bool,
    emit: LogFn,
) -> tuple[int, int]:
    package_name = str(resource.get("name", "package")).strip() or "package"
    discovered_files = client.list_folder_files_from_weburl(source_url, recursive=True)

    downloaded = 0
    dry_run_actions = 0
    for entry in discovered_files:
        relative_path = str(entry.get("relative_path", entry.get("name", entry.get("id", "")))).strip()
        if not relative_path:
            relative_path = str(entry.get("id", "item"))

        destinations = [root / Path(relative_path) for root in output_roots]
        if dry_run:
            for destination in destinations:
                emit(
                    f"Would fetch {package_name}/{relative_path} from {source_url} to {destination}"
                )
            dry_run_actions += len(destinations)
            continue

        primary_destination = destinations[0]
        primary_destination.parent.mkdir(parents=True, exist_ok=True)
        client.download_file(str(entry["id"]), output_path=str(primary_destination))

        for destination in destinations[1:]:
            destination.parent.mkdir(parents=True, exist_ok=True)
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
    resources = load_descriptor(Path(descriptor))
    adapters = _selected_adapter_names(resources, include)
    return check_auth_for_adapters(
        adapters,
        sharepoint_client_factory=sharepoint_client_factory,
        googledrive_client_factory=googledrive_client_factory,
        s3_auth_checker=s3_auth_checker,
    )


def fetch_from_descriptor(
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
) -> FetchSummary:
    """Fetch resources from a descriptor using adapter-specific clients."""
    descriptor_path = Path(descriptor)
    include_set = _normalize_include(include)
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    resources = load_descriptor(descriptor_path)

    summary = FetchSummary(total_resources=len(resources))
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

    def fetch_resource(resource: dict[str, Any], parent: dict[str, Any] | None = None) -> None:
        normalized = _inherit_resource_defaults(resource, parent=parent)
        nested_resources = [
            child for child in get_package_resources(normalized) if isinstance(child, dict)
        ]

        if nested_resources:
            for child in nested_resources:
                child_resource = _inherit_resource_defaults(child, parent=normalized)
                if _resource_or_descendant_matches_include(child_resource, include_set):
                    fetch_resource(child, parent=normalized)
            return

        resource_name = normalized.get("name", "resource")
        source_url = resource_source_url(normalized)
        adapter_name = resource_adapter_name(normalized, source_url)

        if not _resource_matches_include(normalized, include_set):
            return
        if not source_url:
            emit(f"Warning, {resource_name} has no source URL")
            summary.failures += 1
            return

        try:
            output_paths = resource_output_paths(normalized, output_dir_path)
            output_path = output_paths[0]

            if is_package_resource(normalized) and adapter_name == "googledrive":
                if "googledrive" not in clients:
                    factory = googledrive_client_factory or _default_googledrive_client_factory
                    clients["googledrive"] = factory()
                downloaded, dry_run_actions = _download_googledrive_package(
                    normalized,
                    output_roots=output_paths,
                    source_url=source_url,
                    client=clients["googledrive"],
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
                clients["sharepoint"].download_from_weburl(
                    url=source_url,
                    output_path=output_path,
                    dry_run=False,
                )
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
                clients["googledrive"].download_from_weburl(
                    source_url,
                    output_path=str(output_path),
                )
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


def fetch_resources(
    descriptor: Path | str,
    include: str | Iterable[str] = "all",
    output_dir: Path | str = Path("resources"),
    dry_run: bool = False,
    *,
    check_auth: bool = False,
    log: LogFn | None = print,
) -> FetchSummary:
    """Convenience alias for fetch_from_descriptor."""
    return fetch_from_descriptor(
        descriptor=descriptor,
        include=include,
        output_dir=output_dir,
        dry_run=dry_run,
        check_auth=check_auth,
        log=log,
    )


def retrieve_from_descriptor(
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
) -> RetrieveSummary:
    """Backward-compatible alias for fetch_from_descriptor."""
    return fetch_from_descriptor(
        descriptor=descriptor,
        include=include,
        output_dir=output_dir,
        dry_run=dry_run,
        check_auth=check_auth,
        log=log,
        sharepoint_client_factory=sharepoint_client_factory,
        googledrive_client_factory=googledrive_client_factory,
        use_cloudpathlib=use_cloudpathlib,
    )


def retrieve_resources(
    descriptor: Path | str,
    include: str | Iterable[str] = "all",
    output_dir: Path | str = Path("resources"),
    dry_run: bool = False,
    *,
    check_auth: bool = False,
    log: LogFn | None = print,
) -> RetrieveSummary:
    """Backward-compatible alias for fetch_resources."""
    return fetch_resources(
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
    "FetchSummary",
    "RetrieveSummary",
    "fetch_from_descriptor",
    "fetch_resources",
    "load_descriptor",
    "resolve_default_descriptor",
    "resource_adapter_name",
    "resource_output_path",
    "resource_output_paths",
    "resource_source_url",
    "retrieve_from_descriptor",
    "retrieve_resources",
]