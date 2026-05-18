from __future__ import annotations

from pathlib import Path

import pytest

from sharedrive.actions.catalog import SharedriveCatalogAction
from sharedrive.clients.aws import S3Client
from sharedrive.clients.base import AdapterCapabilities
from sharedrive.models import DriveCatalog


class _DownloadItem:
    def __init__(self) -> None:
        self.download_calls: list[str] = []

    def download(self, target: str) -> None:
        self.download_calls.append(target)
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_text("ok", encoding="utf-8")


class _DownloadClient:
    def get_from_weburl(self, _url: str) -> _DownloadItem:
        return _DownloadItem()


def test_download_detects_output_collisions(tmp_path: Path) -> None:
    catalog = DriveCatalog.model_validate(
        {
            "$schema": "data-package-catalog",
            "resources": [
                {
                    "name": "a",
                    "path": "https://docs.google.com/file/d/a",
                    "_cache": "same/file.csv",
                    "serviceType": "GoogleDrive",
                    "entityType": "File",
                },
                {
                    "name": "b",
                    "path": "https://docs.google.com/file/d/b",
                    "_cache": "same/file.csv",
                    "serviceType": "GoogleDrive",
                    "entityType": "File",
                },
            ],
        }
    )

    action = SharedriveCatalogAction(catalog, client_factory=lambda _: _DownloadClient())

    with pytest.raises(ValueError, match="Output collision"):
        action.download(output_dir=tmp_path, dry_run=False, log=None)


def test_check_auth_reports_unsupported_adapter() -> None:
    catalog = DriveCatalog.model_validate(
        {
            "$schema": "data-package-catalog",
            "resources": [
                {
                    "name": "mystery",
                    "path": "https://example.invalid/path",
                    "_cache": "x",
                    "serviceType": "UnknownService",
                    "entityType": "File",
                }
            ],
        }
    )

    action = SharedriveCatalogAction(catalog)
    results = action.check_auth(adapters=["unknown"])

    assert len(results) == 1
    assert results[0].ok is False
    assert "Unsupported adapter" in results[0].message


def test_fetch_respects_adapter_capabilities() -> None:
    catalog = DriveCatalog.model_validate(
        {
            "$schema": "data-package-catalog",
            "catalogs": [
                {
                    "name": "bucket-root",
                    "accessURL": "s3://example-bucket/prefix/",
                    "serviceType": "S3",
                    "entityType": "Directory",
                }
            ],
        }
    )

    class _NoFetchProvider:
        capabilities = AdapterCapabilities(
            supports_fetch=False,
            supports_download=True,
            supports_auth_check=True,
            supports_write=False,
        )

        @classmethod
        def check_auth(cls) -> None:
            pass

    action = SharedriveCatalogAction(
        catalog,
        client_factory=lambda _: _DownloadClient(),
        provider_factory=lambda _: _NoFetchProvider,
    )

    summaries = action.fetch("bucket-root", dry_run=False, log=None)

    assert len(summaries) == 1
    assert summaries[0].failures == 1
    assert "does not support fetch operations" in summaries[0].errors[0]


def test_download_uses_s3_client_method(tmp_path: Path) -> None:
    catalog = DriveCatalog.model_validate(
        {
            "$schema": "data-package-catalog",
            "resources": [
                {
                    "name": "s3-object",
                    "path": "s3://example-bucket/path/file.csv",
                    "_cache": "downloads/file.csv",
                    "serviceType": "S3",
                    "entityType": "File",
                }
            ],
        }
    )

    class _StubS3BotoClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str]] = []

        def download_file(self, bucket: str, key: str, target: str) -> None:
            self.calls.append((bucket, key, target))

    inner = _StubS3BotoClient()
    action = SharedriveCatalogAction(catalog, client_factory=lambda _: S3Client(client=inner))

    summary = action.download(output_dir=tmp_path, dry_run=False, log=None)

    assert summary.ok
    assert summary.downloaded == 1
    assert len(inner.calls) == 1
    assert inner.calls[0][0] == "example-bucket"
    assert inner.calls[0][1] == "path/file.csv"
