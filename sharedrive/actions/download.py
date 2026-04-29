from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from sharedrive.models import (
    Entry,
    DriveSourceReference,
    contained_entries,
    entry_to_dict,
    inherited_entry,
    iter_source_refs,
    load_drive_descriptor,
    normalize_selector,
    remote_basename,
    resource_matches_selector,
    resource_or_descendant_matches_selector,
    resource_selector_path,
    selected_adapter_names,
    sync_target,
)
from sharedrive.clients.aws import check_s3_credentials, download_s3_url
from sharedrive.registry import get_client, get_provider

LogFn = Callable[[str], None]


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


def _resolve_local_path(path_value: str, output_dir: Path) -> Path:
    path = Path(path_value.strip())
    if path.is_absolute():
        return path
    return output_dir / path


def _resource_output_path(resource: Entry, output_dir: Path) -> Path:
    resource_dict = entry_to_dict(resource)
    path_value = resource_dict.get("path")
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValueError("Resource is missing required string field 'path'")
    return _resolve_local_path(path_value, output_dir)


def _resource_output_paths(resource: Entry, output_dir: Path) -> list[Path]:
    paths: list[Path] = [_resource_output_path(resource, output_dir)]
    resource_dict = entry_to_dict(resource)
    targets = resource_dict.get("targets")
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
        resolved = _resolve_local_path(target_value, output_dir)
        deduped.setdefault(str(resolved), resolved)
    return list(deduped.values())


def _source_output_path(
    resource: Entry,
    source: DriveSourceReference,
    output_dir: Path,
    *,
    source_count: int,
    directory: bool,
) -> Path:
    if source_count == 1:
        return _resource_output_path(resource, output_dir)

    if source.target is not None:
        return _resolve_local_path(source.target, output_dir)

    root = _resource_output_path(resource, output_dir) / source.key
    if directory:
        return root

    basename = remote_basename(source.path) or source.key
    return root / basename


def _single_source_output_paths(resource: Entry, output_dir: Path) -> list[Path]:
    return _resource_output_paths(resource, output_dir)


def _reserve_destination(
    destination: Path, *, seen: dict[str, str], label: str
) -> None:
    key = str(destination.resolve() if destination.exists() else destination.absolute())
    previous = seen.get(key)
    if previous is not None and previous != label:
        raise ValueError(
            f"Output collision for {destination}: both {previous} and {label} map there."
        )
    seen[key] = label


def _get_client(adapter_name: str, *, clients: dict[str, Any]) -> Any:
    if adapter_name not in clients:
        clients[adapter_name] = get_client(adapter_name)
    return clients[adapter_name]


def _iter_drive_item_files(item: Any) -> Iterable[Any]:
    if getattr(item, "is_directory", False):
        for child in item.children:
            yield from _iter_drive_item_files(child)
    else:
        yield item


def _download_drive_item(
    *, client: Any, source: DriveSourceReference, output_path: Path
) -> None:
    item = client.get_from_weburl(source.path)
    item.download(str(output_path))


def _download_drive_directory(
    *,
    resource_name: str,
    source: DriveSourceReference,
    output_roots: list[Path],
    client: Any,
    dry_run: bool,
    emit: LogFn,
    seen_destinations: dict[str, str],
) -> tuple[int, int]:
    folder_item = client.get_from_weburl(source.path)

    downloaded = 0
    dry_run_actions = 0
    for child in _iter_drive_item_files(folder_item):
        relative_path = child.path or child.name or getattr(child, "id", None)
        if not relative_path:
            relative_path = getattr(child, "id", "file")

        destinations = [root / Path(relative_path) for root in output_roots]
        for destination in destinations:
            _reserve_destination(
                destination,
                seen=seen_destinations,
                label=f"{resource_name}:{source.index}:{relative_path}",
            )

        if dry_run:
            for destination in destinations:
                emit(
                    f"Would fetch {resource_name}/{relative_path} from {source.path} to {destination}"
                )
            dry_run_actions += len(destinations)
            continue

        primary_destination = destinations[0]
        primary_destination.parent.mkdir(parents=True, exist_ok=True)
        child.download(str(primary_destination))

        for destination in destinations[1:]:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(primary_destination, destination)

        downloaded += len(destinations)

    return downloaded, dry_run_actions


