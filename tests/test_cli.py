from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from typer.testing import CliRunner

from sharedrive.actions.fetch import AuthCheckResult
from sharedrive.actions.sync import SyncSummary
from sharedrive.cli import app

RUNNER = CliRunner()


def _write_descriptor(path: Path) -> None:
    path.write_text("resources: []\n", encoding="utf-8")


def test_auth_check_returns_json_and_passes_include(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    def fake_check_auth_for_descriptor(**kwargs):
        captured.update(kwargs)
        return [AuthCheckResult("googledrive", True, "Google Drive credentials are ready.")]

    monkeypatch.setattr("sharedrive.cli.check_auth_for_descriptor", fake_check_auth_for_descriptor)

    result = RUNNER.invoke(
        app,
        ["auth", "check", str(descriptor), "--include", "googledrive", "--format", "json"],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert '"adapter": "googledrive"' in result.stdout
    assert captured["include"] == ["googledrive"]


def test_auth_check_uses_saved_global_descriptor_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    def fake_check_auth_for_descriptor(**kwargs):
        captured.update(kwargs)
        return [AuthCheckResult("googledrive", True, "Google Drive credentials are ready.")]

    monkeypatch.setattr("sharedrive.cli.check_auth_for_descriptor", fake_check_auth_for_descriptor)

    set_result = RUNNER.invoke(
        app,
        ["set", "--global", "--descriptor", "resources/descriptor.yaml"],
        prog_name="sharedrive",
    )
    assert set_result.exit_code == 0

    result = RUNNER.invoke(
        app,
        ["auth", "check", "--include", "googledrive", "--format", "json"],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert captured["descriptor"] == Path("resources/descriptor.yaml")
    assert captured["include"] == ["googledrive"]


def test_checkout_resource_saves_descriptor_scoped_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
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

    result = RUNNER.invoke(
        app,
        [
            "checkout",
            "resource",
            "census-docs.selected-export",
            "--descriptor",
            str(descriptor),
        ],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    store = json.loads(
        (tmp_path / ".sharedrive" / "sharedrive_set.json").read_text(encoding="utf-8")
    )
    checkout = store["descriptors"][str(descriptor)]["checkout"]
    assert checkout["kind"] == "resource"
    assert checkout["include"] == ["census-docs.selected-export"]
    assert checkout["resolved"] == ["census-docs.selected-export"]


def test_checkout_driveservice_saves_descriptor_scoped_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "descriptor.yaml"
    descriptor.write_text(
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
""".strip(),
        encoding="utf-8",
    )

    result = RUNNER.invoke(
        app,
        ["checkout", "driveservice", "googledrive", "--descriptor", str(descriptor)],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    store = json.loads(
        (tmp_path / ".sharedrive" / "sharedrive_set.json").read_text(encoding="utf-8")
    )
    checkout = store["descriptors"][str(descriptor)]["checkout"]
    assert checkout["kind"] == "driveservice"
    assert checkout["include"] == ["googledrive"]
    assert checkout["resolved"] == ["drive-export"]


def test_checkout_show_displays_descriptor_scoped_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "descriptor.yaml"
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
                            "selector": "spec-workbook",
                            "include": ["spec-workbook"],
                            "resolved": ["spec-workbook"],
                        }
                    }
                },
            },
            indent=4,
        ),
        encoding="utf-8",
    )

    result = RUNNER.invoke(
        app,
        ["checkout", "show", "--descriptor", str(descriptor)],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert "Active checkout kind: resource" in result.stdout
    assert "spec-workbook" in result.stdout


def test_checkout_clear_removes_descriptor_scoped_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "descriptor.yaml"
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
                            "selector": "spec-workbook",
                            "include": ["spec-workbook"],
                            "resolved": ["spec-workbook"],
                        }
                    }
                },
            },
            indent=4,
        ),
        encoding="utf-8",
    )

    result = RUNNER.invoke(
        app,
        ["checkout", "clear", "--descriptor", str(descriptor)],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    store = json.loads(store_path.read_text(encoding="utf-8"))
    assert store["descriptors"][str(descriptor)] == {}
    assert "Cleared checked out selection" in result.stdout


def test_auth_check_exits_nonzero_on_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)

    monkeypatch.setattr(
        "sharedrive.cli.check_auth_for_descriptor",
        lambda **_kwargs: [AuthCheckResult("sharepoint", False, "SharePoint authentication failed: bad config")],
    )

    result = RUNNER.invoke(app, ["auth", "check", str(descriptor)], prog_name="sharedrive")

    assert result.exit_code == 1
    assert "sharepoint: failed" in result.stdout.lower()


def test_auth_login_gdrive_uses_user_oauth_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class DummyStrategy:
        def build(self):
            captured["build_called"] = True
            return object()

    class DummyConfig:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.oauth_token_path = kwargs.get("oauth_token_path")

        def to_strategy(self):
            return DummyStrategy()

    monkeypatch.setattr("sharedrive.auth.settings.GoogleAuthConfig", DummyConfig)

    result = RUNNER.invoke(
        app,
        [
            "auth",
            "login",
            "gdrive",
            "--oauth-client-secrets",
            "oauth-client.json",
            "--oauth-token-path",
            "oauth-token.json",
            "--scope",
            "scope-a",
            "--no-local-server",
        ],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert captured["use_local_server"] is False
    assert captured["scopes"] == ["scope-a"]
    assert str(captured["oauth_client_secrets"]).endswith("oauth-client.json")
    assert str(captured["oauth_token_path"]).endswith("oauth-token.json")
    assert captured["build_called"] is True
    assert "Token saved to" in result.stdout


def test_auth_login_sharepoint_uses_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class DummyStrategy:
        def build(self):
            captured["build_called"] = True
            return "token"

    class DummyConfig:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.auth_mode = SimpleNamespace(value=kwargs.get("auth_mode", "app_only"))
            self.host_url = kwargs.get("host_url", "norc.sharepoint.com")

        def to_strategy(self):
            return DummyStrategy()

    monkeypatch.setattr("sharedrive.auth.settings.MicrosoftAuthConfig", DummyConfig)
    monkeypatch.setattr("sharedrive.auth.settings.MicrosoftAuthMode", lambda value: value)

    result = RUNNER.invoke(
        app,
        [
            "auth",
            "login",
            "sharepoint",
            "--auth-mode",
            "delegated",
            "--host-url",
            "tenant.sharepoint.com",
            "--scope",
            "scope-a",
        ],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert captured["auth_mode"] == "delegated"
    assert captured["host_url"] == "tenant.sharepoint.com"
    assert captured["scopes"] == ["scope-a"]
    assert captured["build_called"] is True
    assert "Microsoft login succeeded" in result.stdout


def test_auth_login_microsoft_uses_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class DummyStrategy:
        def build(self):
            captured["build_called"] = True
            return "token"

    class DummyConfig:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.auth_mode = SimpleNamespace(value=kwargs.get("auth_mode", "app_only"))
            self.host_url = kwargs.get("host_url", "norc.sharepoint.com")

        def to_strategy(self):
            return DummyStrategy()

    monkeypatch.setattr("sharedrive.auth.settings.MicrosoftAuthConfig", DummyConfig)
    monkeypatch.setattr("sharedrive.auth.settings.MicrosoftAuthMode", lambda value: value)

    result = RUNNER.invoke(
        app,
        [
            "auth",
            "login",
            "microsoft",
            "--auth-mode",
            "delegated",
            "--host-url",
            "tenant.sharepoint.com",
            "--scope",
            "scope-a",
        ],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert captured["auth_mode"] == "delegated"
    assert captured["host_url"] == "tenant.sharepoint.com"
    assert captured["scopes"] == ["scope-a"]
    assert captured["build_called"] is True
    assert "Microsoft login succeeded" in result.stdout


def test_fetch_passes_check_auth_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    def fake_fetch_from_descriptor(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(ok=True)

    monkeypatch.setattr("sharedrive.cli.fetch_from_descriptor", fake_fetch_from_descriptor)

    result = RUNNER.invoke(
        app,
        ["fetch", str(descriptor), "--check-auth", "--dry-run"],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert captured["check_auth"] is True


def test_fetch_uses_checked_out_selection_when_include_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

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
                            "selector": "spec-workbook",
                            "include": ["spec-workbook"],
                            "resolved": ["spec-workbook"],
                        }
                    }
                },
            },
            indent=4,
        ),
        encoding="utf-8",
    )

    def fake_fetch_from_descriptor(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(ok=True)

    monkeypatch.setattr("sharedrive.cli.fetch_from_descriptor", fake_fetch_from_descriptor)

    result = RUNNER.invoke(
        app,
        ["fetch", str(descriptor), "--dry-run"],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert captured["include"] == ["spec-workbook"]


def test_auth_check_uses_checked_out_selection_when_include_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    store_path = tmp_path / ".sharedrive" / "sharedrive_set.json"
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(
        json.dumps(
            {
                "global": {},
                "descriptors": {
                    str(descriptor): {
                        "checkout": {
                            "kind": "driveservice",
                            "selector": "GoogleDrive",
                            "include": ["googledrive"],
                            "resolved": ["drive-export"],
                        }
                    }
                },
            },
            indent=4,
        ),
        encoding="utf-8",
    )

    def fake_check_auth_for_descriptor(**kwargs):
        captured.update(kwargs)
        return [AuthCheckResult("googledrive", True, "ready")]

    monkeypatch.setattr("sharedrive.cli.check_auth_for_descriptor", fake_check_auth_for_descriptor)

    result = RUNNER.invoke(
        app,
        ["auth", "check", str(descriptor)],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert captured["include"] == ["googledrive"]


def test_set_command_saves_global_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    _write_descriptor(descriptor)

    result = RUNNER.invoke(
        app,
        ["set", "--global", "--descriptor", "resources/descriptor.yaml", "--output-dir", "exports"],
        prog_name="sharedrive",
    )

    store_path = tmp_path / ".sharedrive" / "sharedrive_set.json"
    store = json.loads(store_path.read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert store == {
        "global": {
            "descriptor": "resources/descriptor.yaml",
            "output_dir": "exports",
        },
        "descriptors": {},
    }


def test_set_command_rejects_missing_descriptor_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)

    result = RUNNER.invoke(
        app,
        ["set", "--global", "--descriptor", "resources/missing.yaml"],
        prog_name="sharedrive",
    )

    assert result.exit_code != 0
    assert "Invalid value for --descriptor" in result.output


def test_add_uses_saved_global_descriptor_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    descriptor.write_text("$schema: example\nresources: []\n", encoding="utf-8")

    set_result = RUNNER.invoke(
        app,
        ["set", "--global", "--descriptor", "resources/descriptor.yaml"],
        prog_name="sharedrive",
    )
    assert set_result.exit_code == 0

    result = RUNNER.invoke(
        app,
        [
            "add",
            "spec-workbook",
            "--path",
            "background/specs/spec-workbook.xlsx",
            "--source",
            "https://tenant.sharepoint.com/sites/Test/Shared%20Documents/spec.xlsx",
        ],
        prog_name="sharedrive",
    )

    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert document["resources"][0]["name"] == "spec-workbook"
    assert "descriptor.yaml" in result.stdout


def test_add_fails_when_saved_global_descriptor_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    _write_descriptor(descriptor)

    set_result = RUNNER.invoke(
        app,
        ["set", "--global", "--descriptor", "resources/descriptor.yaml"],
        prog_name="sharedrive",
    )
    assert set_result.exit_code == 0

    descriptor.unlink()

    result = RUNNER.invoke(
        app,
        [
            "add",
            "spec-workbook",
            "--path",
            "background/specs/spec-workbook.xlsx",
            "--source",
            "https://tenant.sharepoint.com/sites/Test/Shared%20Documents/spec.xlsx",
        ],
        prog_name="sharedrive",
    )

    assert result.exit_code == 1
    assert "does not exist" in result.output


def test_add_allows_creating_default_descriptor_when_not_explicit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = RUNNER.invoke(
        app,
        [
            "add",
            "spec-workbook",
            "--path",
            "background/specs/spec-workbook.xlsx",
            "--source",
            "https://tenant.sharepoint.com/sites/Test/Shared%20Documents/spec.xlsx",
        ],
        prog_name="sharedrive",
    )

    descriptor = tmp_path / "resources" / "descriptor.yaml"
    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert descriptor.exists()
    assert document["resources"][0]["name"] == "spec-workbook"


def test_fetch_uses_saved_defaults_when_descriptor_omitted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    def fake_fetch_from_descriptor(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(ok=True)

    monkeypatch.setattr("sharedrive.cli.fetch_from_descriptor", fake_fetch_from_descriptor)

    set_result = RUNNER.invoke(
        app,
        ["set", "--global", "--descriptor", "resources/descriptor.yaml", "--output-dir", "exports"],
        prog_name="sharedrive",
    )
    assert set_result.exit_code == 0

    result = RUNNER.invoke(
        app,
        ["fetch", "--check-auth", "--dry-run"],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert captured["descriptor"] == Path("resources/descriptor.yaml")
    assert captured["output_dir"] == Path("exports")
    assert captured["check_auth"] is True


def test_fetch_exits_nonzero_when_descriptor_is_missing(tmp_path: Path) -> None:
    descriptor = tmp_path / "missing.yaml"

    result = RUNNER.invoke(
        app,
        ["fetch", str(descriptor), "--dry-run"],
        prog_name="sharedrive",
    )

    assert result.exit_code == 1
    assert "does not exist" in result.output


def test_retrieve_uses_saved_defaults_when_descriptor_omitted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    def fake_fetch_from_descriptor(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(ok=True)

    monkeypatch.setattr("sharedrive.cli.fetch_from_descriptor", fake_fetch_from_descriptor)

    set_result = RUNNER.invoke(
        app,
        ["set", "--global", "--descriptor", "resources/descriptor.yaml", "--output-dir", "exports"],
        prog_name="sharedrive",
    )
    assert set_result.exit_code == 0

    result = RUNNER.invoke(
        app,
        ["retrieve", "--check-auth", "--dry-run"],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert captured["descriptor"] == Path("resources/descriptor.yaml")
    assert captured["output_dir"] == Path("exports")
    assert captured["check_auth"] is True


def test_add_command_writes_resource_to_descriptor(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    descriptor.write_text("$schema: example\nresources: []\n", encoding="utf-8")

    result = RUNNER.invoke(
        app,
        [
            "add",
            "spec-workbook",
            "--path",
            "background/specs/spec-workbook.xlsx",
            "--descriptor",
            str(descriptor),
            "--source",
            "https://tenant.sharepoint.com/sites/Test/Shared%20Documents/spec.xlsx",
            "--title",
            "Spec workbook",
            "--description",
            "Source workbook for specs",
        ],
        prog_name="sharedrive",
    )

    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert document["$schema"] == "example"
    assert document["resources"] == [
        {
            "name": "spec-workbook",
            "path": "background/specs/spec-workbook.xlsx",
            "syncTarget": "path",
            "title": "Spec workbook",
            "description": "Source workbook for specs",
            "sources": [
                {
                    "path": "https://tenant.sharepoint.com/sites/Test/Shared%20Documents/spec.xlsx",
                    "serviceType": "SharePoint",
                    "entityType": "File",
                }
            ],
        }
    ]


def test_add_command_rejects_missing_explicit_descriptor(tmp_path: Path) -> None:
    missing_descriptor = tmp_path / "missing.yaml"

    result = RUNNER.invoke(
        app,
        [
            "add",
            "spec-workbook",
            "--path",
            "background/specs/spec-workbook.xlsx",
            "--descriptor",
            str(missing_descriptor),
            "--source",
            "https://tenant.sharepoint.com/sites/Test/Shared%20Documents/spec.xlsx",
        ],
        prog_name="sharedrive",
    )

    assert result.exit_code == 1
    assert "does not exist" in result.output


def test_add_command_writes_resources_sync_target_to_descriptor(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    descriptor.write_text("resources: []\n", encoding="utf-8")

    result = RUNNER.invoke(
        app,
        [
            "add",
            "census-docs",
            "--path",
            "downloads/census",
            "--descriptor",
            str(descriptor),
            "--source",
            "https://drive.google.com/drive/folders/folder123",
            "--service-type",
            "GoogleDrive",
            "--entity-type",
            "Directory",
            "--sync-target",
            "resources",
            "--profile",
            "data-package",
        ],
        prog_name="sharedrive",
    )

    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert document["resources"] == [
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
            "profile": "data-package",
            "resources": [],
        }
    ]


def test_sync_command_passes_descriptor_and_dry_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    descriptor.write_text("resources: []\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_sync_resource_in_descriptor(**kwargs):
        captured.update(kwargs)
        return SyncSummary(resource_name="census-docs", generated_resources=2, dry_run=True)

    monkeypatch.setattr(
        "sharedrive.cli.sync_resource_in_descriptor",
        fake_sync_resource_in_descriptor,
    )

    result = RUNNER.invoke(
        app,
        [
            "sync",
            "census-docs",
            "--descriptor",
            str(descriptor),
            "--dry-run",
        ],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert captured["descriptor"] == descriptor
    assert captured["resource_name"] == "census-docs"
    assert captured["dry_run"] is True
    assert captured["log"] is None
    assert "Would sync 2 resource(s)" in result.stdout


def test_sync_uses_checked_out_resource_when_name_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "descriptor.yaml"
    descriptor.write_text("resources: []\n", encoding="utf-8")
    captured: dict[str, object] = {}

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
                            "selector": "census-docs",
                            "include": ["census-docs"],
                            "resolved": ["census-docs"],
                        }
                    }
                },
            },
            indent=4,
        ),
        encoding="utf-8",
    )

    def fake_sync_resource_in_descriptor(**kwargs):
        captured.update(kwargs)
        return SyncSummary(resource_name="census-docs", generated_resources=1, dry_run=True)

    monkeypatch.setattr("sharedrive.cli.sync_resource_in_descriptor", fake_sync_resource_in_descriptor)

    result = RUNNER.invoke(
        app,
        ["sync", "--descriptor", str(descriptor), "--dry-run"],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert captured["resource_name"] == "census-docs"


def test_sync_rejects_nested_checked_out_resource_when_name_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "descriptor.yaml"
    descriptor.write_text("resources: []\n", encoding="utf-8")

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
                            "selector": "census-docs.selected-export",
                            "include": ["census-docs.selected-export"],
                            "resolved": ["census-docs.selected-export"],
                        }
                    }
                },
            },
            indent=4,
        ),
        encoding="utf-8",
    )

    result = RUNNER.invoke(
        app,
        ["sync", "--descriptor", str(descriptor)],
        prog_name="sharedrive",
    )

    assert result.exit_code != 0
    assert "nested dot-path selections are not supported" in result.output


def test_sync_command_exits_nonzero_on_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    descriptor.write_text("resources: []\n", encoding="utf-8")

    monkeypatch.setattr(
        "sharedrive.cli.sync_resource_in_descriptor",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("Resource 'missing' was not found.")),
    )

    result = RUNNER.invoke(
        app,
        ["sync", "missing", "--descriptor", str(descriptor)],
        prog_name="sharedrive",
    )

    assert result.exit_code == 1
    assert "was not found" in result.output


def test_sync_command_exits_nonzero_when_descriptor_is_missing(tmp_path: Path) -> None:
    descriptor = tmp_path / "missing.yaml"

    result = RUNNER.invoke(
        app,
        ["sync", "missing", "--descriptor", str(descriptor)],
        prog_name="sharedrive",
    )

    assert result.exit_code == 1
    assert "does not exist" in result.output


def test_add_command_exits_nonzero_for_unknown_source(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)

    result = RUNNER.invoke(
        app,
        [
            "add",
            "local-file",
            "--path",
            "background/local-file.txt",
            "--descriptor",
            str(descriptor),
            "--source",
            "C:/tmp/local-file.txt",
        ],
        prog_name="sharedrive",
    )

    assert result.exit_code == 1
    assert "Could not infer drive service" in result.output