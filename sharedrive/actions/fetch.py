from __future__ import annotations

from pathlib import Path
from typing import Callable

from sharedrive.actions.workflow import FetchSummary, fetch_descriptor_metadata

LogFn = Callable[[str], None]


def fetch(
    descriptor: Path | str,
    selector: str | None = None,
    *,
    dry_run: bool = False,
    depth: int = -1,
    log: LogFn | None = print,
) -> list[FetchSummary]:
    """Fetch remote folder metadata from catalog accessURL values."""
    return fetch_descriptor_metadata(
        Path(descriptor),
        selector=selector,
        dry_run=dry_run,
        depth=depth,
        log=log,
    )


__all__ = ["FetchSummary", "fetch"]
