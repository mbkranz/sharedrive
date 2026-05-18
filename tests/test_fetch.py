from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sharedrive.catalog import CatalogSelector, SharedriveCatalog


def _write_descriptor(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "$schema": "data-package-catalog",
                "resources": [
                    {
                        "name": "drive-export",
                        "path": "https://docs.google.com/spreadsheets/d/test-sheet/edit",
                        "_cache": "downloads/export.csv",
                        "serviceType": "GoogleDrive",
                        "entityType": "File",
                    }
                ],
                "catalogs": [
                    {
                        "name": "research",
                        "accessURL": "https://drive.google.com/drive/folders/folder123",
                        "serviceType": "GoogleDrive",
                        "entityType": "Directory",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


class _File:
    id = "file-1"
    name = "summary.csv"
    path = "summary.csv"
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

    def download(self, target_path: str) -> None:
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        Path(target_path).write_text("ok", encoding="utf-8")


class _Folder:
    is_directory = True

    @property
    def children(self):
        return [_File()]

    def refresh(self, *, include_children: bool = True):
        return self


class _Client:
    def get_from_weburl(self, url: str):
        return _Folder() if "/folders/" in url else _File()


def test_fetch_populates_catalog_from_access_url(monkeypatch, tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    monkeypatch.setattr("sharedrive.catalog.get_client", lambda _name: _Client())

    summaries = SharedriveCatalog.from_path(descriptor).fetch(
        "research", log=None, persist=True
    )

    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
    assert summaries[0].generated_resources == 1
    assert document["catalogs"][0]["resources"][0]["path"] == _File.source_url
    assert document["catalogs"][0]["resources"][0]["_cache"] == _File.path


def test_download_uses_resource_cache(monkeypatch, tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    monkeypatch.setattr("sharedrive.catalog.get_client", lambda _name: _Client())

    summary = SharedriveCatalog.from_path(descriptor).download(
        "drive-export", output_dir=tmp_path, log=None
    )

    assert summary.ok
    assert summary.downloaded == 1
    assert (tmp_path / "downloads" / "export.csv").read_text(encoding="utf-8") == "ok"


def test_check_auth_selects_service_type_adapters(monkeypatch, tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    calls: list[str] = []

    class Provider:
        @classmethod
        def check_auth(cls):
            calls.append("googledrive")

    monkeypatch.setattr(
        "sharedrive.catalog.get_provider",
        lambda name: Provider if name == "googledrive" else None,
    )

    results = SharedriveCatalog.from_path(descriptor).check_auth()

    assert [result.adapter for result in results] == ["googledrive"]
    assert calls == ["googledrive"]


def test_download_requires_existing_descriptor(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="does not exist"):
        SharedriveCatalog.from_path(tmp_path / "missing.yaml").download(log=None)


def test_fetch_rejects_standalone_resource(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)

    with pytest.raises(ValueError, match="standalone resource"):
        SharedriveCatalog.from_path(descriptor).fetch("drive-export", log=None)


def test_fetch_accepts_multi_selectors_in_sorted_token_order(
    monkeypatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    descriptor.write_text(
        yaml.safe_dump(
            {
                "$schema": "data-package-catalog",
                "catalogs": [
                    {
                        "name": "research",
                        "accessURL": "https://drive.google.com/drive/folders/folder123",
                        "serviceType": "GoogleDrive",
                        "entityType": "Directory",
                    },
                    {
                        "name": "archive",
                        "accessURL": "https://drive.google.com/drive/folders/folder456",
                        "serviceType": "GoogleDrive",
                        "entityType": "Directory",
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("sharedrive.catalog.get_client", lambda _name: _Client())

    summaries = SharedriveCatalog.from_path(descriptor).fetch(
        ["research", "archive"], log=None
    )

    expected = sorted(["research", "archive"])
    assert [summary.resource_name for summary in summaries] == expected
    assert all(summary.generated_resources == 1 for summary in summaries)


def test_fetch_accepts_catalog_selector_instance(
    monkeypatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    monkeypatch.setattr("sharedrive.catalog.get_client", lambda _name: _Client())

    summaries = SharedriveCatalog.from_path(descriptor).fetch(
        CatalogSelector("research"), log=None
    )

    assert len(summaries) == 1
    assert summaries[0].resource_name == "research"
