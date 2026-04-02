from __future__ import annotations

from pathlib import Path

import yaml

from sharedrive.actions.download import check_auth_for_descriptor, download_from_descriptor
from sharedrive.actions.download import resource_adapter_name
from sharedrive.actions.fetch import fetch_entity_metadata_in_descriptor, fetch_resource_metadata_in_descriptor
from sharedrive.clients.googledrive import GDriveFile, GDriveFolder
from sharedrive.clients.sharepoint import SharepointFile, SharepointFolder
from sharedrive.item import DriveFile, DriveFolder


def _write_catalog_descriptor(
    path: Path,
    *,
    resources: list[dict] | None = None,
    packages: list[dict] | None = None,
    catalogs: list[dict] | None = None,
) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "$schema": "data-package-catalog",
                "resources": resources or [],
                "packages": packages or [],
                "catalogs": catalogs or [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_drive_file_refresh_returns_self() -> None:
    class DummyFile(DriveFile):
        def __init__(self, *, item_id: str, name: str, path: str, source_url: str) -> None:
            self._id = item_id
            self._name = name
            self._path = path
            self._source_url = source_url

        @property
        def id(self) -> str:
            return self._id

        @property
        def name(self) -> str:
            return self._name

        @property
        def path(self) -> str:
            return self._path

        @property
        def service_type(self) -> str:
            return "GoogleDrive"

        @property
        def source_url(self) -> str:
            return self._source_url

        def download(self, target: Path | str) -> None:
            raise NotImplementedError

        def refresh(self, *, include_children: bool = True) -> "DummyFile":
            return self

    item = DummyFile(
        item_id="file-1",
        name="summary.csv",
        path="summary.csv",
        source_url="https://example.invalid/summary.csv",
    )

    assert item.refresh() is item


def test_drive_folder_refresh_returns_self_and_preserves_children() -> None:
    class DummyFile(DriveFile):
        def __init__(self, *, item_id: str, name: str, path: str, source_url: str) -> None:
            self._id = item_id
            self._name = name
            self._path = path
            self._source_url = source_url

        @property
        def id(self) -> str:
            return self._id

        @property
        def name(self) -> str:
            return self._name

        @property
        def path(self) -> str:
            return self._path

        @property
        def service_type(self) -> str:
            return "GoogleDrive"

        @property
        def source_url(self) -> str:
            return self._source_url

        def download(self, target: Path | str) -> None:
            raise NotImplementedError

        def refresh(self, *, include_children: bool = True) -> "DummyFile":
            return self

    class DummyFolder(DriveFolder):
        def __init__(self, *, item_id: str, name: str, path: str, children: list[DriveFile | DriveFolder]) -> None:
            self._id = item_id
            self._name = name
            self._path = path
            self._children = children

        @property
        def id(self) -> str:
            return self._id

        @property
        def name(self) -> str:
            return self._name

        @property
        def path(self) -> str:
            return self._path

        @property
        def service_type(self) -> str:
            return "GoogleDrive"

        @property
        def source_url(self) -> str:
            return "https://drive.google.com/drive/folders/example"

        @property
        def children(self) -> list[DriveFile | DriveFolder]:
            return self._children

        def refresh(self, *, include_children: bool = True) -> "DummyFolder":
            return self

    nested_folder = DummyFolder(
        item_id="folder-2",
        name="nested",
        path="nested",
        children=[
            DummyFile(
                item_id="file-2",
                name="detail.csv",
                path="nested/detail.csv",
                source_url="https://example.invalid/detail.csv",
            )
        ],
    )
    summary_file = DummyFile(
        item_id="file-1",
        name="summary.csv",
        path="summary.csv",
        source_url="https://example.invalid/summary.csv",
    )

    folder = DummyFolder(
        item_id="folder-1",
        name="folder",
        path="folder",
        children=[nested_folder, summary_file],
    )

    refreshed = folder.refresh()

    assert refreshed is folder
    assert folder.children == [
        nested_folder,
        summary_file,
    ]


def test_fetch_build_child_resources_flattens_runtime_items() -> None:
    class DummyFile(DriveFile):
        def __init__(self, *, item_id: str, name: str, path: str, source_url: str) -> None:
            self._id = item_id
            self._name = name
            self._path = path
            self._source_url = source_url

        @property
        def id(self) -> str:
            return self._id

        @property
        def name(self) -> str:
            return self._name

        @property
        def path(self) -> str:
            return self._path

        @property
        def service_type(self) -> str:
            return "GoogleDrive"

        @property
        def source_url(self) -> str:
            return self._source_url

        def download(self, target: Path | str) -> None:
            raise NotImplementedError

        def refresh(self, *, include_children: bool = True) -> "DummyFile":
            return self

    class DummyFolder(DriveFolder):
        def __init__(self, *, item_id: str, name: str, path: str, children: list[DriveFile | DriveFolder]) -> None:
            self._id = item_id
            self._name = name
            self._path = path
            self._children = children

        @property
        def id(self) -> str:
            return self._id

        @property
        def name(self) -> str:
            return self._name

        @property
        def path(self) -> str:
            return self._path

        @property
        def service_type(self) -> str:
            return "GoogleDrive"

        @property
        def source_url(self) -> str:
            return "https://drive.google.com/drive/folders/example"

        @property
        def children(self) -> list[DriveFile | DriveFolder]:
            return self._children

        def refresh(self, *, include_children: bool = True) -> "DummyFolder":
            return self

    folder = DummyFolder(
        item_id="folder-1",
        name="folder",
        path="folder",
        children=[
            DummyFolder(
                item_id="folder-2",
                name="nested",
                path="nested",
                children=[
                    DummyFile(
                        item_id="file-2",
                        name="detail.csv",
                        path="nested/detail.csv",
                        source_url="https://example.invalid/detail.csv",
                    )
                ],
            ),
            DummyFile(
                item_id="file-1",
                name="summary.csv",
                path="summary.csv",
                source_url="https://example.invalid/summary.csv",
            ),
        ],
    )

    from sharedrive.actions.fetch import _build_child_resources

    resources = _build_child_resources(folder)

    assert [resource["path"] for resource in resources] == [
        "nested/detail.csv",
        "summary.csv",
    ]


def test_gdrive_file_refresh_refreshes_metadata() -> None:
    class DummyClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def get_file(self, file_id: str, *, fields: str):
            self.calls.append((file_id, fields))
            return {
                "id": file_id,
                "name": "renamed.csv",
                "mimeType": "text/csv",
                "webViewLink": "https://example.invalid/refreshed",
                "relative_path": "nested/renamed.csv",
            }

        def _to_item(self, raw_metadata: dict, *, current_rel_path: str = "", scope_root: bool = False):
            return GDriveFile(raw_metadata=raw_metadata, client=self, current_rel_path=current_rel_path, scope_root=scope_root)

    client = DummyClient()
    item = GDriveFile(
        raw_metadata={
            "id": "file-1",
            "name": "summary.csv",
            "mimeType": "text/csv",
            "relative_path": "nested/summary.csv",
            "webViewLink": "https://example.invalid/original",
        },
        client=client,
        current_rel_path="",
        scope_root=False,
    )

    refreshed = item.refresh()

    assert isinstance(refreshed, GDriveFile)
    assert refreshed is item
    assert refreshed.name == "renamed.csv"
    assert refreshed.path == "nested/renamed.csv"
    assert client.calls == [
        ("file-1", "id,name,mimeType,parents,webViewLink"),
    ]


def test_gdrive_folder_refresh_refreshes_children() -> None:
    class DummyClient:
        def __init__(self) -> None:
            self.get_calls: list[tuple[str, str]] = []
            self.list_calls: list[tuple[str, bool]] = []

        def get_file(self, file_id: str, *, fields: str):
            self.get_calls.append((file_id, fields))
            return {
                "id": file_id,
                "name": "folder",
                "mimeType": "application/vnd.google-apps.folder",
                "relative_path": "folder",
                "webViewLink": "https://example.invalid/folder",
            }

        def list_folder_contents(self, folder_id: str, *, recursive: bool = False):
            self.list_calls.append((folder_id, recursive))
            return [
                {
                    "id": "child-1",
                    "name": "report.csv",
                    "mimeType": "text/csv",
                    "relative_path": "report.csv",
                    "webViewLink": "https://example.invalid/report",
                }
            ]

        def _to_item(self, raw_metadata: dict, *, current_rel_path: str = "", scope_root: bool = False):
            if raw_metadata.get("mimeType") == "application/vnd.google-apps.folder":
                return GDriveFolder(raw_metadata=raw_metadata, client=self, current_rel_path=current_rel_path, scope_root=scope_root)
            return GDriveFile(raw_metadata=raw_metadata, client=self, current_rel_path=current_rel_path, scope_root=scope_root)

    client = DummyClient()
    item = GDriveFolder(
        raw_metadata={
            "id": "folder-1",
            "name": "folder",
            "mimeType": "application/vnd.google-apps.folder",
            "relative_path": "folder",
        },
        client=client,
        current_rel_path="",
        scope_root=False,
    )

    refreshed = item.refresh()

    assert refreshed is item
    children = item.children
    assert len(children) == 1
    assert isinstance(children[0], GDriveFile)
    assert children[0].path == "folder/report.csv"
    assert client.get_calls == [("folder-1", "id,name,mimeType,parents,webViewLink")]
    assert client.list_calls == [("folder-1", False)]


def test_sharepoint_file_refresh_refreshes_metadata() -> None:
    class DummyClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def get_item_metadata(self, drive: str, *, item_path=None, item_id=None, fields=None):
            self.calls.append((drive, item_id))
            return {
                "id": item_id,
                "name": "renamed.csv",
                "file": {},
                "parentReference": {"driveId": drive},
                "webUrl": "https://example.invalid/refreshed",
                "relative_path": "nested/renamed.csv",
            }

        def _to_item(self, raw_metadata: dict, *, current_rel_path: str = "", scope_root: bool = False):
            return SharepointFile(raw_metadata=raw_metadata, client=self, current_rel_path=current_rel_path, scope_root=scope_root)

    client = DummyClient()
    item = SharepointFile(
        raw_metadata={
            "id": "file-1",
            "name": "summary.csv",
            "file": {},
            "parentReference": {"driveId": "drive-1"},
            "relative_path": "nested/summary.csv",
            "webUrl": "https://example.invalid/original",
        },
        client=client,
        current_rel_path="",
        scope_root=False,
    )

    refreshed = item.refresh()

    assert isinstance(refreshed, SharepointFile)
    assert refreshed is item
    assert refreshed.name == "renamed.csv"
    assert refreshed.path == "nested/renamed.csv"
    assert client.calls == [("drive-1", "file-1")]


def test_sharepoint_folder_refresh_refreshes_children() -> None:
    class DummyClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def get_item_metadata(self, drive: str, *, item_path=None, item_id=None, fields=None):
            self.calls.append((drive, item_id))
            return {
                "id": item_id,
                "name": "folder",
                "folder": {"childCount": 1},
                "parentReference": {"driveId": drive},
                "relative_path": "folder",
                "children": [
                    {
                        "id": "child-1",
                        "name": "report.csv",
                        "file": {},
                        "parentReference": {"driveId": drive},
                        "relative_path": "report.csv",
                        "webUrl": "https://example.invalid/report",
                    }
                ],
            }

        def _to_item(self, raw_metadata: dict, *, current_rel_path: str = "", scope_root: bool = False):
            if "folder" in raw_metadata:
                return SharepointFolder(raw_metadata=raw_metadata, client=self, current_rel_path=current_rel_path, scope_root=scope_root)
            return SharepointFile(raw_metadata=raw_metadata, client=self, current_rel_path=current_rel_path, scope_root=scope_root)

    client = DummyClient()
    item = SharepointFolder(
        raw_metadata={
            "id": "folder-1",
            "name": "folder",
            "folder": {"childCount": 1},
            "parentReference": {"driveId": "drive-1"},
            "relative_path": "folder",
        },
        client=client,
        current_rel_path="",
        scope_root=False,
    )

    refreshed = item.refresh()

    assert refreshed is item
    children = item.children
    assert len(children) == 1
    assert isinstance(children[0], SharepointFile)
    assert children[0].path == "folder/report.csv"
    assert client.calls == [("drive-1", "folder-1")]


def _write_descriptor(path: Path) -> None:
    _write_catalog_descriptor(
        path,
        resources=[
            {
                "name": "sharepoint-spec",
                "path": "downloads/spec.xlsx",
                "syncTarget": "path",
                "sources": [
                    {
                        "path": "https://example.sharepoint.com/sites/Test/Shared%20Documents/spec.xlsx",
                        "serviceType": "SharePoint",
                        "entityType": "File",
                    }
                ],
            },
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
            },
            {
                "name": "raw-data",
                "path": "downloads/raw.csv",
                "syncTarget": "path",
                "sources": [
                    {
                        "path": "s3://bucket/raw.csv",
                        "serviceType": "S3",
                        "entityType": "File",
                    }
                ],
            },
        ],
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
    _write_catalog_descriptor(
        descriptor,
        packages=[
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
    _write_catalog_descriptor(
        descriptor,
        resources=[
            {
                "name": "term-proposal-docs",
                "path": "downloads/term-proposal-documents",
                "syncTarget": "path",
                "sources": [
                    {
                        "path": "https://drive.google.com/drive/folders/folder123",
                        "serviceType": "GoogleDrive",
                        "entityType": "Directory",
                    }
                ],
            }
        ],
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
    _write_catalog_descriptor(
        descriptor,
        packages=[
            {
                "name": "analytics-docs",
                "path": "downloads/analytics",
                "syncTarget": "resources",
                "sources": [
                    {
                        "path": "https://drive.google.com/drive/folders/folder123",
                        "serviceType": "GoogleDrive",
                        "entityType": "Directory",
                    }
                ],
                "resources": [
                    {
                        "name": "selected-export",
                        "path": "export.csv",
                        "sources": [
                            {
                                "path": "https://docs.google.com/spreadsheets/d/test-sheet/edit",
                                "serviceType": "GoogleDrive",
                                "entityType": "File",
                            }
                        ],
                    }
                ],
            }
        ],
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
    _write_catalog_descriptor(
        descriptor,
        packages=[
            {
                "name": "analytics-docs",
                "path": "downloads/analytics",
                "syncTarget": "resources",
                "sources": [
                    {
                        "path": "https://drive.google.com/drive/folders/folder123",
                        "serviceType": "GoogleDrive",
                        "entityType": "Directory",
                    }
                ],
                "resources": [
                    {
                        "name": "selected-export",
                        "path": "export.csv",
                        "sources": [
                            {
                                "path": "https://docs.google.com/spreadsheets/d/test-sheet/edit",
                                "serviceType": "GoogleDrive",
                                "entityType": "File",
                            }
                        ],
                    },
                    {
                        "name": "other-export",
                        "path": "other.csv",
                        "sources": [
                            {
                                "path": "https://docs.google.com/spreadsheets/d/other-sheet/edit",
                                "serviceType": "GoogleDrive",
                                "entityType": "File",
                            }
                        ],
                    },
                ],
            }
        ],
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
    _write_catalog_descriptor(
        descriptor,
        packages=[
            {
                "name": "analytics-docs",
                "path": "downloads/analytics",
                "syncTarget": "resources",
                "sources": [
                    {
                        "path": "https://drive.google.com/drive/folders/folder123",
                        "serviceType": "GoogleDrive",
                        "entityType": "Directory",
                    }
                ],
                "resources": [
                    {
                        "name": "selected-export",
                        "path": "export.csv",
                        "sources": [
                            {
                                "path": "https://docs.google.com/spreadsheets/d/test-sheet/edit",
                                "serviceType": "GoogleDrive",
                                "entityType": "File",
                            }
                        ],
                    }
                ],
            }
        ],
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


def test_download_from_descriptor_matches_nested_catalog_package_name(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(
        descriptor,
        catalogs=[
            {
                "name": "research",
                "catalogs": [
                    {
                        "name": "archive",
                        "packages": [
                            {
                                "name": "analytics-docs",
                                "path": "downloads/analytics",
                                "syncTarget": "resources",
                                "sources": [
                                    {
                                        "path": "https://drive.google.com/drive/folders/folder123",
                                        "serviceType": "GoogleDrive",
                                        "entityType": "Directory",
                                    }
                                ],
                                "resources": [
                                    {
                                        "name": "selected-export",
                                        "path": "export.csv",
                                        "sources": [
                                            {
                                                "path": "https://docs.google.com/spreadsheets/d/test-sheet/edit",
                                                "serviceType": "GoogleDrive",
                                                "entityType": "File",
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
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
        include=["research.archive.analytics-docs"],
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
    _write_catalog_descriptor(
        descriptor,
        packages=[
            {
                "name": "shared-specs",
                "path": "downloads/shared-specs",
                "syncTarget": "resources",
                "sources": [
                    {
                        "path": "https://example.sharepoint.com/sites/Test/Shared%20Documents/specs",
                        "serviceType": "SharePoint",
                        "entityType": "Directory",
                    }
                ],
            }
        ],
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


def test_fetch_resource_metadata_resolves_nested_catalog_package_selector(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(
        descriptor,
        catalogs=[
            {
                "name": "research",
                "catalogs": [
                    {
                        "name": "archive",
                        "packages": [
                            {
                                "name": "shared-specs",
                                "path": "downloads/shared-specs",
                                "syncTarget": "resources",
                                "sources": [
                                    {
                                        "path": "https://example.sharepoint.com/sites/Test/Shared%20Documents/specs",
                                        "serviceType": "SharePoint",
                                        "entityType": "Directory",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    )

    class DummySharepointClient:
        def get_from_weburl(self, _url: str):
            class DummyFolder:
                @property
                def is_directory(self):
                    return True

                @property
                def children(self):
                    class DummyItem:
                        path = "spec.xlsx"
                        is_directory = False

                        def to_dp(self):
                            from sharedrive.models import DriveResource, DriveSource

                            return DriveResource(
                                name="spec.xlsx",
                                path="downloads/shared-specs/spec.xlsx",
                                sources=[
                                    DriveSource(
                                        path="https://example.sharepoint.com/sites/Test/Shared%20Documents/specs/spec.xlsx",
                                        serviceType="SharePoint",
                                        entityType="File",
                                    )
                                ],
                            )

                    return [DummyItem()]

            return DummyFolder()

    summary = fetch_resource_metadata_in_descriptor(
        descriptor=descriptor,
        resource_name="research.archive.shared-specs",
        dry_run=False,
        log=lambda _message: None,
        sharepoint_client_factory=lambda: DummySharepointClient(),
    )

    assert summary.changed is True
    assert summary.resource_name == "shared-specs"
    assert "spec.xlsx" in descriptor.read_text(encoding="utf-8")


def test_fetch_resource_metadata_rejects_legacy_package_root_descriptor(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    descriptor.write_text(
        """
resources:
  - name: legacy-package
    path: downloads/legacy
    syncTarget: resources
    sources:
      - path: https://drive.google.com/drive/folders/folder123
        serviceType: GoogleDrive
        entityType: Directory
""".strip(),
        encoding="utf-8",
    )

    try:
        fetch_resource_metadata_in_descriptor(
            descriptor=descriptor,
            resource_name="legacy-package",
            dry_run=True,
            log=lambda _message: None,
        )
    except ValueError as exc:
        assert "data-package-catalog" in str(exc)
        assert "packages:" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected legacy package-root descriptor validation failure")


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


def test_fetch_entity_metadata_fetches_all_packages_in_catalog(tmp_path: Path) -> None:
    """fetch_entity_metadata_in_descriptor with a DriveCatalog selector fetches each package."""
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(
        descriptor,
        catalogs=[
            {
                "name": "research",
                "packages": [
                    {
                        "name": "docs",
                        "path": "downloads/docs",
                        "syncTarget": "resources",
                        "sources": [
                            {
                                "path": "https://drive.google.com/drive/folders/docs-folder",
                                "serviceType": "GoogleDrive",
                                "entityType": "Directory",
                            }
                        ],
                    },
                    {
                        "name": "data",
                        "path": "downloads/data",
                        "syncTarget": "resources",
                        "sources": [
                            {
                                "path": "https://drive.google.com/drive/folders/data-folder",
                                "serviceType": "GoogleDrive",
                                "entityType": "Directory",
                            }
                        ],
                    },
                ],
                "catalogs": [],
            }
        ],
    )

    fetched_urls: list[str] = []

    class DummyDriveClient:
        def get_from_weburl(self, url: str):
            fetched_urls.append(url)

            class DummyItem:
                path = "report.csv"
                is_directory = False

                def to_dp(self):
                    from sharedrive.models import DriveResource, DriveSource
                    return DriveResource(
                        name="report.csv",
                        path="report.csv",
                        sources=[DriveSource(path=url + "/report.csv", serviceType="GoogleDrive", entityType="File")],
                    )

            class DummyFolder:
                @property
                def is_directory(self):
                    return True

                @property
                def children(self):
                    return [DummyItem()]

            return DummyFolder()

    summaries = fetch_entity_metadata_in_descriptor(
        descriptor=descriptor,
        entity_selector="research",
        dry_run=False,
        log=None,
        googledrive_client_factory=lambda: DummyDriveClient(),
    )

    assert len(summaries) == 2
    assert summaries[0].resource_name == "docs"
    assert summaries[0].generated_resources == 1
    assert summaries[0].changed is True
    assert summaries[1].resource_name == "data"
    assert summaries[1].generated_resources == 1
    assert summaries[1].changed is True

    assert fetched_urls == [
        "https://drive.google.com/drive/folders/docs-folder",
        "https://drive.google.com/drive/folders/data-folder",
    ]

    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
    catalog = document["catalogs"][0]
    assert catalog["packages"][0]["resources"][0]["name"] == "report.csv"
    assert catalog["packages"][1]["resources"][0]["name"] == "report.csv"


def test_fetch_entity_metadata_dry_run_does_not_write_catalog(tmp_path: Path) -> None:
    """Catalog fetch with dry_run=True does not modify the descriptor."""
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(
        descriptor,
        catalogs=[
            {
                "name": "research",
                "packages": [
                    {
                        "name": "docs",
                        "path": "downloads/docs",
                        "syncTarget": "resources",
                        "sources": [
                            {
                                "path": "https://drive.google.com/drive/folders/docs-folder",
                                "serviceType": "GoogleDrive",
                                "entityType": "Directory",
                            }
                        ],
                    }
                ],
                "catalogs": [],
            }
        ],
    )
    before = descriptor.read_text(encoding="utf-8")

    class DummyDriveClient:
        def get_from_weburl(self, _url: str):
            class DummyItem:
                path = "report.csv"
                is_directory = False

                def to_dp(self):
                    from sharedrive.models import DriveResource, DriveSource
                    return DriveResource(
                        name="report.csv",
                        path="report.csv",
                        sources=[DriveSource(path="https://example.com/report.csv", serviceType="GoogleDrive", entityType="File")],
                    )

            class DummyFolder:
                @property
                def is_directory(self):
                    return True

                @property
                def children(self):
                    return [DummyItem()]

            return DummyFolder()

    summaries = fetch_entity_metadata_in_descriptor(
        descriptor=descriptor,
        entity_selector="research",
        dry_run=True,
        log=None,
        googledrive_client_factory=lambda: DummyDriveClient(),
    )

    assert len(summaries) == 1
    assert summaries[0].dry_run is True
    assert summaries[0].changed is False
    assert descriptor.read_text(encoding="utf-8") == before


def test_fetch_entity_metadata_with_depth_recurses_sub_catalogs(tmp_path: Path) -> None:
    """depth=1 causes fetch to recurse one level into nested catalogs."""
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(
        descriptor,
        catalogs=[
            {
                "name": "research",
                "packages": [
                    {
                        "name": "top-docs",
                        "path": "downloads/top",
                        "syncTarget": "resources",
                        "sources": [
                            {
                                "path": "https://drive.google.com/drive/folders/top-folder",
                                "serviceType": "GoogleDrive",
                                "entityType": "Directory",
                            }
                        ],
                    }
                ],
                "catalogs": [
                    {
                        "name": "archive",
                        "packages": [
                            {
                                "name": "archive-docs",
                                "path": "downloads/archive",
                                "syncTarget": "resources",
                                "sources": [
                                    {
                                        "path": "https://drive.google.com/drive/folders/archive-folder",
                                        "serviceType": "GoogleDrive",
                                        "entityType": "Directory",
                                    }
                                ],
                            }
                        ],
                        "catalogs": [],
                    }
                ],
            }
        ],
    )

    fetched_urls: list[str] = []

    class DummyDriveClient:
        def get_from_weburl(self, url: str):
            fetched_urls.append(url)

            class DummyItem:
                path = "file.csv"
                is_directory = False

                def to_dp(self):
                    from sharedrive.models import DriveResource, DriveSource
                    return DriveResource(
                        name="file.csv",
                        path="file.csv",
                        sources=[DriveSource(path=url + "/file.csv", serviceType="GoogleDrive", entityType="File")],
                    )

            class DummyFolder:
                @property
                def is_directory(self):
                    return True

                @property
                def children(self):
                    return [DummyItem()]

            return DummyFolder()

    # depth=0 (default): only top-level package
    summaries_flat = fetch_entity_metadata_in_descriptor(
        descriptor=descriptor,
        entity_selector="research",
        dry_run=True,
        depth=0,
        log=None,
        googledrive_client_factory=lambda: DummyDriveClient(),
    )
    assert len(summaries_flat) == 1
    assert summaries_flat[0].resource_name == "top-docs"

    # depth=1: top-level package AND packages in direct sub-catalogs
    summaries_deep = fetch_entity_metadata_in_descriptor(
        descriptor=descriptor,
        entity_selector="research",
        dry_run=True,
        depth=1,
        log=None,
        googledrive_client_factory=lambda: DummyDriveClient(),
    )
    assert len(summaries_deep) == 2
    assert summaries_deep[0].resource_name == "top-docs"
    assert summaries_deep[1].resource_name == "archive-docs"


def test_fetch_entity_metadata_raises_for_standalone_resource(tmp_path: Path) -> None:
    """fetch_entity_metadata_in_descriptor raises ValueError for standalone DriveResource."""
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(
        descriptor,
        resources=[
            {
                "name": "my-file",
                "path": "downloads/file.csv",
                "sources": [
                    {
                        "path": "https://docs.google.com/spreadsheets/d/abc/edit",
                        "serviceType": "GoogleDrive",
                        "entityType": "File",
                    }
                ],
            }
        ],
    )

    try:
        fetch_entity_metadata_in_descriptor(
            descriptor=descriptor,
            entity_selector="my-file",
            log=None,
        )
    except ValueError as exc:
        assert "standalone resource" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for standalone resource")