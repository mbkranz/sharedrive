from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from sharedrive.cli import app

RUNNER = CliRunner()


def _write_descriptor(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "resources": [
                    {
                        "name": "spec-workbook",
                        "path": "background/specs/spec-workbook.xlsx",
                        "syncTarget": "path",
                        "sources": [
                            {
                                "path": "https://tenant.sharepoint.com/sites/Test/Shared%20Documents/spec.xlsx",
                                "serviceType": "SharePoint",
                                "entityType": "File",
                            }
                        ],
                    },
                    {
                        "name": "spec-catalog",
                        "path": "background/specs/spec-catalog.xlsx",
                        "syncTarget": "path",
                        "sources": [
                            {
                                "path": "https://tenant.sharepoint.com/sites/Test/Shared%20Documents/spec-catalog.xlsx",
                                "serviceType": "SharePoint",
                                "entityType": "File",
                            }
                        ],
                    },
                    {
                        "name": "other-resource",
                        "path": "background/specs/other-resource.xlsx",
                        "syncTarget": "path",
                        "sources": [
                            {
                                "path": "https://tenant.sharepoint.com/sites/Test/Shared%20Documents/other-resource.xlsx",
                                "serviceType": "SharePoint",
                                "entityType": "File",
                            }
                        ],
                    },
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_checked_out_resource(tmp_path: Path, descriptor: Path, resource_name: str) -> None:
    store_path = tmp_path / ".sharedrive" / "sharedrive_set.json"
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(
        json.dumps(
            {
                "global": {},
                "descriptors": {
                    str(descriptor): {
                        "checkout": {
                            "kind": "resource",
                            "selector": resource_name,
                            "include": [resource_name],
                            "resolved": [resource_name],
                        }
                    }
                },
            },
            indent=4,
        ),
        encoding="utf-8",
    )


def _write_checked_out_resources(tmp_path: Path, descriptor: Path, resource_names: list[str]) -> None:
    store_path = tmp_path / ".sharedrive" / "sharedrive_set.json"
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(
        json.dumps(
            {
                "global": {},
                "descriptors": {
                    str(descriptor): {
                        "checkout": {
                            "kind": "resource",
                            "selector": "bulk",
                            "include": resource_names,
                            "resolved": resource_names,
                        }
                    }
                },
            },
            indent=4,
        ),
        encoding="utf-8",
    )


def test_update_resource_updates_explicit_property(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)

    result = RUNNER.invoke(
        app,
        [
            "update",
            "spec-workbook",
            "path",
            "background/specs/spec-workbook-renamed.xlsx",
            "--descriptor",
            str(descriptor),
        ],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
    assert document["resources"][0]["path"] == "background/specs/spec-workbook-renamed.xlsx"


def test_update_resource_uses_checked_out_resource(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    _write_checked_out_resource(tmp_path, descriptor, "spec-workbook")

    result = RUNNER.invoke(
        app,
        ["update", "title", "Updated title", "--descriptor", str(descriptor)],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
    assert document["resources"][0]["title"] == "Updated title"


def test_update_resource_normalizes_service_type(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)

    result = RUNNER.invoke(
        app,
        [
            "update",
            "spec-workbook",
            "serviceType",
            "sharepoint",
            "--descriptor",
            str(descriptor),
        ],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
    assert document["resources"][0]["sources"][0]["serviceType"] == "SharePoint"


def test_update_resource_glob_updates_multiple_resources(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)

    result = RUNNER.invoke(
        app,
        [
            "update",
            "spec-*",
            "title",
            "Shared title",
            "--descriptor",
            str(descriptor),
        ],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
    titles = {resource["name"]: resource.get("title") for resource in document["resources"]}
    assert titles["spec-workbook"] == "Shared title"
    assert titles["spec-catalog"] == "Shared title"
    assert titles.get("other-resource") is None


def test_update_resource_uses_multiple_checked_out_resources(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    _write_checked_out_resources(tmp_path, descriptor, ["spec-workbook", "spec-catalog"])

    result = RUNNER.invoke(
        app,
        ["update", "title", "Checked out title", "--descriptor", str(descriptor)],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))
    titles = {resource["name"]: resource.get("title") for resource in document["resources"]}
    assert titles["spec-workbook"] == "Checked out title"
    assert titles["spec-catalog"] == "Checked out title"
    assert titles.get("other-resource") is None