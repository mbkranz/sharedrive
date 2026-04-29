from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import yaml

from sharedrive.actions.download import check_auth, download
from sharedrive.actions.fetch import fetch
from sharedrive.clients.googledrive import GDriveItem
from sharedrive.clients.sharepoint import SharepointItem
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


def _make_fake_provider(googledrive_factory=None, sharepoint_factory=None):
    """Return a fake ``get_provider`` callable for use with monkeypatch.

    The returned function maps adapter names to minimal stub classes whose
    ``build_default()`` returns the object produced by the corresponding
    factory, and whose ``check_auth()`` calls the factory (so a raising factory
    doubles as a failing auth check).
    """
    from sharedrive.registry import get_provider as _real

    def fake_get_provider(name):
        if name == "googledrive" and googledrive_factory is not None:

            class _FakeGDrive:
                @classmethod
                def build_default(cls):
                    return googledrive_factory()

                @classmethod
                def check_auth(cls):
                    googledrive_factory()

            return _FakeGDrive

        if name == "sharepoint" and sharepoint_factory is not None:

            class _FakeSP:
                @classmethod
                def build_default(cls):
                    return sharepoint_factory()

                @classmethod
                def check_auth(cls):
                    sharepoint_factory()

            return _FakeSP

        return _real(name)

    return fake_get_provider


def _make_fake_get_client(googledrive_factory=None, sharepoint_factory=None):
    """Return a fake ``get_client`` callable for use with monkeypatch.

    Unlike :func:`_make_fake_provider`, the returned function maps adapter
    names directly to *instances* (the return value of the factory), matching
    the signature of :func:`~sharedrive.registry.get_client`.
    """
    from sharedrive.registry import get_client as _real

    def fake_get_client(name):
        if name == "googledrive" and googledrive_factory is not None:
            return googledrive_factory()
        if name == "sharepoint" and sharepoint_factory is not None:
            return sharepoint_factory()
        return _real(name)

    return fake_get_client


def _patch_fetch_registry(
    monkeypatch: pytest.MonkeyPatch,
    *,
    googledrive_factory=None,
    sharepoint_factory=None,
) -> None:
    """Patch ``get_client`` inside fetch.py for unit tests."""
    fake = _make_fake_get_client(
        googledrive_factory=googledrive_factory, sharepoint_factory=sharepoint_factory
    )
    fetch_module = importlib.import_module("sharedrive.actions.fetch")
    monkeypatch.setattr(fetch_module, "get_client", fake)


def _patch_download_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    googledrive_factory=None,
    sharepoint_factory=None,
) -> None:
    """Patch ``get_provider`` and ``get_client`` inside download.py for unit tests."""
    fake_provider = _make_fake_provider(
        googledrive_factory=googledrive_factory, sharepoint_factory=sharepoint_factory
    )
    fake_client = _make_fake_get_client(
        googledrive_factory=googledrive_factory, sharepoint_factory=sharepoint_factory
    )
    download_module = importlib.import_module("sharedrive.actions.download")
    monkeypatch.setattr(download_module, "get_provider", fake_provider)
    monkeypatch.setattr(download_module, "get_client", fake_client)


class _DriveStub(DriveItem):
    """Minimal :class:`~sharedrive.item.DriveItem` stub for fetch action tests.

    Subclasses override only the class variables or properties they need;
    everything else defaults to safe no-op values.  ``refresh()`` returns
    *self* so that :meth:`~sharedrive.item.DriveItem.refresh_tree` and
    ``_build_child_resources`` work without touching the network.
    """

    _item_id: str = "stub-id"
    _name: str = "stub"
    _path: str = ""
    _service_type: str = "stub"
    _source_url: str = ""
    _is_directory: bool = False

    @property
    def id(self) -> str:
        return self._item_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def path(self) -> str:
        return self._path

    @property
    def service_type(self) -> str:
        return self._service_type

    @property
    def source_url(self) -> str:
        return self._source_url

    @property
    def is_directory(self) -> bool:
        return self._is_directory

    def refresh(self, *, include_children: bool = True) -> "_DriveStub":
        return self

    def download(self, target: Path | str) -> None:
        raise NotImplementedError


