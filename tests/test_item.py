from __future__ import annotations

from pathlib import Path

import pytest

from sharedrive.item import ServiceItem
from sharedrive.models import DriveRemoteCatalog, DriveRemoteResource


class _Item(ServiceItem):
    @classmethod
    def from_path(cls, path: str, **kwargs) -> ServiceItem:
        return cls(
            id=kwargs.get("id", path or "root"),
            name=kwargs.get("name", Path(path).name or "root"),
            path=path,
            source_url=kwargs.get("source_url", f"mock://{path}"),
            service_type=kwargs.get("service_type", "Mock"),
            is_directory=kwargs.get("is_directory", False),
            children=kwargs.get("children"),
        )

    def move(self, weburl: str):
        return

    def add_comment(self, body: str) -> "_Item":
        return self
    def __init__(
        self,
        *,
        id: str,
        name: str,
        path: str,
        source_url: str,
        service_type: str = "GoogleDrive",
        is_directory: bool = False,
        children: list[ServiceItem] | None = None,
    ) -> None:
        self._id = id
        self._name = name
        self._path = path
        self._source_url = source_url
        self._service_type = service_type
        self._is_directory = is_directory
        self._children = children or []
        self.downloaded_to: list[Path] = []
        self.refresh_calls: list[bool] = []

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
        return self._service_type

    @property
    def source_url(self) -> str:
        return self._source_url

    @property
    def is_directory(self) -> bool:
        return self._is_directory

    @property
    def children(self) -> list[ServiceItem]:
        return self._children

    def refresh(self, *, include_children: bool = True) -> ServiceItem:
        self.refresh_calls.append(include_children)
        return self

    def download(self, target: Path | str) -> None:
        if self.is_directory:
            super().download(target)
            return
        self.downloaded_to.append(Path(target))


def test_file_to_catalog_uses_remote_path_and_local_cache() -> None:
    item = _Item(
        id="file-1",
        name="Report.CSV",
        path="reports/Report.CSV",
        source_url="https://drive.google.com/file/d/file-1",
    )

    resource = item.to_catalog()

    assert isinstance(resource, DriveRemoteResource)
    assert resource.name == "reports/Report.CSV"
    assert str(resource.path) == "https://drive.google.com/file/d/file-1"
    assert resource.cache == "reports/Report.CSV"
    assert resource.serviceId == "file-1"
    assert resource.serviceType == "GoogleDrive"
    assert resource.entityType == "File"
    assert resource.format == "csv"


def test_service_item_from_path_contract_returns_runtime_item() -> None:
    item = _Item.from_path("reports/Report.CSV", source_url="mock://reports/Report.CSV")

    assert isinstance(item, ServiceItem)
    assert item.path == "reports/Report.CSV"
    assert item.name == "Report.CSV"


def test_file_to_catalog_leaves_format_empty_without_extension() -> None:
    item = _Item(
        id="file-1",
        name="README",
        path="README",
        source_url="s3://example-bucket/README",
        service_type="S3",
    )

    resource = item.to_catalog()

    assert isinstance(resource, DriveRemoteResource)
    assert resource.format is None


def test_directory_to_catalog_preserves_child_resources_and_catalogs() -> None:
    nested_file = _Item(
        id="nested-file",
        name="detail.parquet",
        path="archive/detail.parquet",
        source_url="s3://example-bucket/archive/detail.parquet",
        service_type="S3",
    )
    nested_folder = _Item(
        id="nested-folder",
        name="archive",
        path="archive",
        source_url="s3://example-bucket/archive/",
        service_type="S3",
        is_directory=True,
        children=[nested_file],
    )
    root_file = _Item(
        id="root-file",
        name="summary.csv",
        path="summary.csv",
        source_url="s3://example-bucket/summary.csv",
        service_type="S3",
    )
    root = _Item(
        id="root-folder",
        name="bucket",
        path="",
        source_url="s3://example-bucket",
        service_type="S3",
        is_directory=True,
        children=[nested_folder, root_file],
    )

    catalog = root.to_catalog()

    assert isinstance(catalog, DriveRemoteCatalog)
    assert catalog.name == ""
    assert str(catalog.accessUrl) == "s3://example-bucket"
    assert catalog.serviceId == "root-folder"
    assert catalog.serviceType == "S3"
    assert catalog.entityType == "Directory"
    assert [resource.name for resource in catalog.resources] == ["summary.csv"]
    assert [child.name for child in catalog.catalogs] == ["archive"]
    assert [resource.name for resource in catalog.catalogs[0].resources] == [
        "archive/detail.parquet"
    ]


