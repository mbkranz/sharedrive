from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sharedrive.actions.sync import sync_package_resource_in_descriptor


def _write_package_descriptor(path: Path) -> None:
    path.write_text(
        """
resources:
  - name: census-package
    profile: data-package
    path: downloads/census
    driveService: googledrive
    sources:
      - path: https://drive.google.com/drive/folders/folder123
""".strip(),
        encoding="utf-8",
    )


def test_sync_package_resource_in_descriptor_writes_nested_resources(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_package_descriptor(descriptor)

    class DummyDriveClient:
        def list_folder_files_from_weburl(self, url: str, *, recursive: bool = True):
            assert url == "https://drive.google.com/drive/folders/folder123"
            assert recursive is True
            return [
                {"id": "file-2", "relative_path": "nested/detail.csv"},
                {"id": "file-1", "relative_path": "summary.csv"},
            ]

    summary = sync_package_resource_in_descriptor(
        descriptor,
        "census-package",
        googledrive_client_factory=lambda: DummyDriveClient(),
        log=None,
    )

    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))

    assert summary.package_name == "census-package"
    assert summary.generated_resources == 2
    assert summary.changed is True
    assert document["resources"][0]["resources"] == [
        {
            "name": "nested/detail.csv",
            "path": "nested/detail.csv",
            "sources": [{"path": "https://drive.google.com/open?id=file-2"}],
        },
        {
            "name": "summary.csv",
            "path": "summary.csv",
            "sources": [{"path": "https://drive.google.com/open?id=file-1"}],
        },
    ]


def test_sync_package_resource_in_descriptor_dry_run_does_not_write(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_package_descriptor(descriptor)
    before = descriptor.read_text(encoding="utf-8")

    class DummyDriveClient:
        def list_folder_files_from_weburl(self, _url: str, *, recursive: bool = True):
            assert recursive is True
            return [{"id": "file-1", "relative_path": "summary.csv"}]

    summary = sync_package_resource_in_descriptor(
        descriptor,
        "census-package",
        dry_run=True,
        googledrive_client_factory=lambda: DummyDriveClient(),
        log=None,
    )

    assert summary.dry_run is True
    assert summary.changed is False
    assert descriptor.read_text(encoding="utf-8") == before


def test_sync_package_resource_in_descriptor_rejects_non_package(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    descriptor.write_text(
        """
resources:
  - name: drive-export
    path: downloads/export.csv
    driveService: googledrive
    sources:
      - path: https://docs.google.com/spreadsheets/d/test-sheet/edit
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not a package resource"):
        sync_package_resource_in_descriptor(
            descriptor,
            "drive-export",
            googledrive_client_factory=lambda: object(),
            log=None,
        )