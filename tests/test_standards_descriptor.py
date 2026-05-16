from __future__ import annotations

from pathlib import Path

import yaml

from sharedrive.actions.add import add_resource_to_descriptor
from sharedrive.actions.download import download
from sharedrive.actions.fetch import fetch
from sharedrive.actions.migrate import migrate_descriptor


class _FileItem:
    id = "file-1"
    name = "report.csv"
    path = "reports/report.csv"
    service_type = "GoogleDrive"
    source_url = "https://drive.google.com/file/d/file-1"
    is_directory = False

    def refresh(self, *, include_children: bool = True):
        return self

    def to_resource(self):
        from sharedrive.models import DriveResource

        return DriveResource.from_drive_metadata(
            name=self.path,
            path=self.path,
            service_type=self.service_type,
            entity_type="File",
            source_url=self.source_url,
            format_str="csv",
            drive_id=self.id,
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

    def to_resource(self):
        from sharedrive.models import DriveCatalog

        return DriveCatalog(
            name=self.path,
            accessURL=self.source_url,
            serviceType=self.service_type,
            entityType="Directory",
        )


class _Client:
    def get_from_weburl(self, url: str):
        return _FolderItem() if "/folders/" in url else _FileItem()


def test_add_writes_path_cache_resource_and_access_url_catalog(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"

    resource = add_resource_to_descriptor(
        descriptor,
        name="raw",
        path="s3://bucket/raw.csv",
        cache="downloads/raw.csv",
        create_if_missing=True,
    )
    catalog = add_resource_to_descriptor(
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
    add_resource_to_descriptor(
        descriptor,
        name="research",
        access_url="https://drive.google.com/drive/folders/folder-1",
        catalog=True,
        create_if_missing=True,
    )

    monkeypatch.setattr("sharedrive.actions.catalog.get_client", lambda _name: _Client())
    summaries = fetch(descriptor, "research", log=None)

    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
    child = document["catalogs"][0]["resources"][0]
    assert summaries[0].generated_resources == 1
    assert child["path"] == "https://drive.google.com/file/d/file-1"
    assert child["_cache"] == "reports/report.csv"

    monkeypatch.setattr("sharedrive.actions.catalog.get_client", lambda _name: _Client())
    summary = download(descriptor, output_dir=tmp_path, log=None)

    assert summary.downloaded == 1
    assert (tmp_path / "reports" / "report.csv").read_text(encoding="utf-8") == "ok"


def test_migrate_legacy_descriptor_to_canonical_shape(tmp_path: Path) -> None:
    descriptor = tmp_path / "legacy.yaml"
    descriptor.write_text(
        yaml.safe_dump(
            {
                "resources": [
                    {
                        "name": "raw",
                        "path": "downloads/raw.csv",
                        "sources": [
                            {
                                "path": "s3://bucket/raw.csv",
                                "serviceType": "S3",
                                "entityType": "File",
                            }
                        ],
                    }
                ],
                "packages": [
                    {
                        "name": "research",
                        "path": "downloads/research",
                        "sources": [
                            {
                                "path": "https://drive.google.com/drive/folders/folder-1",
                                "serviceType": "GoogleDrive",
                                "entityType": "Directory",
                            }
                        ],
                        "resources": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    migrated = migrate_descriptor(descriptor, dry_run=True).to_dict()

    assert migrated["resources"][0]["path"] == "s3://bucket/raw.csv"
    assert migrated["resources"][0]["_cache"] == "downloads/raw.csv"
    assert migrated["catalogs"][0]["accessURL"].endswith("folder-1")
