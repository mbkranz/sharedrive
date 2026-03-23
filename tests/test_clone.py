from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from sharedrive.cli import app

RUNNER = CliRunner()


def _write_descriptor(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
resources:
  - name: source-export
    path: downloads/source.csv
    syncTarget: path
    sources:
      - path: s3://bucket/source.csv
        serviceType: S3
        entityType: File
""".strip(),
        encoding="utf-8",
    )


def test_clone_descriptor_writes_target_yaml(tmp_path: Path) -> None:
    source_descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(source_descriptor)
    target_descriptor = tmp_path / "descriptor-copy.yaml"

    result = RUNNER.invoke(
        app,
        ["clone", "descriptor", str(target_descriptor), "--descriptor", str(source_descriptor)],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert yaml.safe_load(target_descriptor.read_text(encoding="utf-8")) == yaml.safe_load(
        source_descriptor.read_text(encoding="utf-8")
    )


def test_clone_descriptor_uses_target_suffix_format(tmp_path: Path) -> None:
    source_descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(source_descriptor)
    target_descriptor = tmp_path / "descriptor-copy.json"

    result = RUNNER.invoke(
        app,
        ["clone", "descriptor", str(target_descriptor), "--descriptor", str(source_descriptor)],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    payload = json.loads(target_descriptor.read_text(encoding="utf-8"))
    assert payload["resources"][0]["name"] == "source-export"


def test_clone_descriptor_dry_run_does_not_write(tmp_path: Path) -> None:
    source_descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(source_descriptor)
    target_descriptor = tmp_path / "descriptor-copy.yaml"

    result = RUNNER.invoke(
        app,
        [
            "clone",
            "descriptor",
            str(target_descriptor),
            "--descriptor",
            str(source_descriptor),
            "--dry-run",
        ],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert "Would clone descriptor" in result.stdout
    assert not target_descriptor.exists()


def test_clone_descriptor_rejects_existing_target_without_force(tmp_path: Path) -> None:
    source_descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(source_descriptor)
    target_descriptor = tmp_path / "descriptor-copy.yaml"
    target_descriptor.write_text("resources: []\n", encoding="utf-8")

    result = RUNNER.invoke(
        app,
        ["clone", "descriptor", str(target_descriptor), "--descriptor", str(source_descriptor)],
        prog_name="sharedrive",
    )

    assert result.exit_code != 0
    assert "Refusing to overwrite existing descriptor" in result.output


def test_clone_descriptor_force_overwrites_existing_target(tmp_path: Path) -> None:
    source_descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(source_descriptor)
    target_descriptor = tmp_path / "descriptor-copy.yaml"
    target_descriptor.write_text("resources: []\n", encoding="utf-8")

    result = RUNNER.invoke(
        app,
        [
            "clone",
            "descriptor",
            str(target_descriptor),
            "--descriptor",
            str(source_descriptor),
            "--force",
        ],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert yaml.safe_load(target_descriptor.read_text(encoding="utf-8"))["resources"][0]["name"] == "source-export"