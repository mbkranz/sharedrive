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

        def get_from_weburl(self, url: str) -> None:
            calls = self.calls
            class DummyFileItem:
                @property
                def is_directory(self) -> bool:
                    return False
                def download(self, target_path: str) -> None:
                    calls.append((url, target_path))
                    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(target_path).write_text("ok", encoding="utf-8")
            return DummyFileItem()

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

        def get_from_weburl(self, url: str):
            list_calls = self.list_calls
            download_calls = self.download_calls
            list_calls.append((url, True))

            class DummyItem:
                def __init__(self, id, name, relative_path):
                    self.id = id
                    self.name = name
                    self.path = relative_path
                    self.is_directory = False

                def download(self, target_path: str):
                    download_calls.append((self.id, target_path))
                    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(target_path).write_text(self.id, encoding="utf-8")

            class DummyFolder:
                @property
                def is_directory(self):
                    return True

                @property
                def children(self):
                    return [
                        DummyItem("sheet-1", "summary.csv", "summary.csv"),
                        DummyItem("sheet-2", "detail.csv", "nested/detail.csv"),
                    ]

            return DummyFolder()

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

        def get_from_weburl(self, _url: str):
            download_calls = self.download_calls

            class DummyItem:
                def __init__(self, id, relative_path):
                    self.id = id
                    self.name = relative_path
                    self.path = relative_path
                    self.is_directory = False

                def download(self, target_path: str):
                    download_calls.append((self.id, target_path))
                    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(target_path).write_text(self.id, encoding="utf-8")

            class DummyFolder:
                @property
                def is_directory(self):
                    return True

                @property
                def children(self):
                    return [
                        DummyItem("file-1", "summary.csv"),
                        DummyItem("file-2", "nested/detail.csv"),
                    ]

            return DummyFolder()

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

        def get_from_weburl(self, url: str):
            calls = self.calls

            class DummyFileItem:
                @property
                def is_directory(self) -> bool:
                    return False

                def download(self, target_path: str) -> None:
                    calls.append((url, target_path))
                    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(target_path).write_text("nested-ok", encoding="utf-8")

            return DummyFileItem()

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

        def get_from_weburl(self, url: str):
            calls = self.calls

            class DummyFileItem:
                @property
                def is_directory(self) -> bool:
                    return False

                def download(self, target_path: str) -> None:
                    calls.append((url, target_path))
                    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(target_path).write_text("nested-ok", encoding="utf-8")

            return DummyFileItem()

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

        def get_from_weburl(self, url: str):
            calls = self.calls

            class DummyFileItem:
                @property
                def is_directory(self) -> bool:
                    return False

                def download(self, target_path: str) -> None:
                    calls.append((url, target_path))
                    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(target_path).write_text("nested-ok", encoding="utf-8")

            return DummyFileItem()

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
        def get_from_weburl(self, url: str):
            assert url == "https://example.sharepoint.com/sites/Test/Shared%20Documents/specs"

            class DummyFolder:
                @property
                def is_directory(self): return True

                @property
                def children(self):
                    class DummyItem1:
                        @property
                        def id(self): return "1"
                        @property
                        def name(self): return "spec.xlsx"
                        @property
                        def path(self): return "spec.xlsx"
                        @property
                        def is_directory(self): return False
                        @property
                        def source_url(self): return "https://example.sharepoint.com/sites/Test/Shared%20Documents/specs/spec.xlsx"
                        def to_dp(self):
                            from sharedrive.models import DriveSource, DriveResource
                            return DriveResource(
                                name="spec.xlsx",
                                path="downloads/shared-specs/spec.xlsx",
                                format="xlsx",
                                mediatype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                sources=[
                                    DriveSource(
                                        title="spec.xlsx",
                                        path="https://example.sharepoint.com/sites/Test/Shared%20Documents/specs/spec.xlsx",
                                        email="",
                                        serviceType="SharePoint",
                                        entityType="object",
                                    )
                                ],
                            )

                    class DummyItem2:
                        @property
                        def id(self): return "2"
                        @property
                        def name(self): return "detail.csv"
                        @property
                        def path(self): return "nested/detail.csv"
                        @property
                        def is_directory(self): return False
                        @property
                        def source_url(self): return "https://example.sharepoint.com/sites/Test/Shared%20Documents/specs/nested/detail.csv"
                        def to_dp(self):
                            from sharedrive.models import DriveSource, DriveResource
                            return DriveResource(
                                name="detail.csv",
                                path="downloads/shared-specs/nested/detail.csv",
                                format="csv",
                                mediatype="text/csv",
                                sources=[
                                    DriveSource(
                                        title="detail.csv",
                                        path="https://example.sharepoint.com/sites/Test/Shared%20Documents/specs/nested/detail.csv",
                                        email="",
                                        serviceType="SharePoint",
                                        entityType="object",
                                    )
                                ],
                            )
                    return [DummyItem1(), DummyItem2()]
            return DummyFolder()

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