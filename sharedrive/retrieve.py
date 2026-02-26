from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

import yaml

from sharedrive.aws import download_s3_url

LogFn = Callable[[str], None]


@dataclass(slots=True)
class RetrieveSummary:
    total_resources: int = 0
    downloaded: int = 0
    skipped: int = 0
    dry_run_actions: int = 0
    failures: int = 0

    @property
    def ok(self) -> bool:
        return self.failures == 0


def load_descriptor(path: Path) -> list[dict[str, Any]]:
    """Load a JSON/YAML descriptor and return the top-level resources list."""
    descriptor_text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()

    if suffix == ".json":
        data = json.loads(descriptor_text)
    elif suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(descriptor_text)
    else:
        try:
            data = json.loads(descriptor_text)
        except json.JSONDecodeError:
            data = yaml.safe_load(descriptor_text)

    if not isinstance(data, dict):
        raise ValueError("Descriptor must be a top-level JSON/YAML object")

    resources = data.get("resources")
    if not isinstance(resources, list):
        raise ValueError("Descriptor must contain a top-level 'resources' array")
    return resources


def resolve_default_descriptor() -> Path:
    """Return the first existing default descriptor path."""
    for candidate in (
        Path("resources/descriptor.yaml"),
        Path("resources/descriptor.yml"),
        Path("resources/descriptor.json"),
    ):
        if candidate.exists():
            return candidate
    return Path("resources/descriptor.yaml")


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


def resource_adapter_name(resource: dict[str, Any], source_url: str | None) -> str:
    """Resolve adapter from x-adapter override or infer from URL."""
    adapter = resource.get("x-adapter")
    if isinstance(adapter, str) and adapter.strip():
        return adapter.strip().lower()

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
    normalized = {item.strip().lower() for item in include_items if item and item.strip()}
    return normalized or {"all"}


def _default_sharepoint_client_factory() -> Any:
    from sharedrive.azure import SpoConfig

    return SpoConfig().to_client()


def _default_googledrive_client_factory() -> Any:
    from sharedrive.googledrive import GoogleDriveClient

    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    return GoogleDriveClient(credentials_path=credentials_path)


def retrieve_from_descriptor(
    descriptor: Path | str,
    include: str | Iterable[str] = "all",
    output_dir: Path | str = Path("resources"),
    dry_run: bool = False,
    *,
    log: LogFn | None = print,
    sharepoint_client_factory: Callable[[], Any] | None = None,
    googledrive_client_factory: Callable[[], Any] | None = None,
    use_cloudpathlib: bool = True,
) -> RetrieveSummary:
    """Retrieve resources from a descriptor using adapter-specific clients."""
    descriptor_path = Path(descriptor)
    include_set = _normalize_include(include)
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    resources = load_descriptor(descriptor_path)

    summary = RetrieveSummary(total_resources=len(resources))
    clients: dict[str, Any] = {}

    def emit(message: str) -> None:
        if log is not None:
            log(message)

    for index, resource in enumerate(resources):
        if not isinstance(resource, dict):
            emit(f"Warning, resource[{index}] is not an object")
            summary.failures += 1
            continue

        resource_name = resource.get("name", f"resource[{index}]")
        source_url = resource_source_url(resource)
        adapter_name = resource_adapter_name(resource, source_url)

        if "all" not in include_set and adapter_name not in include_set:
            emit(
                f"Skipping {resource_name}; adapter '{adapter_name}' not selected."
            )
            summary.skipped += 1
            continue
        if not source_url:
            emit(f"Warning, {resource_name} has no source URL")
            summary.failures += 1
            continue

        try:
            output_path = resource_output_path(resource, output_dir_path)
            if adapter_name == "sharepoint":
                if "sharepoint" not in clients:
                    factory = (
                        sharepoint_client_factory
                        or _default_sharepoint_client_factory
                    )
                    clients["sharepoint"] = factory()
                clients["sharepoint"].download_from_weburl(
                    url=source_url,
                    output_path=output_path,
                    dry_run=dry_run,
                )
                if dry_run:
                    summary.dry_run_actions += 1
                else:
                    summary.downloaded += 1
            elif adapter_name == "s3":
                result = download_s3_url(
                    source_url,
                    output_path,
                    dry_run=dry_run,
                    use_cloudpathlib=use_cloudpathlib,
                )
                if result is None:
                    summary.dry_run_actions += 1
                else:
                    summary.downloaded += 1
            elif adapter_name == "googledrive":
                if dry_run:
                    emit(
                        f"Would download Google Drive resource {source_url} to {output_path}"
                    )
                    summary.dry_run_actions += 1
                else:
                    if "googledrive" not in clients:
                        factory = (
                            googledrive_client_factory
                            or _default_googledrive_client_factory
                        )
                        clients["googledrive"] = factory()
                    clients["googledrive"].download_from_weburl(
                        source_url,
                        output_path=str(output_path),
                    )
                    emit(f"Downloaded Google Drive resource to {output_path}")
                    summary.downloaded += 1
            else:
                emit(
                    f"Warning, {resource_name} has unsupported adapter '{adapter_name}'"
                )
                summary.failures += 1
        except Exception as exc:
            emit(f"Warning, {resource_name} failed: {exc}")
            summary.failures += 1

    return summary


def retrieve_resources(
    descriptor: Path | str,
    include: str | Iterable[str] = "all",
    output_dir: Path | str = Path("resources"),
    dry_run: bool = False,
    *,
    log: LogFn | None = print,
) -> RetrieveSummary:
    """Convenience alias for retrieve_from_descriptor."""
    return retrieve_from_descriptor(
        descriptor=descriptor,
        include=include,
        output_dir=output_dir,
        dry_run=dry_run,
        log=log,
    )


__all__ = [
    "RetrieveSummary",
    "load_descriptor",
    "resolve_default_descriptor",
    "resource_source_url",
    "resource_output_path",
    "resource_adapter_name",
    "retrieve_from_descriptor",
    "retrieve_resources",
]
