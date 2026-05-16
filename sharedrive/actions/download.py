from __future__ import annotations

from pathlib import Path
from typing import Iterable

from sharedrive.actions.workflow import (
    AuthCheckResult,
    DownloadSummary,
    check_descriptor_auth,
    download_descriptor_resources,
)


def check_auth(
    descriptor: Path | str | None = None,
    selector: str | Iterable[str] | None = None,
    *,
    adapters: Iterable[str] | None = None,
) -> list[AuthCheckResult]:
    """Validate credentials for selected descriptor entities or explicit adapters."""
    return check_descriptor_auth(descriptor, selector, adapters=adapters)


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
    return download_descriptor_resources(
        descriptor,
        selector=selector,
        output_dir=output_dir,
        dry_run=dry_run,
        check_auth=check_auth,
        log=log,
        use_cloudpathlib=use_cloudpathlib,
    )


__all__ = ["AuthCheckResult", "DownloadSummary", "check_auth", "download"]
