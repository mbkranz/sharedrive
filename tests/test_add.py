from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sharedrive.commands.descriptor import _add_resource_to_descriptor
from sharedrive.models import infer_service_type


def _write_catalog_descriptor(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {"$schema": "data-package-catalog", "resources": [], "catalogs": []},
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_add_resource_to_descriptor_writes_path_cache_and_service_type(
    tmp_path: Path,
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(descriptor)

    resource = _add_resource_to_descriptor(
        descriptor,
        name="source-export",
        path="s3://my-bucket/path/to/source-export.csv",
        cache="background/exports/source-export.csv",
        title="Source export",
        description="Exported source data",
    )

    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))

    assert document["$schema"] == "data-package-catalog"
    assert resource["path"] == "s3://my-bucket/path/to/source-export.csv"
    assert resource["_cache"] == "background/exports/source-export.csv"
    assert document["resources"][0]["serviceType"] == "S3"
    assert document["resources"][0]["entityType"] == "File"
    assert "sources" not in document["resources"][0]


def test_add_resource_to_descriptor_rejects_duplicate_names(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(descriptor)
    _add_resource_to_descriptor(
        descriptor,
        name="source-export",
        path="s3://bucket/existing.csv",
        cache="existing.csv",
    )

    with pytest.raises(ValueError, match="already exists"):
        _add_resource_to_descriptor(
            descriptor,
            name="source-export",
            path="s3://my-bucket/path/to/source-export.csv",
            cache="background/exports/source-export.csv",
        )


def test_add_resource_to_descriptor_rejects_unsupported_service_type(
    tmp_path: Path,
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(descriptor)

    with pytest.raises(NotImplementedError, match="not implemented"):
        _add_resource_to_descriptor(
            descriptor,
            name="local-file",
            path="https://example.com/files/local-file.txt",
            cache="background/local-file.txt",
            service_type="OneDrive",
        )


def test_add_resource_to_descriptor_creates_access_url_catalog(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(descriptor)

    catalog = _add_resource_to_descriptor(
        descriptor,
        name="census-docs",
        access_url="https://drive.google.com/drive/folders/folder123",
        service_type="GoogleDrive",
        entity_type="Directory",
        catalog=True,
        profile="data-package-catalog",
    )

    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))

    assert catalog["profile"] == "data-package-catalog"
    assert catalog["accessURL"] == "https://drive.google.com/drive/folders/folder123"
    assert document["catalogs"][0]["accessURL"] == catalog["accessURL"]
    assert document["catalogs"][0]["serviceType"] == "GoogleDrive"
    assert document["catalogs"][0]["entityType"] == "Directory"


def test_add_resource_to_descriptor_rejects_directory_as_resource(
    tmp_path: Path,
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(descriptor)

    with pytest.raises(ValueError, match="Non-file drive entries"):
        _add_resource_to_descriptor(
            descriptor,
            name="census-docs",
            path="https://drive.google.com/drive/folders/folder123",
            cache="downloads/census",
            service_type="GoogleDrive",
            entity_type="Directory",
        )


def test_add_resource_to_descriptor_requires_existing_descriptor_by_default(
    tmp_path: Path,
) -> None:
    descriptor = tmp_path / "missing.yaml"

    with pytest.raises(FileNotFoundError, match="does not exist"):
        _add_resource_to_descriptor(
            descriptor,
            name="source-export",
            path="s3://my-bucket/path/to/source-export.csv",
            cache="background/exports/source-export.csv",
        )


def test_add_resource_to_descriptor_allows_create_if_missing(tmp_path: Path) -> None:
    descriptor = tmp_path / "created.yaml"

    resource = _add_resource_to_descriptor(
        descriptor,
        name="source-export",
        path="s3://my-bucket/path/to/source-export.csv",
        cache="background/exports/source-export.csv",
        create_if_missing=True,
    )

    assert descriptor.exists()
    assert resource["name"] == "source-export"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("s3://bucket/raw.csv", "S3"),
        (
            "https://tenant.sharepoint.com/sites/Test/Shared%20Documents/spec.xlsx",
            "SharePoint",
        ),
        ("https://docs.google.com/spreadsheets/d/test-sheet/edit", "GoogleDrive"),
    ],
)
def test_infer_service_type(source: str, expected: str) -> None:
    assert infer_service_type(source) == expected


def test_infer_service_type_raises_when_unknown() -> None:
    with pytest.raises(NotImplementedError, match="Could not infer serviceType"):
        infer_service_type("C:/tmp/local-file.txt")
