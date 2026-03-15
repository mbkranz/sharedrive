from __future__ import annotations

from pathlib import Path

from sharedrive.actions.fetch import check_auth_for_descriptor, fetch_from_descriptor
from sharedrive.actions.fetch import resource_adapter_name


def _write_descriptor(path: Path) -> None:
    path.write_text(
        """
resources:
  - name: sharepoint-spec
    path: downloads/spec.xlsx
    x-adapter: sharepoint
    sources:
      - path: https://example.sharepoint.com/sites/Test/Shared%20Documents/spec.xlsx
  - name: drive-export
    path: downloads/export.csv
    x-adapter: googledrive
    sources:
      - path: https://docs.google.com/spreadsheets/d/test-sheet/edit
  - name: raw-data
    path: downloads/raw.csv
    x-adapter: s3
    sources:
      - path: s3://bucket/raw.csv
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

    summary = fetch_from_descriptor(
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

    summary = fetch_from_descriptor(
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


def test_resource_adapter_name_prefers_drive_service_over_legacy_adapter() -> None:
    resource = {
        "driveService": "sharepoint",
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