def _fetch_one(descriptor: Path, selector: str, **kwargs):
    summaries = fetch(descriptor, selector, **kwargs)
    assert len(summaries) == 1
    return summaries[0]


def test_drive_file_refresh_returns_self() -> None:
    class DummyFile(DriveFile):
        def __init__(
            self, *, item_id: str, name: str, path: str, source_url: str
        ) -> None:
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
        def __init__(
            self, *, item_id: str, name: str, path: str, source_url: str
        ) -> None:
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
        def __init__(
            self,
            *,
            item_id: str,
            name: str,
            path: str,
            children: list[DriveFile | DriveFolder],
        ) -> None:
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
    assert folder.children == [nested_folder, summary_file]


def test_drive_folder_refresh_tree_refreshes_descendants() -> None:
    class DummyFile(DriveFile):
        def __init__(
            self,
            *,
            item_id: str,
            name: str,
            path: str,
            source_url: str,
            calls: list[str],
        ) -> None:
            self._id = item_id
            self._name = name
            self._path = path
            self._source_url = source_url
            self._calls = calls

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
            self._calls.append(f"file:{self.path}")
            return self

    class DummyFolder(DriveFolder):
        def __init__(
            self,
            *,
            item_id: str,
            name: str,
            path: str,
            children: list[DriveFile | DriveFolder],
            calls: list[str],
        ) -> None:
            self._id = item_id
            self._name = name
            self._path = path
            self._children = children
            self._calls = calls

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
            self._calls.append(f"folder:{self.path}")
            return self

    calls: list[str] = []
    folder = DummyFolder(
        item_id="folder-1",
        name="folder",
        path="folder",
        calls=calls,
        children=[
            DummyFolder(
                item_id="folder-2",
                name="nested",
                path="nested",
                calls=calls,
                children=[
                    DummyFile(
                        item_id="file-2",
                        name="detail.csv",
                        path="nested/detail.csv",
                        source_url="https://example.invalid/detail.csv",
                        calls=calls,
                    )
                ],
            ),
            DummyFile(
                item_id="file-1",
                name="summary.csv",
                path="summary.csv",
                source_url="https://example.invalid/summary.csv",
                calls=calls,
            ),
        ],
    )

    refreshed = folder.refresh_tree()

    assert refreshed is folder
    assert calls == [
        "folder:folder",
        "folder:nested",
        "file:nested/detail.csv",
        "file:summary.csv",
    ]


