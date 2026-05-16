from __future__ import annotations

from pathlib import Path
from typing import Iterable

from sharedrive.actions.catalog import (
    AuthCheckResult,
    DownloadSummary,
    FetchSummary,
    SharedriveCatalogAction,
)


def fetch_descriptor_metadata(
    descriptor: Path | str,
    selector: str | None = None,
    *,
    dry_run: bool = False,
    depth: int = -1,
    log=print,
) -> list[FetchSummary]:
    action = SharedriveCatalogAction.from_path(descriptor)
    summaries = action.fetch(selector, dry_run=dry_run, depth=depth, log=log)
    if not dry_run and any(summary.changed for summary in summaries):
        action.catalog.to_path(str(Path(descriptor)))
    return summaries


def download_descriptor_resources(
    descriptor: Path | str,
    selector: str | Iterable[str] | None = None,
    *,
    output_dir: Path | str = Path("resources"),
    dry_run: bool = False,
    check_auth: bool = False,
    log=print,
    use_cloudpathlib: bool = True,
) -> DownloadSummary:
    return SharedriveCatalogAction.from_path(descriptor).download(
        selector,
        output_dir=output_dir,
        dry_run=dry_run,
        check_auth=check_auth,
        log=log,
        use_cloudpathlib=use_cloudpathlib,
    )


def check_descriptor_auth(
    descriptor: Path | str | None = None,
    selector: str | Iterable[str] | None = None,
    *,
    adapters: Iterable[str] | None = None,
) -> list[AuthCheckResult]:
    if descriptor is None:
        if adapters is None:
            raise ValueError("descriptor is required when adapters are not provided.")
        from sharedrive.models import DriveCatalog

        return SharedriveCatalogAction(DriveCatalog.empty()).check_auth(adapters=adapters)
    return SharedriveCatalogAction.from_path(descriptor).check_auth(
        selector, adapters=adapters
    )


__all__ = [
    "AuthCheckResult",
    "DownloadSummary",
    "FetchSummary",
    "SharedriveCatalogAction",
    "check_descriptor_auth",
    "download_descriptor_resources",
    "fetch_descriptor_metadata",
]
