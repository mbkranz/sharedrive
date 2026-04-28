from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sharedrive.actions.fetch import fetch_resource_metadata_in_descriptor
from sharedrive.registry import get_provider


def _write_syncable_descriptor(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "$schema": "data-package-catalog",
                "resources": [],
                "packages": [
                    {
                        "name": "census-docs",
                        "path": "downloads/census",
                        "syncTarget": "resources",
                        "sources": [
                            {
                                "path": "https://drive.google.com/drive/folders/folder123",
                                "serviceType": "GoogleDrive",
                                "entityType": "Directory",
                            }
                        ],
                    }
                ],
                "catalogs": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _patch_fetch_registry(
    monkeypatch: pytest.MonkeyPatch,
    *,
    googledrive_factory=None,
    sharepoint_factory=None,
) -> None:
    _real_get_provider = get_provider

    def fake_get_provider(name: str):
        if name == "googledrive" and googledrive_factory is not None:

            class _GDriveStub:
                @classmethod
                def build_default(cls):
                    return googledrive_factory()

            return _GDriveStub
        if name == "sharepoint" and sharepoint_factory is not None:

            class _SPStub:
                @classmethod
                def build_default(cls):
                    return sharepoint_factory()

            return _SPStub
        return _real_get_provider(name)

    monkeypatch.setattr(
        "sharedrive.actions.fetch.get_provider", fake_get_provider
    )


def test_fetch_resource_metadata_in_descriptor_writes_nested_resources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_syncable_descriptor(descriptor)

    class DummyDriveClient:
        def get_from_weburl(self, url: str):
            assert url == "https://drive.google.com/drive/folders/folder123"

            class DummyItem:
                def __init__(self, n, p, d=False):
                    self.name = n
                    self.path = p
                    self.is_directory = d
                    self.id = "id"
                    self.service_type = "GoogleDrive"
                    self.source_url = f"https://drive.google.com/open?id={n}"

                def to_resource(self):
                    from sharedrive.models import DriveResource, DriveSource

                    return DriveResource(
                        name=self.path,
                        path=self.path,
                        sources=[
                            DriveSource(
                                path=self.source_url,
                                serviceType=self.service_type,
                                entityType="File",
                            )
                        ],
                    )

            class DummyFolder(DummyItem):
                @property
                def children(self):
                    return [
                        DummyItem("file-2", "nested/detail.csv"),
                        DummyItem("file-1", "summary.csv"),
                    ]

            return DummyFolder("folder", "folder", True)

    _patch_fetch_registry(monkeypatch, googledrive_factory=lambda: DummyDriveClient())

    summary = fetch_resource_metadata_in_descriptor(descriptor, "census-docs", log=None)

    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))

    assert summary.resource_name == "census-docs"
    assert summary.generated_resources == 2
    assert summary.changed is True
    assert document["packages"][0]["resources"] == [
        {
            "name": "nested/detail.csv",
            "path": "nested/detail.csv",
            "sources": [
                {
                    "path": "https://drive.google.com/open?id=file-2",
                    "serviceType": "GoogleDrive",
                    "entityType": "File",
                }
            ],
        },
        {
            "name": "summary.csv",
            "path": "summary.csv",
            "sources": [
                {
                    "path": "https://drive.google.com/open?id=file-1",
                    "serviceType": "GoogleDrive",
                    "entityType": "File",
                }
            ],
        },
    ]


def test_fetch_resource_metadata_in_descriptor_dry_run_does_not_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_syncable_descriptor(descriptor)
    before = descriptor.read_text(encoding="utf-8")

    class DummyDriveClient:
        def get_from_weburl(self, _url: str):
            class DummyItem:
                def __init__(self, n, p, d=False):
                    self.name = n
                    self.path = p
                    self.is_directory = d
                    self.id = "id"
                    self.service_type = "GoogleDrive"
                    self.source_url = f"https://drive.google.com/open?id={n}"

                def to_resource(self):
                    from sharedrive.models import DriveResource, DriveSource

                    return DriveResource(
                        name=self.path,
                        path=self.path,
                        sources=[
                            DriveSource(
                                path=self.source_url,
                                serviceType=self.service_type,
                                entityType="File",
                            )
                        ],
                    )

            class DummyFolder(DummyItem):
                @property
                def children(self):
                    return [DummyItem("file-1", "summary.csv")]

            return DummyFolder("folder", "folder", True)

    _patch_fetch_registry(monkeypatch, googledrive_factory=lambda: DummyDriveClient())

    summary = fetch_resource_metadata_in_descriptor(
        descriptor, "census-docs", dry_run=True, log=None
    )

    assert summary.dry_run is True
    assert summary.changed is False
    assert descriptor.read_text(encoding="utf-8") == before


def test_fetch_resource_metadata_in_descriptor_rejects_path_sync_target(
    tmp_path: Path,
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    descriptor.write_text(
        yaml.safe_dump(
            {
                "$schema": "data-package-catalog",
                "resources": [
                    {
                        "name": "drive-export",
                        "path": "downloads/export.csv",
                        "syncTarget": "path",
                        "sources": [
                            {
                                "path": "https://docs.google.com/spreadsheets/d/test-sheet/edit",
                                "serviceType": "GoogleDrive",
                                "entityType": "File",
                            }
                        ],
                    }
                ],
                "packages": [],
                "catalogs": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="syncTarget 'resources'"):
        fetch_resource_metadata_in_descriptor(descriptor, "drive-export", log=None)


def test_fetch_resource_metadata_in_descriptor_requires_existing_descriptor(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.yaml"

    with pytest.raises(FileNotFoundError, match="does not exist"):
        fetch_resource_metadata_in_descriptor(missing, "census-docs", log=None)