def test_fetch_build_child_resources_flattens_runtime_items() -> None:
    class DummyFile(DriveFile):
        def __init__(
            self, *, item_id: str, name: str, path: str, source_url: str
        ) -> None:
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
        def __init__(
            self,
            *,
            item_id: str,
            name: str,
            path: str,
            children: list[DriveFile | DriveFolder],
        ) -> None:
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

        def _to_item(
            self,
            raw_metadata: dict,
            *,
            current_rel_path: str = "",
            scope_root: bool = False,
        ):
            return GDriveItem(
                raw_metadata=raw_metadata,
                client=self,
                current_rel_path=current_rel_path,
                scope_root=scope_root,
            )

    client = DummyClient()
    item = GDriveItem(
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

    assert isinstance(refreshed, GDriveItem)
    assert not refreshed.is_directory
    assert refreshed is item
    assert refreshed.name == "renamed.csv"
    assert refreshed.path == "nested/renamed.csv"
    assert client.calls == [("file-1", "id,name,mimeType,parents,webViewLink")]


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

        def _to_item(
            self,
            raw_metadata: dict,
            *,
            current_rel_path: str = "",
            scope_root: bool = False,
        ):
            return GDriveItem(
                raw_metadata=raw_metadata,
                client=self,
                current_rel_path=current_rel_path,
                scope_root=scope_root,
            )

    client = DummyClient()
    item = GDriveItem(
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
    assert refreshed.is_directory
    children = item.children
    assert len(children) == 1
    assert isinstance(children[0], GDriveItem)
    assert not children[0].is_directory
    assert children[0].path == "folder/report.csv"
    assert client.get_calls == [("folder-1", "id,name,mimeType,parents,webViewLink")]
    assert client.list_calls == [("folder-1", False)]


def test_sharepoint_file_refresh_refreshes_metadata() -> None:
    class DummyClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def get_item_metadata(
            self, drive: str, *, item_path=None, item_id=None, fields=None
        ):
            self.calls.append((drive, item_id))
            return {
                "id": item_id,
                "name": "renamed.csv",
                "file": {},
                "parentReference": {"driveId": drive},
                "webUrl": "https://example.invalid/refreshed",
                "relative_path": "nested/renamed.csv",
            }

        def _to_item(
            self,
            raw_metadata: dict,
            *,
            current_rel_path: str = "",
            scope_root: bool = False,
        ):
            return SharepointItem(
                raw_metadata=raw_metadata,
                client=self,
                current_rel_path=current_rel_path,
                scope_root=scope_root,
            )

    client = DummyClient()
    item = SharepointItem(
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

    assert isinstance(refreshed, SharepointItem)
    assert not refreshed.is_directory
    assert refreshed is item
    assert refreshed.name == "renamed.csv"
    assert refreshed.path == "nested/renamed.csv"
    assert client.calls == [("drive-1", "file-1")]


def test_sharepoint_folder_refresh_refreshes_children() -> None:
    class DummyClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def get_item_metadata(
            self, drive: str, *, item_path=None, item_id=None, fields=None
        ):
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

        def _to_item(
            self,
            raw_metadata: dict,
            *,
            current_rel_path: str = "",
            scope_root: bool = False,
        ):
            return SharepointItem(
                raw_metadata=raw_metadata,
                client=self,
                current_rel_path=current_rel_path,
                scope_root=scope_root,
            )

    client = DummyClient()
    item = SharepointItem(
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
    assert refreshed.is_directory
    children = item.children
    assert len(children) == 1
    assert isinstance(children[0], SharepointItem)
    assert not children[0].is_directory
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


def test_check_auth_limits_checks_to_selected_adapters(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    calls: list[str] = []

    def sharepoint_factory():
        calls.append("sharepoint")
        return object()

    _patch_download_client(monkeypatch, sharepoint_factory=sharepoint_factory)

    results = check_auth(descriptor, selector=["sharepoint"])

    assert calls == ["sharepoint"]
    assert [result.adapter for result in results] == ["sharepoint"]
    assert results[0].ok is True


def test_fetch_from_descriptor_check_auth_stops_before_download_on_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    messages: list[str] = []

    def failing_sharepoint_factory():
        raise RuntimeError("missing Azure tenant")

    _patch_download_client(monkeypatch, sharepoint_factory=failing_sharepoint_factory)

    summary = download(
        descriptor,
        selector=["sharepoint"],
        output_dir=tmp_path / "resources",
        dry_run=False,
        check_auth=True,
        log=messages.append,
    )

    assert summary.ok is False
    assert summary.failures == 1
    assert summary.downloaded == 0
    assert any("Auth check failed for sharepoint" in message for message in messages)
    assert not (tmp_path / "resources" / "downloads" / "spec.xlsx").exists()


def test_fetch_from_descriptor_check_auth_allows_download_when_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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

    _patch_download_client(monkeypatch, googledrive_factory=lambda: client)

    summary = download(
        descriptor,
        selector=["googledrive"],
        output_dir=tmp_path / "resources",
        dry_run=False,
        check_auth=True,
        log=lambda _message: None,
    )

    output_path = tmp_path / "resources" / "downloads" / "export.csv"
    assert summary.ok is True
    assert summary.downloaded == 1
    assert client.calls == [
        ("https://docs.google.com/spreadsheets/d/test-sheet/edit", str(output_path))
    ]
    assert output_path.read_text(encoding="utf-8") == "ok"


def test_fetch_from_descriptor_materializes_google_drive_directory_resources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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

    _patch_download_client(monkeypatch, googledrive_factory=lambda: client)

    summary = download(
        descriptor,
        selector=["googledrive"],
        output_dir=tmp_path / "resources",
        dry_run=False,
        log=lambda _message: None,
    )

    summary_path = tmp_path / "resources" / "downloads" / "census" / "summary.csv"
    detail_path = (
        tmp_path / "resources" / "downloads" / "census" / "nested" / "detail.csv"
    )
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


def test_fetch_from_descriptor_materializes_google_drive_directory_path_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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

    _patch_download_client(monkeypatch, googledrive_factory=lambda: client)

    summary = download(
        descriptor,
        selector=["googledrive"],
        output_dir=tmp_path / "resources",
        dry_run=False,
        log=lambda _message: None,
    )

    assert summary.ok is True
    assert summary.downloaded == 2
    assert client.download_calls == [
        (
            "file-1",
            str(
                tmp_path
                / "resources"
                / "downloads"
                / "term-proposal-documents"
                / "summary.csv"
            ),
        ),
        (
            "file-2",
            str(
                tmp_path
                / "resources"
                / "downloads"
                / "term-proposal-documents"
                / "nested"
                / "detail.csv"
            ),
        ),
    ]


def test_fetch_from_descriptor_fetches_nested_package_resources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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

    _patch_download_client(monkeypatch, googledrive_factory=lambda: client)

    summary = download(
        descriptor,
        selector=["selected-export"],
        output_dir=tmp_path / "resources",
        dry_run=False,
        log=lambda _message: None,
    )

    output_path = tmp_path / "resources" / "downloads" / "analytics" / "export.csv"
    assert summary.ok is True
    assert summary.downloaded == 1
    assert client.calls == [
        ("https://docs.google.com/spreadsheets/d/test-sheet/edit", str(output_path))
    ]
    assert output_path.read_text(encoding="utf-8") == "nested-ok"


def test_fetch_from_descriptor_matches_nested_dot_path_include(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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

    _patch_download_client(monkeypatch, googledrive_factory=lambda: client)

    summary = download(
        descriptor,
        selector=["analytics-docs.selected-export"],
        output_dir=tmp_path / "resources",
        dry_run=False,
        log=lambda _message: None,
    )

    output_path = tmp_path / "resources" / "downloads" / "analytics" / "export.csv"
    assert summary.ok is True
    assert summary.downloaded == 1
    assert client.calls == [
        ("https://docs.google.com/spreadsheets/d/test-sheet/edit", str(output_path))
    ]


def test_fetch_from_descriptor_matches_top_level_package_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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

    _patch_download_client(monkeypatch, googledrive_factory=lambda: client)

    summary = download(
        descriptor,
        selector=["analytics-docs"],
        output_dir=tmp_path / "resources",
        dry_run=False,
        log=lambda _message: None,
    )

    output_path = tmp_path / "resources" / "downloads" / "analytics" / "export.csv"
    assert summary.ok is True
    assert summary.downloaded == 1
    assert client.calls == [
        ("https://docs.google.com/spreadsheets/d/test-sheet/edit", str(output_path))
    ]


def test_download_matches_nested_catalog_package_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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

    _patch_download_client(monkeypatch, googledrive_factory=lambda: client)

    summary = download(
        descriptor,
        selector=["research.archive.analytics-docs"],
        output_dir=tmp_path / "resources",
        dry_run=False,
        log=lambda _message: None,
    )

    output_path = tmp_path / "resources" / "downloads" / "analytics" / "export.csv"
    assert summary.ok is True
    assert summary.downloaded == 1
    assert client.calls == [
        ("https://docs.google.com/spreadsheets/d/test-sheet/edit", str(output_path))
    ]


def test_download_selecting_catalog_includes_nested_package_resources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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

    _patch_download_client(monkeypatch, googledrive_factory=lambda: client)

    summary = download(
        descriptor,
        selector=["research"],
        output_dir=tmp_path / "resources",
        dry_run=False,
        log=lambda _message: None,
    )

    output_path = tmp_path / "resources" / "downloads" / "analytics" / "export.csv"
    assert summary.ok is True
    assert summary.downloaded == 1
    assert client.calls == [
        ("https://docs.google.com/spreadsheets/d/test-sheet/edit", str(output_path))
    ]


def test_fetch_supports_sharepoint_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
            assert (
                url
                == "https://example.sharepoint.com/sites/Test/Shared%20Documents/specs"
            )

            class DummyItem1(_DriveStub):
                _item_id = "1"
                _name = "spec.xlsx"
                _path = "spec.xlsx"
                _is_directory = False
                _service_type = "SharePoint"
                _source_url = "https://example.sharepoint.com/sites/Test/Shared%20Documents/specs/spec.xlsx"

                def to_resource(self):
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

            class DummyItem2(_DriveStub):
                _item_id = "2"
                _name = "detail.csv"
                _path = "nested/detail.csv"
                _is_directory = False
                _service_type = "SharePoint"
                _source_url = "https://example.sharepoint.com/sites/Test/Shared%20Documents/specs/nested/detail.csv"

                def to_resource(self):
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

            class DummyFolder(_DriveStub):
                _is_directory = True

                @property
                def children(self):
                    return [DummyItem1(), DummyItem2()]

            return DummyFolder()

    _patch_fetch_registry(
        monkeypatch, sharepoint_factory=lambda: DummySharepointClient()
    )

    summary = _fetch_one(
        descriptor=descriptor,
        selector="shared-specs",
        dry_run=False,
        log=lambda _message: None,
    )

    assert summary.changed is True
    assert summary.generated_resources == 2

    document = descriptor.read_text(encoding="utf-8")
    assert "nested/detail.csv" in document
    assert "serviceType: SharePoint" in document


def test_fetch_resolves_nested_catalog_package_selector(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
            class DummyItem(_DriveStub):
                _path = "spec.xlsx"
                _name = "spec.xlsx"
                _is_directory = False
                _service_type = "SharePoint"

                def to_resource(self):
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

            class DummyFolder(_DriveStub):
                _is_directory = True

                @property
                def children(self):
                    return [DummyItem()]

            return DummyFolder()

    _patch_fetch_registry(
        monkeypatch, sharepoint_factory=lambda: DummySharepointClient()
    )

    summary = _fetch_one(
        descriptor=descriptor,
        selector="research.archive.shared-specs",
        dry_run=False,
        log=lambda _message: None,
    )

    assert summary.changed is True
    assert summary.resource_name == "shared-specs"
    assert "spec.xlsx" in descriptor.read_text(encoding="utf-8")


def test_fetch_rejects_legacy_package_root_descriptor(tmp_path: Path) -> None:
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
        _fetch_one(
            descriptor=descriptor,
            selector="legacy-package",
            dry_run=True,
            log=lambda _message: None,
        )
    except ValueError as exc:
        assert "data-package-catalog" in str(exc)
        assert "packages:" in str(exc)
    else:  # pragma: no cover
        raise AssertionError(
            "Expected legacy package-root descriptor validation failure"
        )


def test_download_requires_existing_descriptor(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"

    try:
        download(missing, output_dir=tmp_path / "resources")
    except FileNotFoundError as exc:
        assert "does not exist" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected FileNotFoundError for missing descriptor")


def test_check_auth_requires_existing_descriptor(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"

    try:
        check_auth(missing)
    except FileNotFoundError as exc:
        assert "does not exist" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected FileNotFoundError for missing descriptor")


def test_fetch_fetches_all_packages_in_catalog(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """fetch with a DriveCatalog selector fetches each package."""
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

            class DummyItem(_DriveStub):
                _path = "report.csv"
                _name = "report.csv"
                _is_directory = False
                _service_type = "GoogleDrive"

                def to_resource(self):
                    from sharedrive.models import DriveResource, DriveSource

                    return DriveResource(
                        name="report.csv",
                        path="report.csv",
                        sources=[
                            DriveSource(
                                path=url + "/report.csv",
                                serviceType="GoogleDrive",
                                entityType="File",
                            )
                        ],
                    )

            class DummyFolder(_DriveStub):
                _is_directory = True

                @property
                def children(self):
                    return [DummyItem()]

            return DummyFolder()

    _patch_fetch_registry(monkeypatch, googledrive_factory=lambda: DummyDriveClient())

    summaries = fetch(
        descriptor=descriptor, selector="research", dry_run=False, log=None
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


def test_fetch_dry_run_does_not_write_catalog(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
            class DummyItem(_DriveStub):
                _path = "report.csv"
                _name = "report.csv"
                _is_directory = False
                _service_type = "GoogleDrive"

                def to_resource(self):
                    from sharedrive.models import DriveResource, DriveSource

                    return DriveResource(
                        name="report.csv",
                        path="report.csv",
                        sources=[
                            DriveSource(
                                path="https://example.com/report.csv",
                                serviceType="GoogleDrive",
                                entityType="File",
                            )
                        ],
                    )

            class DummyFolder(_DriveStub):
                _is_directory = True

                @property
                def children(self):
                    return [DummyItem()]

            return DummyFolder()

    _patch_fetch_registry(monkeypatch, googledrive_factory=lambda: DummyDriveClient())

    summaries = fetch(
        descriptor=descriptor, selector="research", dry_run=True, log=None
    )

    assert len(summaries) == 1
    assert summaries[0].dry_run is True
    assert summaries[0].changed is False
    assert descriptor.read_text(encoding="utf-8") == before


def test_fetch_fetches_source_backed_catalog_children(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(
        descriptor,
        catalogs=[
            {
                "name": "research",
                "sources": [
                    {
                        "path": "https://drive.google.com/drive/folders/research-folder",
                        "serviceType": "GoogleDrive",
                        "entityType": "Directory",
                    }
                ],
                "resources": [{"name": "stale-resource", "path": "stale.csv"}],
                "packages": [
                    {
                        "name": "stale-package",
                        "path": "downloads/stale",
                        "syncTarget": "resources",
                    }
                ],
                "catalogs": [{"name": "stale-catalog"}],
            }
        ],
    )

    class DummyDriveClient:
        def get_from_weburl(self, url: str):
            assert url == "https://drive.google.com/drive/folders/research-folder"

            class DummyFile:
                name = "report.csv"
                path = "report.csv"
                is_directory = False
                service_type = "GoogleDrive"
                source_url = "https://drive.google.com/open?id=report"

                def to_resource(self):
                    from sharedrive.models import DriveResource, DriveSource

                    return DriveResource(
                        name="report.csv",
                        path="report.csv",
                        sources=[
                            DriveSource(
                                path=self.source_url,
                                serviceType="GoogleDrive",
                                entityType="File",
                            )
                        ],
                    )

            class DummyFolder:
                name = "archive"
                path = "archive"
                is_directory = True
                service_type = "GoogleDrive"
                source_url = "https://drive.google.com/drive/folders/archive-folder"
                children: list[object] = []

            class DummyRootFolder(_DriveStub):
                _is_directory = True

                @property
                def children(self):
                    return [DummyFolder(), DummyFile()]

            return DummyRootFolder()

    _patch_fetch_registry(monkeypatch, googledrive_factory=lambda: DummyDriveClient())

    summaries = fetch(
        descriptor=descriptor, selector="research", dry_run=False, log=None
    )

    assert len(summaries) == 1
    assert summaries[0].resource_name == "research"
    assert summaries[0].generated_resources == 2

    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
    catalog = document["catalogs"][0]
    assert [resource["name"] for resource in catalog["resources"]] == ["report.csv"]
    assert [sub_catalog["name"] for sub_catalog in catalog["catalogs"]] == ["archive"]
    assert catalog["catalogs"][0]["sources"][0]["path"] == (
        "https://drive.google.com/drive/folders/archive-folder"
    )
    assert not catalog.get("packages")


def test_fetch_from_root_fetches_immediate_source_backed_catalogs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(
        descriptor,
        catalogs=[
            {
                "name": "research",
                "sources": [
                    {
                        "path": "https://drive.google.com/drive/folders/research-folder",
                        "serviceType": "GoogleDrive",
                        "entityType": "Directory",
                    }
                ],
                "resources": [],
                "catalogs": [],
            }
        ],
    )

    class DummyDriveClient:
        def get_from_weburl(self, url: str):
            assert url == "https://drive.google.com/drive/folders/research-folder"

            class DummyFile:
                name = "report.csv"
                path = "report.csv"
                is_directory = False
                service_type = "GoogleDrive"
                source_url = "https://drive.google.com/open?id=report"

                def to_resource(self):
                    from sharedrive.models import DriveResource, DriveSource

                    return DriveResource(
                        name="report.csv",
                        path="report.csv",
                        sources=[
                            DriveSource(
                                path=self.source_url,
                                serviceType="GoogleDrive",
                                entityType="File",
                            )
                        ],
                    )

            class DummyRootFolder(_DriveStub):
                _is_directory = True

                @property
                def children(self):
                    return [DummyFile()]

            return DummyRootFolder()

    _patch_fetch_registry(monkeypatch, googledrive_factory=lambda: DummyDriveClient())

    summaries = fetch(descriptor=descriptor, selector=None, dry_run=False, log=None)

    assert len(summaries) == 1
    assert summaries[0].resource_name == "research"

    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
    assert document["catalogs"][0]["resources"][0]["name"] == "report.csv"


def test_fetch_with_depth_recurses_sub_catalogs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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

            class DummyItem(_DriveStub):
                _path = "file.csv"
                _name = "file.csv"
                _is_directory = False
                _service_type = "GoogleDrive"

                def to_resource(self):
                    from sharedrive.models import DriveResource, DriveSource

                    return DriveResource(
                        name="file.csv",
                        path="file.csv",
                        sources=[
                            DriveSource(
                                path=url + "/file.csv",
                                serviceType="GoogleDrive",
                                entityType="File",
                            )
                        ],
                    )

            class DummyFolder(_DriveStub):
                _is_directory = True

                @property
                def children(self):
                    return [DummyItem()]

            return DummyFolder()

    # depth=0 (default): only top-level package
    _patch_fetch_registry(monkeypatch, googledrive_factory=lambda: DummyDriveClient())

    summaries_flat = fetch(
        descriptor=descriptor, selector="research", dry_run=True, depth=0, log=None
    )
    assert len(summaries_flat) == 1
    assert summaries_flat[0].resource_name == "top-docs"

    # depth=1: top-level package AND packages in direct sub-catalogs
    summaries_deep = fetch(
        descriptor=descriptor, selector="research", dry_run=True, depth=1, log=None
    )
    assert len(summaries_deep) == 2
    assert summaries_deep[0].resource_name == "top-docs"
    assert summaries_deep[1].resource_name == "archive-docs"


def test_fetch_raises_for_standalone_resource(tmp_path: Path) -> None:
    """fetch raises ValueError for standalone DriveResource."""
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
        fetch(descriptor=descriptor, selector="my-file", log=None)
    except ValueError as exc:
        assert "standalone resource" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for standalone resource")


def test_download_multiple_file_sources_uses_source_key_directories(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(
        descriptor,
        resources=[
            {
                "name": "combined",
                "path": "downloads/combined",
                "sources": [
                    {
                        "title": "First Source",
                        "path": "https://drive.google.com/files/a.csv",
                        "serviceType": "GoogleDrive",
                        "entityType": "File",
                    },
                    {
                        "title": "Second Source",
                        "path": "https://drive.google.com/files/b.csv",
                        "serviceType": "GoogleDrive",
                        "entityType": "File",
                    },
                ],
            }
        ],
    )

    class DummyDriveClient:
        def get_from_weburl(self, url: str):
            class DummyFile:
                @property
                def is_directory(self) -> bool:
                    return False

                def download(self, target_path: str) -> None:
                    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(target_path).write_text(url, encoding="utf-8")

            return DummyFile()

    _patch_download_client(monkeypatch, googledrive_factory=lambda: DummyDriveClient())

    summary = download(descriptor, output_dir=tmp_path / "resources", log=None)

    assert summary.ok
    assert summary.downloaded == 2
    assert (
        tmp_path / "resources" / "downloads" / "combined" / "first-source" / "a.csv"
    ).read_text(encoding="utf-8") == "https://drive.google.com/files/a.csv"
    assert (
        tmp_path / "resources" / "downloads" / "combined" / "second-source" / "b.csv"
    ).read_text(encoding="utf-8") == "https://drive.google.com/files/b.csv"


def test_download_source_target_override_and_collision(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(
        descriptor,
        resources=[
            {
                "name": "combined",
                "path": "downloads/combined",
                "sources": [
                    {
                        "path": "https://drive.google.com/files/a.csv",
                        "serviceType": "GoogleDrive",
                        "entityType": "File",
                        "target": "custom/a.csv",
                    },
                    {
                        "path": "https://drive.google.com/files/b.csv",
                        "serviceType": "GoogleDrive",
                        "entityType": "File",
                        "target": "custom/b.csv",
                    },
                ],
            }
        ],
    )

    class DummyDriveClient:
        def get_from_weburl(self, url: str):
            class DummyFile:
                @property
                def is_directory(self) -> bool:
                    return False

                def download(self, target_path: str) -> None:
                    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(target_path).write_text(url, encoding="utf-8")

            return DummyFile()

    _patch_download_client(monkeypatch, googledrive_factory=lambda: DummyDriveClient())

    summary = download(descriptor, output_dir=tmp_path / "resources", log=None)

    assert summary.ok
    assert (tmp_path / "resources" / "custom" / "a.csv").exists()
    assert (tmp_path / "resources" / "custom" / "b.csv").exists()

    collision_descriptor = tmp_path / "collision.yaml"
    _write_catalog_descriptor(
        collision_descriptor,
        resources=[
            {
                "name": "combined",
                "path": "downloads/combined",
                "sources": [
                    {
                        "path": "https://drive.google.com/files/a.csv",
                        "serviceType": "GoogleDrive",
                        "entityType": "File",
                        "target": "custom/same.csv",
                    },
                    {
                        "path": "https://drive.google.com/files/b.csv",
                        "serviceType": "GoogleDrive",
                        "entityType": "File",
                        "target": "custom/same.csv",
                    },
                ],
            }
        ],
    )

    with pytest.raises(ValueError, match="Output collision"):
        download(collision_descriptor, output_dir=tmp_path / "resources", log=None)


def test_fetch_multiple_directory_sources_namespaces_generated_resources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(
        descriptor,
        packages=[
            {
                "name": "docs",
                "path": "downloads/docs",
                "syncTarget": "resources",
                "sources": [
                    {
                        "title": "First Source",
                        "path": "https://drive.google.com/drive/folders/first",
                        "serviceType": "GoogleDrive",
                        "entityType": "Directory",
                    },
                    {
                        "title": "Second Source",
                        "path": "https://drive.google.com/drive/folders/second",
                        "serviceType": "GoogleDrive",
                        "entityType": "Directory",
                    },
                ],
            }
        ],
    )

    class DummyDriveClient:
        def get_from_weburl(self, url: str):
            class DummyItem(_DriveStub):
                _path = "report.csv"
                _name = "report.csv"
                _is_directory = False
                _service_type = "GoogleDrive"

                def to_resource(self):
                    from sharedrive.models import DriveResource, DriveSource

                    return DriveResource(
                        name="report.csv",
                        path="report.csv",
                        sources=[
                            DriveSource(
                                path=f"{url}/report.csv",
                                serviceType="GoogleDrive",
                                entityType="File",
                            )
                        ],
                    )

            class DummyFolder(_DriveStub):
                _is_directory = True

                @property
                def children(self):
                    return [DummyItem()]

            return DummyFolder()

    _patch_fetch_registry(monkeypatch, googledrive_factory=lambda: DummyDriveClient())

    summaries = fetch(descriptor, "docs", log=None)
    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))

    assert summaries[0].generated_resources == 2
    assert [item["path"] for item in document["packages"][0]["resources"]] == [
        "first-source/report.csv",
        "second-source/report.csv",
    ]


def test_check_auth_dedupes_adapters_across_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(
        descriptor,
        resources=[
            {
                "name": "combined",
                "path": "downloads/combined",
                "sources": [
                    {
                        "path": "https://drive.google.com/files/a.csv",
                        "serviceType": "GoogleDrive",
                        "entityType": "File",
                    },
                    {
                        "path": "https://drive.google.com/files/b.csv",
                        "serviceType": "GoogleDrive",
                        "entityType": "File",
                    },
                ],
            }
        ],
    )
    calls: list[str] = []

    def googledrive_factory():
        calls.append("googledrive")
        return object()

    _patch_download_client(monkeypatch, googledrive_factory=googledrive_factory)

    results = check_auth(descriptor)

    assert [result.adapter for result in results] == ["googledrive"]
    assert calls == ["googledrive"]
