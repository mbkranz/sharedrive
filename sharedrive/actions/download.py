from __future__ import annotations

from pathlib import Path
from typing import Iterable

from sharedrive.actions.catalog import (
    AuthCheckResult,
    DownloadSummary,
    SharedriveCatalogAction,
)


def check_auth(
    descriptor: Path | str | None = None,
    selector: str | Iterable[str] | None = None,
    *,
    adapters: Iterable[str] | None = None,
) -> list[AuthCheckResult]:
    """Validate credentials for selected descriptor entities or explicit adapters."""
    if descriptor is None:
        if adapters is None:
            raise ValueError("descriptor is required when adapters are not provided.")
        from sharedrive.models import DriveCatalog

        return SharedriveCatalogAction(DriveCatalog.empty()).check_auth(adapters=adapters)
    return SharedriveCatalogAction.from_path(descriptor).check_auth(
        selector, adapters=adapters
    )


def download(
    descriptor: Path | str,
    selector: str | Iterable[str] | None = None,
    *,
    output_dir: Path | str = Path("resources"),
    dry_run: bool = False,
    check_auth: bool = False,
    log=None,
    use_cloudpathlib: bool = True,
) -> DownloadSummary:
    """Download selected resources from `path` to `_cache`."""
    return SharedriveCatalogAction.from_path(descriptor).download(
        selector,
        output_dir=output_dir,
        dry_run=dry_run,
        check_auth=check_auth,
        log=log,
        use_cloudpathlib=use_cloudpathlib,
    )


__all__ = ["AuthCheckResult", "DownloadSummary", "check_auth", "download"]
