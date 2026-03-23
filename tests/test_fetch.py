from __future__ import annotations

from pathlib import Path

from sharedrive.actions.download import check_auth_for_descriptor, download_from_descriptor
from sharedrive.actions.download import resource_adapter_name
from sharedrive.actions.fetch import fetch_resource_metadata_in_descriptor


def _write_descriptor(path: Path) -> None:
    path.write_text(
        """
resources:
  - name: sharepoint-spec
    path: downloads/spec.xlsx
    syncTarget: path
    sources:
      - path: https://example.sharepoint.com/sites/Test/Shared%20Documents/spec.xlsx
        serviceType: SharePoint
        entityType: File
  - name: drive-export
    path: downloads/export.csv
    syncTarget: path
    sources:
      - path: https://docs.google.com/spreadsheets/d/test-sheet/edit
        serviceType: GoogleDrive
        entityType: File
  - name: raw-data
    path: downloads/raw.csv
    syncTarget: path
    sources:
      - path: s3://bucket/raw.csv
        serviceType: S3
        entityType: File
""".strip(),
        encoding="utf-8",
    )


def test_check_auth_for_descriptor_limits_checks_to_selected_adapters(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    calls: list[str] = []

    def sharepoint_factory():
        calls.append("sharepoint")
        return object()

    def unexpected_gdrive_factory():
        raise AssertionError("Google Drive auth check should not run")

    def unexpected_s3_check() -> None:
        raise AssertionError("S3 auth check should not run")

    results = check_auth_for_descriptor(
        descriptor,
        include=["sharepoint"],
        sharepoint_client_factory=sharepoint_factory,
        googledrive_client_factory=unexpected_gdrive_factory,
        s3_auth_checker=unexpected_s3_check,
    )

    assert calls == ["sharepoint"]
    assert [result.adapter for result in results] == ["sharepoint"]
    assert results[0].ok is True


def test_fetch_from_descriptor_check_auth_stops_before_download_on_failure(
    tmp_path: Path,
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    messages: list[str] = []

    def failing_sharepoint_factory():
        raise RuntimeError("missing Azure tenant")

    summary = download_from_descriptor(
        descriptor,
        include=["sharepoint"],
        output_dir=tmp_path / "resources",
        dry_run=False,
        check_auth=True,
        log=messages.append,
        sharepoint_client_factory=failing_sharepoint_factory,
        googledrive_client_factory=lambda: object(),
    )

    assert summary.ok is False
    assert summary.failures == 1
    assert summary.downloaded == 0
    assert any("Auth check failed for sharepoint" in message for message in messages)
    assert not (tmp_path / "resources" / "downloads" / "spec.xlsx").exists()


def test_fetch_from_descriptor_check_auth_allows_download_when_ready(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)

    class DummyDriveClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def _ensure_valid_credentials(self) -> None:
            return None

        def download_from_weburl(self, url: str, output_path: str) -> None:
            self.calls.append((url, output_path))
            Path(output_path).write_text("ok", encoding="utf-8")

    client = DummyDriveClient()

    summary = download_from_descriptor(
        descriptor,
        include=["googledrive"],
        output_dir=tmp_path / "resources",
        dry_run=False,
        check_auth=True,
        log=lambda _message: None,
        googledrive_client_factory=lambda: client,
    )

    output_path = tmp_path / "resources" / "downloads" / "export.csv"
    assert summary.ok is True
    assert summary.downloaded == 1
    assert client.calls == [
        (
            "https://docs.google.com/spreadsheets/d/test-sheet/edit",
            str(output_path),
        )
    ]
    assert output_path.read_text(encoding="utf-8") == "ok"


def test_fetch_from_descriptor_materializes_google_drive_directory_resources(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    descriptor.write_text(
        """
resources:
  - name: census-docs
    path: downloads/census
    syncTarget: resources
    sources:
      - path: https://drive.google.com/drive/folders/folder123
        serviceType: GoogleDrive
        entityType: Directory
""".strip(),
        encoding="utf-8",
    )

    class DummyDriveClient:
        def __init__(self) -> None:
            self.list_calls: list[tuple[str, bool]] = []
            self.download_calls: list[tuple[str, str]] = []

        def list_folder_files_from_weburl(self, url: str, *, recursive: bool = True):
            self.list_calls.append((url, recursive))
            return [
                {"id": "sheet-1", "name": "summary.csv", "relative_path": "summary.csv"},
                {"id": "sheet-2", "name": "detail.csv", "relative_path": "nested/detail.csv"},
            ]

        def download_file(self, file_id: str, output_path: str) -> None:
            self.download_calls.append((file_id, output_path))
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(file_id, encoding="utf-8")

    client = DummyDriveClient()

    summary = download_from_descriptor(
        descriptor,
        include=["googledrive"],
        output_dir=tmp_path / "resources",
        dry_run=False,
        log=lambda _message: None,
        googledrive_client_factory=lambda: client,
    )

    summary_path = tmp_path / "resources" / "downloads" / "census" / "summary.csv"
    detail_path = tmp_path / "resources" / "downloads" / "census" / "nested" / "detail.csv"
    assert summary.ok is True
    assert summary.downloaded == 2
    assert client.list_calls == [
        ("https://drive.google.com/drive/folders/folder123", True)
    ]
    assert client.download_calls == [
        ("sheet-1", str(summary_path)),
        ("sheet-2", str(detail_path)),
    ]
    assert summary_path.read_text(encoding="utf-8") == "sheet-1"
    assert detail_path.read_text(encoding="utf-8") == "sheet-2"


def test_fetch_from_descriptor_materializes_google_drive_directory_path_target(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    descriptor.write_text(
        """
resources:
  - name: term-proposal-docs
    path: downloads/term-proposal-documents
    syncTarget: path
    sources:
      - path: https://drive.google.com/drive/folders/folder123
        serviceType: GoogleDrive
        entityType: Directory
""".strip(),
        encoding="utf-8",
    )

    class DummyDriveClient:
        def __init__(self) -> None:
            self.download_calls: list[tuple[str, str]] = []

        def list_folder_files_from_weburl(self, _url: str, *, recursive: bool = True):
            assert recursive is True
            return [
                {"id": "file-1", "relative_path": "summary.csv"},
                {"id": "file-2", "relative_path": "nested/detail.csv"},
            ]

        def download_file(self, file_id: str, output_path: str) -> None:
            self.download_calls.append((file_id, output_path))
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text(file_id, encoding="utf-8")

    client = DummyDriveClient()

    summary = download_from_descriptor(
        descriptor,
        include=["googledrive"],
        output_dir=tmp_path / "resources",
        dry_run=False,
        log=lambda _message: None,
        googledrive_client_factory=lambda: client,
    )

    assert summary.ok is True
    assert summary.downloaded == 2
    assert client.download_calls == [
        (
            "file-1",
            str(tmp_path / "resources" / "downloads" / "term-proposal-documents" / "summary.csv"),
        ),
        (
            "file-2",
            str(tmp_path / "resources" / "downloads" / "term-proposal-documents" / "nested" / "detail.csv"),
        ),
    ]


def test_fetch_from_descriptor_fetches_nested_package_resources(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    descriptor.write_text(
        """
resources:
  - name: analytics-docs
    path: downloads/analytics
    syncTarget: resources
    sources:
      - path: https://drive.google.com/drive/folders/folder123
        serviceType: GoogleDrive
        entityType: Directory
    resources:
      - name: selected-export
        path: export.csv
        sources:
          - path: https://docs.google.com/spreadsheets/d/test-sheet/edit
            serviceType: GoogleDrive
            entityType: File
""".strip(),
        encoding="utf-8",
    )

    class DummyDriveClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def download_from_weburl(self, url: str, output_path: str) -> None:
            self.calls.append((url, output_path))
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text("nested-ok", encoding="utf-8")

    client = DummyDriveClient()

    summary = download_from_descriptor(
        descriptor,
        include=["selected-export"],
        output_dir=tmp_path / "resources",
        dry_run=False,
        log=lambda _message: None,
        googledrive_client_factory=lambda: client,
    )

    output_path = tmp_path / "resources" / "downloads" / "analytics" / "export.csv"
    assert summary.ok is True
    assert summary.downloaded == 1
    assert client.calls == [
        (
            "https://docs.google.com/spreadsheets/d/test-sheet/edit",
            str(output_path),
        )
    ]
    assert output_path.read_text(encoding="utf-8") == "nested-ok"


def test_fetch_from_descriptor_matches_nested_dot_path_include(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    descriptor.write_text(
        """
resources:
  - name: analytics-docs
    path: downloads/analytics
    syncTarget: resources
    sources:
      - path: https://drive.google.com/drive/folders/folder123
        serviceType: GoogleDrive
        entityType: Directory
    resources:
      - name: selected-export
        path: export.csv
        sources:
          - path: https://docs.google.com/spreadsheets/d/test-sheet/edit
            serviceType: GoogleDrive
            entityType: File
      - name: other-export
        path: other.csv
        sources:
          - path: https://docs.google.com/spreadsheets/d/other-sheet/edit
            serviceType: GoogleDrive
            entityType: File
""".strip(),
        encoding="utf-8",
    )

    class DummyDriveClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def download_from_weburl(self, url: str, output_path: str) -> None:
            self.calls.append((url, output_path))
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text("nested-ok", encoding="utf-8")

    client = DummyDriveClient()

    summary = download_from_descriptor(
        descriptor,
        include=["analytics-docs.selected-export"],
        output_dir=tmp_path / "resources",
        dry_run=False,
        log=lambda _message: None,
        googledrive_client_factory=lambda: client,
    )

    output_path = tmp_path / "resources" / "downloads" / "analytics" / "export.csv"
    assert summary.ok is True
    assert summary.downloaded == 1
    assert client.calls == [
        (
            "https://docs.google.com/spreadsheets/d/test-sheet/edit",
            str(output_path),
        )
    ]


def test_fetch_from_descriptor_matches_top_level_package_name(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    descriptor.write_text(
        """
resources:
  - name: analytics-docs
    path: downloads/analytics
    syncTarget: resources
    sources:
      - path: https://drive.google.com/drive/folders/folder123
        serviceType: GoogleDrive
        entityType: Directory
    resources:
      - name: selected-export
        path: export.csv
        sources:
          - path: https://docs.google.com/spreadsheets/d/test-sheet/edit
            serviceType: GoogleDrive
            entityType: File
""".strip(),
        encoding="utf-8",
    )

    class DummyDriveClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def download_from_weburl(self, url: str, output_path: str) -> None:
            self.calls.append((url, output_path))
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text("nested-ok", encoding="utf-8")

    client = DummyDriveClient()

    summary = download_from_descriptor(
        descriptor,
        include=["analytics-docs"],
        output_dir=tmp_path / "resources",
        dry_run=False,
        log=lambda _message: None,
        googledrive_client_factory=lambda: client,
    )

    output_path = tmp_path / "resources" / "downloads" / "analytics" / "export.csv"
    assert summary.ok is True
    assert summary.downloaded == 1
    assert client.calls == [
        (
            "https://docs.google.com/spreadsheets/d/test-sheet/edit",
            str(output_path),
        )
    ]


def test_fetch_resource_metadata_supports_sharepoint_directory(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    descriptor.write_text(
        """
resources:
  - name: shared-specs
    path: downloads/shared-specs
    syncTarget: resources
    sources:
      - path: https://example.sharepoint.com/sites/Test/Shared%20Documents/specs
        serviceType: SharePoint
        entityType: Directory
""".strip(),
        encoding="utf-8",
    )

    class DummySharepointClient:
        def list_folder_files_from_weburl(self, url: str, *, recursive: bool = True):
            assert url == "https://example.sharepoint.com/sites/Test/Shared%20Documents/specs"
            assert recursive is True
            return [
                {
                    "webUrl": "https://example.sharepoint.com/sites/Test/Shared%20Documents/specs/spec.xlsx",
                    "relative_path": "spec.xlsx",
                },
                {
                    "webUrl": "https://example.sharepoint.com/sites/Test/Shared%20Documents/specs/nested/detail.csv",
                    "relative_path": "nested/detail.csv",
                },
            ]

    summary = fetch_resource_metadata_in_descriptor(
        descriptor=descriptor,
        resource_name="shared-specs",
        dry_run=False,
        log=lambda _message: None,
        sharepoint_client_factory=lambda: DummySharepointClient(),
    )

    assert summary.changed is True
    assert summary.generated_resources == 2

    document = descriptor.read_text(encoding="utf-8")
    assert "nested/detail.csv" in document
    assert "serviceType: SharePoint" in document


def test_resource_adapter_name_prefers_drive_service_over_legacy_adapter() -> None:
    resource = {
        "sources": [
            {
                "serviceType": "SharePoint",
                "path": "https://example.invalid/file.xlsx",
            }
        ],
        "x-adapter": "s3",
    }

    assert resource_adapter_name(resource, "s3://bucket/raw.csv") == "sharepoint"


def test_resource_adapter_name_supports_legacy_x_adapter() -> None:
    resource = {"x-adapter": "googledrive"}

    assert (
        resource_adapter_name(
            resource,
            "https://example.invalid/path.csv",
        )
        == "googledrive"
    )


def test_download_from_descriptor_requires_existing_descriptor(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"

    try:
        download_from_descriptor(missing, output_dir=tmp_path / "resources")
    except FileNotFoundError as exc:
        assert "does not exist" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected FileNotFoundError for missing descriptor")


def test_check_auth_for_descriptor_requires_existing_descriptor(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"

    try:
        check_auth_for_descriptor(missing)
    except FileNotFoundError as exc:
        assert "does not exist" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected FileNotFoundError for missing descriptor")