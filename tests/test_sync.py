from __future__ import annotations

from pathlib import Path

import pytest

from sharedrive.catalog import SharedriveCatalog


def test_fetch_requires_existing_descriptor(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="does not exist"):
        SharedriveCatalog.from_path(tmp_path / "missing.yaml").fetch(
            "catalog", log=None
        )