def _check_auth_for_adapters(adapters: Iterable[str]) -> list[AuthCheckResult]:
    ok_messages = {
        "sharepoint": "SharePoint credentials are ready.",
        "googledrive": "Google Drive credentials are ready.",
        "s3": "AWS credentials are ready for S3 operations.",
    }
    fail_prefixes = {
        "sharepoint": "SharePoint authentication failed",
        "googledrive": "Google Drive authentication failed",
        "s3": "S3 credential check failed",
    }

    results: list[AuthCheckResult] = []
    for adapter_name in adapters:
        if adapter_name == "s3":
            try:
                check_s3_credentials()
                results.append(AuthCheckResult("s3", True, ok_messages["s3"]))
            except Exception as exc:
                results.append(
                    AuthCheckResult("s3", False, f"{fail_prefixes['s3']}: {exc}")
                )
            continue

        cls = get_provider(adapter_name)
        if cls is None:
            results.append(
                AuthCheckResult(
                    adapter_name, False, f"Unsupported adapter '{adapter_name}'."
                )
            )
            continue

        try:
            cls.check_auth()
            results.append(
                AuthCheckResult(
                    adapter_name,
                    True,
                    ok_messages.get(
                        adapter_name, f"Adapter '{adapter_name}' is ready."
                    ),
                )
            )
        except Exception as exc:
            prefix = fail_prefixes.get(
                adapter_name, f"Adapter '{adapter_name}' authentication failed"
            )
            results.append(AuthCheckResult(adapter_name, False, f"{prefix}: {exc}"))

    return results


def check_auth(
    descriptor: Path | str | None = None,
    selector: str | Iterable[str] | None = None,
    *,
    adapters: Iterable[str] | None = None,
) -> list[AuthCheckResult]:
    """Validate credentials for selected descriptor sources or explicit adapters."""
    if adapters is not None:
        deduped = list(dict.fromkeys(adapter.strip().lower() for adapter in adapters))
        return _check_auth_for_adapters(deduped)

    if descriptor is None:
        raise ValueError("descriptor is required when adapters are not provided.")

    entries = contained_entries(load_drive_descriptor(Path(descriptor)))
    return _check_auth_for_adapters(selected_adapter_names(entries, selector))


def download(
    descriptor: Path | str,
    selector: str | Iterable[str] | None = None,
    *,
    output_dir: Path | str = Path("resources"),
    dry_run: bool = False,
    check_auth: bool = False,
    log: LogFn | None = print,
    use_cloudpathlib: bool = True,
) -> DownloadSummary:
    """Download all sources selected from a descriptor."""
    descriptor_path = Path(descriptor)
    selector_set = normalize_selector(selector)
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    resources = contained_entries(load_drive_descriptor(descriptor_path))

    summary = DownloadSummary(total_resources=len(resources))
    clients: dict[str, Any] = {}
    seen_destinations: dict[str, str] = {}

    def emit(message: str) -> None:
        if log is not None:
            log(message)

    if check_auth:
        auth_results = _check_auth_for_adapters(
            selected_adapter_names(resources, selector_set)
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
        resource: Entry,
        parent: Entry | None = None,
        parent_selector_path: str | None = None,
        selected_by_ancestor: bool = False,
    ) -> None:
        normalized = inherited_entry(resource, parent=parent)
        selector_path = resource_selector_path(normalized, parent_selector_path)
        nested_entries = contained_entries(resource)

        if nested_entries:
            parent_selected = resource_matches_selector(
                normalized, selector_set, selector_path=selector_path
            )
            for child in nested_entries:
                child_resource = inherited_entry(child, parent=normalized)
                if (
                    selected_by_ancestor
                    or parent_selected
                    or resource_or_descendant_matches_selector(
                        child_resource, selector_set, parent_selector_path=selector_path
                    )
                ):
                    fetch_resource(
                        child,
                        parent=normalized,
                        parent_selector_path=selector_path,
                        selected_by_ancestor=selected_by_ancestor or parent_selected,
                    )
            return

        resource_name = str(normalized.get("name", "resource"))
        if not selected_by_ancestor and not resource_matches_selector(
            normalized, selector_set, selector_path=selector_path
        ):
            return

        sources = iter_source_refs(normalized, parent=parent)
        if not sources:
            emit(f"Warning, {resource_name} has no source URL")
            summary.failures += 1
            return

        for source in sources:
            try:
                _download_one_source(
                    normalized,
                    resource_name=resource_name,
                    source=source,
                    source_count=len(sources),
                    output_dir=output_dir_path,
                    clients=clients,
                    dry_run=dry_run,
                    emit=emit,
                    seen_destinations=seen_destinations,
                    summary=summary,
                    use_cloudpathlib=use_cloudpathlib,
                )
            except Exception as exc:
                if isinstance(exc, ValueError) and "Output collision" in str(exc):
                    raise
                emit(f"Warning, {resource_name} source {source.index} failed: {exc}")
                summary.failures += 1

    for index, resource in enumerate(resources):
        normalized = entry_to_dict(resource)
        normalized.setdefault("name", f"resource[{index}]")
        if not resource_or_descendant_matches_selector(normalized, selector_set):
            resource_name = normalized.get("name", f"resource[{index}]")
            emit(f"Skipping {resource_name}; selector did not match.")
            summary.skipped += 1
            continue

        fetch_resource(resource)

    return summary


