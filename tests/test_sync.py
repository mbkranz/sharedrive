from __future__ import annotations

from pathlib import Path

import pytest

from sharedrive.actions.fetch import fetch


def test_fetch_requires_existing_descriptor(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="does not exist"):
        fetch(tmp_path / "missing.yaml", "catalog", log=None)