def test_directory_download_writes_leaf_files_relative_to_target(
    tmp_path: Path,
) -> None:
    leaf = _Item(
        id="file-1",
        name="report.csv",
        path="reports/report.csv",
        source_url="https://drive.google.com/file/d/file-1",
    )
    root = _Item(
        id="folder-1",
        name="Research",
        path="research",
        source_url="https://drive.google.com/drive/folders/folder-1",
        is_directory=True,
        children=[leaf],
    )

    root.download(tmp_path)

    assert leaf.downloaded_to == [tmp_path / "reports" / "report.csv"]


def test_file_download_default_requires_subclass_override(tmp_path: Path) -> None:
    class _UndownloadableFile(_Item):
        def move(self, weburl: str):
            return
        def download(self, target: Path | str) -> None:
            ServiceItem.download(self, target)

    item = _UndownloadableFile(
        id="file-1",
        name="report.csv",
        path="report.csv",
        source_url="https://drive.google.com/file/d/file-1",
    )

    with pytest.raises(NotImplementedError, match="File download is not implemented"):
        item.download(tmp_path)


def test_get_path_returns_descendant_item() -> None:
    target = _Item(
        id="file-1",
        name="report.csv",
        path="reports/report.csv",
        source_url="mock://reports/report.csv",
    )
    reports = _Item(
        id="folder-1",
        name="reports",
        path="reports",
        source_url="mock://reports",
        is_directory=True,
        children=[target],
    )
    root = _Item(
        id="root",
        name="root",
        path="",
        source_url="mock://",
        is_directory=True,
        children=[reports],
    )

    assert root.get_path("reports/report.csv") is target


def test_get_path_raises_when_segment_missing() -> None:
    root = _Item(
        id="root",
        name="root",
        path="",
        source_url="mock://",
        is_directory=True,
        children=[],
    )

    with pytest.raises(FileNotFoundError, match="missing"):
        root.get_path("missing")


def test_get_path_returns_default_when_missing() -> None:
    root = _Item(
        id="root",
        name="root",
        path="",
        source_url="mock://",
        is_directory=True,
        children=[],
    )

    assert root.get_path("missing", default=None) is None


def test_glob_returns_iterator_of_matching_descendants() -> None:
    nested_csv = _Item(
        id="file-1",
        name="report.csv",
        path="reports/report.csv",
        source_url="mock://reports/report.csv",
    )
    nested_txt = _Item(
        id="file-2",
        name="report.txt",
        path="reports/report.txt",
        source_url="mock://reports/report.txt",
    )
    top_csv = _Item(
        id="file-3",
        name="summary.csv",
        path="summary.csv",
        source_url="mock://summary.csv",
    )
    reports = _Item(
        id="folder-1",
        name="reports",
        path="reports",
        source_url="mock://reports",
        is_directory=True,
        children=[nested_csv, nested_txt],
    )
    root = _Item(
        id="root",
        name="root",
        path="",
        source_url="mock://",
        is_directory=True,
        children=[reports, top_csv],
    )

    flat_matches = root.glob("*.csv")
    assert iter(flat_matches) is flat_matches
    assert list(flat_matches) == [top_csv]
    assert list(root.glob("reports/*.csv")) == [nested_csv]
    assert list(root.glob("**/*.csv")) == [nested_csv, top_csv]


def test_glob_accepts_path_pattern_and_current_directory_pattern() -> None:
    child = _Item(
        id="folder-1",
        name="reports",
        path="reports",
        source_url="mock://reports",
        is_directory=True,
        children=[],
    )
    root = _Item(
        id="root",
        name="root",
        path="",
        source_url="mock://",
        is_directory=True,
        children=[child],
    )

    assert list(root.glob(Path("reports"))) == [child]
    assert list(root.glob(".")) == [root]
