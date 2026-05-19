from __future__ import annotations

from pathlib import Path

import yaml

from sharedrive.catalog import SharedriveCatalog
from sharedrive.commands.descriptor import _add_resource_to_descriptor


class _FileItem:
    id = "file-1"
    name = "report.csv"
    path = "reports/report.csv"
    service_type = "GoogleDrive"
    source_url = "https://drive.google.com/file/d/file-1"
    is_directory = False

    def refresh(self, *, include_children: bool = True):
        return self

    def to_catalog(self):
        from sharedrive.models import DriveResource

        return DriveResource(
            name=self.path,
            path=self.source_url,
            cache=self.path,
            serviceId=self.id,
            serviceType=self.service_type,
            entityType="File",
            format="csv",
        )

    def download(self, target: Path | str) -> None:
        Path(target).write_text("ok", encoding="utf-8")


class _FolderItem:
    id = "folder-1"
    name = "Research"
    path = "research"
    service_type = "GoogleDrive"
    source_url = "https://drive.google.com/drive/folders/folder-1"
    is_directory = True

    @property
    def children(self):
        return [_FileItem()]

    def refresh(self, *, include_children: bool = True):
        return self

    def to_catalog(self):
        from sharedrive.models import DriveCatalog

        return DriveCatalog(
            name=self.path,
            accessURL=self.source_url,
            serviceId=self.id,
            serviceType=self.service_type,
            entityType="Directory",
        )


class _Client:
    def get_from_weburl(self, url: str):
        return _FolderItem() if "/folders/" in url else _FileItem()


def test_add_writes_path_cache_resource_and_access_url_catalog(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"

    resource = _add_resource_to_descriptor(
        descriptor,
        name="raw",
        path="s3://bucket/raw.csv",
        cache="downloads/raw.csv",
        create_if_missing=True,
    )
    catalog = _add_resource_to_descriptor(
        descriptor,
        name="research",
        access_url="https://drive.google.com/drive/folders/folder-1",
        catalog=True,
    )

    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))

    assert resource["path"] == "s3://bucket/raw.csv"
    assert resource["_cache"] == "downloads/raw.csv"
    assert "sources" not in resource
    assert catalog["accessURL"].endswith("folder-1")
    assert document["resources"][0]["_cache"] == "downloads/raw.csv"
    assert document["catalogs"][0]["accessURL"].endswith("folder-1")


def test_fetch_expands_catalog_and_download_uses_cache(
    monkeypatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _add_resource_to_descriptor(
        descriptor,
        name="research",
        access_url="https://drive.google.com/drive/folders/folder-1",
        catalog=True,
        create_if_missing=True,
    )

    monkeypatch.setattr("sharedrive.catalog.get_client", lambda _name: _Client())
    summaries = SharedriveCatalog.from_path(descriptor).fetch(
        "research", log=None, persist=True
    )

    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
    child = document["catalogs"][0]["resources"][0]
    assert summaries[0].generated_resources == 1
    assert child["path"] == "https://drive.google.com/file/d/file-1"
    assert child["_cache"] == "reports/report.csv"

    monkeypatch.setattr("sharedrive.catalog.get_client", lambda _name: _Client())
    summary = SharedriveCatalog.from_path(descriptor).download(
        output_dir=tmp_path, log=None
    )

    assert summary.downloaded == 1
    assert (tmp_path / "reports" / "report.csv").read_text(encoding="utf-8") == "ok"
