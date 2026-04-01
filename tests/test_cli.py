from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from typer.testing import CliRunner

from sharedrive.actions.download import AuthCheckResult
from sharedrive.cli import app

RUNNER = CliRunner()


def _write_descriptor(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "$schema": "data-package-catalog",
                "resources": [
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
                ],
                "packages": [
                    {
                        "name": "census-package",
                        "path": "downloads/census",
                        "syncTarget": "resources",
                        "sources": [
                            {
                                "path": "https://drive.google.com/drive/folders/folder123",
                                "serviceType": "GoogleDrive",
                                "entityType": "Directory",
                            }
                        ],
                        "resources": [],
                    },
                ],
                "catalogs": [
                    {
                        "name": "archived",
                        "packages": [
                            {
                                "name": "nested-package",
                                "path": "downloads/archived/nested-package",
                                "syncTarget": "resources",
                                "sources": [
                                    {
                                        "path": "https://drive.google.com/drive/folders/nested-folder",
                                        "serviceType": "GoogleDrive",
                                        "entityType": "Directory",
                                    }
                                ],
                                "resources": [],
                            }
                        ],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


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


def test_auth_check_uses_checked_out_descriptor_default(
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

    checkout_result = RUNNER.invoke(
        app,
        ["checkout", "resources/descriptor.yaml"],
        prog_name="sharedrive",
    )
    assert checkout_result.exit_code == 0

    result = RUNNER.invoke(
        app,
        ["auth", "check", "--include", "googledrive", "--format", "json"],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert captured["descriptor"] == Path("resources/descriptor.yaml")
    assert captured["include"] == ["googledrive"]


def test_checkout_sets_global_descriptor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    _write_descriptor(descriptor)

    result = RUNNER.invoke(app, ["checkout", "resources/descriptor.yaml"], prog_name="sharedrive")

    store = json.loads((tmp_path / ".sharedrive" / "sharedrive_set.json").read_text(encoding="utf-8"))
    assert result.exit_code == 0
    assert store["global"]["descriptor"] == "resources/descriptor.yaml"


def test_checkout_rejects_missing_descriptor(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)

    result = RUNNER.invoke(app, ["checkout", "missing.yaml"], prog_name="sharedrive")

    assert result.exit_code != 0
    assert "does not exist" in result.output


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


def test_download_passes_check_auth_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    def fake_download_from_descriptor(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(ok=True)

    monkeypatch.setattr("sharedrive.cli.download_from_descriptor", fake_download_from_descriptor)

    result = RUNNER.invoke(
        app,
        ["download", str(descriptor), "--check-auth", "--dry-run"],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert captured["check_auth"] is True


def test_download_defaults_to_all_when_include_is_omitted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    def fake_download_from_descriptor(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(ok=True)

    monkeypatch.setattr("sharedrive.cli.download_from_descriptor", fake_download_from_descriptor)

    result = RUNNER.invoke(app, ["download", "my-package", "--descriptor", str(descriptor), "--dry-run"], prog_name="sharedrive")

    assert result.exit_code == 0
    assert captured["include"] == "my-package"


def test_download_uses_saved_defaults_when_descriptor_omitted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    def fake_download_from_descriptor(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(ok=True)

    monkeypatch.setattr("sharedrive.cli.download_from_descriptor", fake_download_from_descriptor)

    set_result = RUNNER.invoke(
        app,
        ["set", "--global", "--descriptor", "resources/descriptor.yaml", "--output-dir", "exports", "--selector", "my-package"],
        prog_name="sharedrive",
    )
    assert set_result.exit_code == 0

    result = RUNNER.invoke(app, ["download", "--check-auth", "--dry-run"], prog_name="sharedrive")

    assert result.exit_code == 0
    assert captured["descriptor"] == Path("resources/descriptor.yaml")
    assert captured["output_dir"] == Path("exports")
    assert captured["check_auth"] is True
    assert captured["include"] == "my-package"


def test_download_exits_nonzero_when_descriptor_is_missing(tmp_path: Path) -> None:
    descriptor = tmp_path / "missing.yaml"

    result = RUNNER.invoke(app, ["download", "my-package", "--descriptor", str(descriptor), "--dry-run"], prog_name="sharedrive")

    assert result.exit_code == 1
    assert "does not exist" in result.output


def test_fetch_passes_descriptor_and_dry_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    def fake_fetch_resource_metadata_in_descriptor(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(resource_name="census-package", generated_resources=2, dry_run=True)

    monkeypatch.setattr(
        "sharedrive.cli.fetch_resource_metadata_in_descriptor",
        fake_fetch_resource_metadata_in_descriptor,
    )

    result = RUNNER.invoke(
        app,
        ["fetch", "census-package", "--descriptor", str(descriptor), "--dry-run"],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert captured["descriptor"] == descriptor
    assert captured["resource_name"] == "census-package"
    assert captured["dry_run"] is True


def test_fetch_uses_checked_out_descriptor_when_omitted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    def fake_fetch_resource_metadata_in_descriptor(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(resource_name="census-package", generated_resources=1, dry_run=True)

    monkeypatch.setattr(
        "sharedrive.cli.fetch_resource_metadata_in_descriptor",
        fake_fetch_resource_metadata_in_descriptor,
    )

    checkout_result = RUNNER.invoke(app, ["checkout", "resources/descriptor.yaml"], prog_name="sharedrive")
    assert checkout_result.exit_code == 0

    result = RUNNER.invoke(app, ["fetch", "census-package", "--dry-run"], prog_name="sharedrive")

    assert result.exit_code == 0
    assert captured["descriptor"] == Path("resources/descriptor.yaml")


def test_fetch_uses_checked_out_descriptor_and_saved_selector_when_arguments_are_omitted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    def fake_fetch_resource_metadata_in_descriptor(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(resource_name="archived.nested-package", generated_resources=1, dry_run=True)

    monkeypatch.setattr(
        "sharedrive.cli.fetch_resource_metadata_in_descriptor",
        fake_fetch_resource_metadata_in_descriptor,
    )

    checkout_result = RUNNER.invoke(app, ["checkout", "resources/descriptor.yaml"], prog_name="sharedrive")
    assert checkout_result.exit_code == 0

    set_result = RUNNER.invoke(
        app,
        ["set", "--global", "--selector", "archived.nested-package"],
        prog_name="sharedrive",
    )
    assert set_result.exit_code == 0

    result = RUNNER.invoke(app, ["fetch", "--dry-run"], prog_name="sharedrive")

    assert result.exit_code == 0
    assert captured["descriptor"] == Path("resources/descriptor.yaml")
    assert captured["resource_name"] == "archived.nested-package"


def test_download_source_path_upserts_descriptor_and_runs_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    captured: dict[str, object] = {}

    def fake_run_download_command(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("sharedrive.cli._run_download_command", fake_run_download_command)

    result = RUNNER.invoke(
        app,
        [
            "download",
            "--source-path",
            "https://example.sharepoint.com/sites/Test/Shared%20Documents/spec.xlsx",
            "--resource",
            "sharepoint-spec",
        ],
        prog_name="sharedrive",
    )

    descriptor = tmp_path / "resources" / "descriptor.yaml"
    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert captured["include"] == ["sharepoint-spec"]
    assert document["resources"][0]["name"] == "sharepoint-spec"
    assert document["resources"][0]["syncTarget"] == "path"


def test_fetch_source_path_upserts_descriptor_and_runs_fetch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    captured: dict[str, object] = {}

    def fake_fetch_resource_metadata_in_descriptor(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(resource_name="shared-specs", generated_resources=2, dry_run=False)

    monkeypatch.setattr(
        "sharedrive.cli.fetch_resource_metadata_in_descriptor",
        fake_fetch_resource_metadata_in_descriptor,
    )

    result = RUNNER.invoke(
        app,
        [
            "fetch",
            "--source-path",
            "https://example.sharepoint.com/sites/Test/Shared%20Documents/specs/",
            "--resource",
            "shared-specs",
        ],
        prog_name="sharedrive",
    )

    descriptor = tmp_path / "resources" / "descriptor.yaml"
    document = yaml.safe_load(descriptor.read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert captured["resource_name"] == "shared-specs"
    assert document["packages"][0]["name"] == "shared-specs"
    assert document["packages"][0]["syncTarget"] == "resources"


def test_removed_raw_adapter_commands_fail() -> None:
    for args in (
        ["gdrive", "list"],
        ["sharepoint", "get", "https://example.sharepoint.com/sites/Test/Shared%20Documents/spec.xlsx"],
        ["s3", "cp", "s3://bucket/file.csv", "resources/file.csv"],
    ):
        result = RUNNER.invoke(app, args, prog_name="sharedrive")
        assert result.exit_code != 0


def test_fetch_command_exits_nonzero_on_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)

    monkeypatch.setattr(
        "sharedrive.cli.fetch_resource_metadata_in_descriptor",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("Resource 'missing' was not found.")),
    )

    result = RUNNER.invoke(
        app,
        ["fetch", "missing", "--descriptor", str(descriptor)],
        prog_name="sharedrive",
    )

    assert result.exit_code == 1
    assert "was not found" in result.output


@pytest.mark.parametrize(
    "args",
    [
        ["sync", "census-package"],
        ["retrieve"],
        ["checkout", "resource", "spec-workbook"],
        ["checkout", "driveservice", "googledrive"],
        ["checkout", "show"],
        ["checkout", "clear"],
    ],
)
def test_removed_commands_fail(args: list[str]) -> None:
    result = RUNNER.invoke(app, args, prog_name="sharedrive")

    assert result.exit_code != 0


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


def test_add_uses_saved_global_descriptor_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    descriptor.write_text(
        "$schema: data-package-catalog\nresources: []\npackages: []\ncatalogs: []\n",
        encoding="utf-8",
    )

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