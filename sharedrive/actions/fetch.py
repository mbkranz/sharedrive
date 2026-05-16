from __future__ import annotations

from pathlib import Path
from typing import Callable

from sharedrive.actions.catalog import FetchSummary, SharedriveCatalogAction

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
    descriptor_path = Path(descriptor)
    action = SharedriveCatalogAction.from_path(descriptor_path)
    summaries = action.fetch(selector, dry_run=dry_run, depth=depth, log=log)
    if not dry_run and any(summary.changed for summary in summaries):
        action.catalog.to_path(str(descriptor_path))
    return summaries


__all__ = ["FetchSummary", "fetch"]