def _download_one_source(
    resource: Entry,
    *,
    resource_name: str,
    source: DriveSourceReference,
    source_count: int,
    output_dir: Path,
    clients: dict[str, Any],
    dry_run: bool,
    emit: LogFn,
    seen_destinations: dict[str, str],
    summary: DownloadSummary,
    use_cloudpathlib: bool,
) -> None:
    directory = source.entity_type in {"Directory", "Container"}
    sync = sync_target(resource)
    cls = get_provider(source.adapter)

    if cls is not None:
        if directory:
            client = _get_client(source.adapter, clients=clients)
            if source_count == 1:
                output_roots = (
                    _single_source_output_paths(resource, output_dir)
                    if sync == "resources"
                    else [_resource_output_path(resource, output_dir)]
                )
            else:
                output_roots = [
                    _source_output_path(
                        resource,
                        source,
                        output_dir,
                        source_count=source_count,
                        directory=True,
                    )
                ]
            downloaded, dry_run_actions = _download_drive_directory(
                resource_name=resource_name,
                source=source,
                output_roots=output_roots,
                client=client,
                dry_run=dry_run,
                emit=emit,
                seen_destinations=seen_destinations,
            )
            summary.downloaded += downloaded
            summary.dry_run_actions += dry_run_actions
            return

        destinations = (
            _single_source_output_paths(resource, output_dir)
            if source_count == 1
            else [
                _source_output_path(
                    resource,
                    source,
                    output_dir,
                    source_count=source_count,
                    directory=False,
                )
            ]
        )
        _download_file_source(
            destinations=destinations,
            download_fn=lambda destination: _download_drive_item(
                client=_get_client(source.adapter, clients=clients),
                source=source,
                output_path=destination,
            ),
            source=source,
            dry_run=dry_run,
            emit=emit,
            seen_destinations=seen_destinations,
            summary=summary,
        )
        return

    if source.adapter == "s3":
        destinations = (
            _single_source_output_paths(resource, output_dir)
            if source_count == 1
            else [
                _source_output_path(
                    resource,
                    source,
                    output_dir,
                    source_count=source_count,
                    directory=False,
                )
            ]
        )
        _download_file_source(
            destinations=destinations,
            download_fn=lambda destination: _download_s3_source(
                source, destination, use_cloudpathlib=use_cloudpathlib
            ),
            source=source,
            dry_run=dry_run,
            emit=emit,
            seen_destinations=seen_destinations,
            summary=summary,
        )
        return

    raise ValueError(f"Unsupported adapter '{source.adapter}'")


def _download_file_source(
    *,
    destinations: list[Path],
    download_fn: Callable[[Path], None],
    source: DriveSourceReference,
    dry_run: bool,
    emit: LogFn,
    seen_destinations: dict[str, str],
    summary: DownloadSummary,
) -> None:
    for destination in destinations:
        _reserve_destination(
            destination,
            seen=seen_destinations,
            label=f"{source.adapter}:{source.index}:{source.path}",
        )

    if dry_run:
        for destination in destinations:
            emit(f"Would fetch {source.path} to {destination}")
        summary.dry_run_actions += len(destinations)
        return

    primary_destination = destinations[0]
    primary_destination.parent.mkdir(parents=True, exist_ok=True)
    download_fn(primary_destination)

    for destination in destinations[1:]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(primary_destination, destination)

    summary.downloaded += len(destinations)


def _download_s3_source(
    source: DriveSourceReference, output_path: Path, *, use_cloudpathlib: bool
) -> None:
    result = download_s3_url(
        source.path, output_path, dry_run=False, use_cloudpathlib=use_cloudpathlib
    )
    if result is None:
        raise RuntimeError("S3 download returned no output path")


__all__ = ["AuthCheckResult", "DownloadSummary", "check_auth", "download"]
