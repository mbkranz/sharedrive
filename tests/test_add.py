from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from sharedrive.actions.add import add_resource_to_descriptor, infer_drive_service


def _write_catalog_descriptor(
    path: Path,
    *,
    resources: list[dict] | None = None,
    packages: list[dict] | None = None,
) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "$schema": "data-package-catalog",
                "resources": resources or [],
                "packages": packages or [],
                "catalogs": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_add_resource_to_descriptor_writes_source_service_type(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(descriptor)

    resource = add_resource_to_descriptor(
        descriptor,
        name="source-export",
        path="background/exports/source-export.csv",
        source="s3://my-bucket/path/to/source-export.csv",
        title="Source export",
        description="Exported source data",
    )

    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))

    assert resource["syncTarget"] == "path"
    assert document["$schema"] == "data-package-catalog"
    assert document["resources"][0]["sources"][0]["serviceType"] == "S3"
    assert document["resources"][0]["sources"][0]["entityType"] == "File"


def test_add_resource_to_descriptor_rejects_duplicate_names(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(
        descriptor,
        resources=[
            {
                "name": "source-export",
                "path": "existing.csv",
                "syncTarget": "path",
                "sources": [
                    {
                        "path": "s3://bucket/existing.csv",
                        "serviceType": "S3",
                        "entityType": "File",
                    }
                ],
            }
        ],
    )

    with pytest.raises(ValueError, match="already exists"):
        add_resource_to_descriptor(
            descriptor,
            name="source-export",
            path="background/exports/source-export.csv",
            source="s3://my-bucket/path/to/source-export.csv",
        )


def test_add_resource_to_descriptor_rejects_unsupported_service_type(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(descriptor)

    with pytest.raises(NotImplementedError, match="not implemented"):
        add_resource_to_descriptor(
            descriptor,
            name="local-file",
            path="background/local-file.txt",
            source="https://example.com/files/local-file.txt",
            service_type="OneDrive",
        )


def test_add_resource_to_descriptor_creates_resources_sync_target(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(descriptor)

    resource = add_resource_to_descriptor(
        descriptor,
        name="census-docs",
        path="downloads/census",
        source="https://drive.google.com/drive/folders/folder123",
        service_type="GoogleDrive",
        entity_type="Directory",
        sync_target="resources",
        profile="data-package",
    )

    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))

    assert resource["profile"] == "data-package"
    assert resource["syncTarget"] == "resources"
    assert resource["resources"] == []
    assert document["packages"][0]["profile"] == "data-package"
    assert document["packages"][0]["resources"] == []
    assert document["packages"][0]["sources"][0]["serviceType"] == "GoogleDrive"
    assert document["packages"][0]["sources"][0]["entityType"] == "Directory"


def test_add_resource_to_descriptor_requires_sync_target_for_directory_source(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_catalog_descriptor(descriptor)

    with pytest.raises(ValueError, match="syncTarget is required"):
        add_resource_to_descriptor(
            descriptor,
            name="census-docs",
            path="downloads/census",
            source="https://drive.google.com/drive/folders/folder123",
            service_type="GoogleDrive",
            entity_type="Directory",
        )


def test_add_resource_to_descriptor_requires_existing_descriptor_by_default(
    tmp_path: Path,
) -> None:
    descriptor = tmp_path / "missing.yaml"

    with pytest.raises(FileNotFoundError, match="does not exist"):
        add_resource_to_descriptor(
            descriptor,
            name="source-export",
            path="background/exports/source-export.csv",
            source="s3://my-bucket/path/to/source-export.csv",
        )


def test_add_resource_to_descriptor_allows_create_if_missing(tmp_path: Path) -> None:
    descriptor = tmp_path / "created.yaml"

    resource = add_resource_to_descriptor(
        descriptor,
        name="source-export",
        path="background/exports/source-export.csv",
        source="s3://my-bucket/path/to/source-export.csv",
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
def test_infer_drive_service(source: str, expected: str) -> None:
    assert infer_drive_service(source) == expected


def test_infer_drive_service_raises_when_unknown() -> None:
    with pytest.raises(NotImplementedError, match="Could not infer drive service"):
        infer_drive_service("C:/tmp/local-file.txt")