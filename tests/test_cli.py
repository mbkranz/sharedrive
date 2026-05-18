from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from typer.testing import CliRunner

from sharedrive.catalog import AuthCheckResult
from sharedrive.cli import app
from sharedrive.exceptions import GoogleAuthError

RUNNER = CliRunner()


def _patch_catalog(
    monkeypatch: pytest.MonkeyPatch,
    module_path: str,
    *,
    captured: dict[str, object] | None = None,
    auth_result: object | None = None,
    download_result: object | None = None,
    fetch_result: object | None = None,
    auth_error: Exception | None = None,
    download_error: Exception | None = None,
    fetch_error: Exception | None = None,
) -> None:
    captured = captured if captured is not None else {}

    class _Catalog:
        def __init__(self, descriptor: Path) -> None:
            self.descriptor = descriptor

        def check_auth(self, selector=None, *, adapters=None):
            if auth_error is not None:
                raise auth_error
            captured["descriptor"] = self.descriptor
            if isinstance(selector, list):
                captured["selector"] = [
                    part.strip()
                    for value in selector
                    for part in value.split(",")
                    if part.strip()
                ]
            else:
                captured["selector"] = selector
            captured["adapters"] = adapters
            return auth_result

        def download(self, selector=None, **kwargs):
            if download_error is not None:
                raise download_error
            captured["descriptor"] = self.descriptor
            captured["selector"] = selector
            captured.update(kwargs)
            return download_result

        def fetch(self, selector=None, **kwargs):
            if fetch_error is not None:
                raise fetch_error
            captured["descriptor"] = self.descriptor
            captured["selector"] = selector
            captured.update(kwargs)
            return fetch_result

    monkeypatch.setattr(
        f"{module_path}.SharedriveCatalog.from_path", lambda path: _Catalog(Path(path))
    )


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
                    }
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


def test_auth_check_returns_json_and_passes_include(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    _patch_catalog(
        monkeypatch,
        "sharedrive.commands.auth",
        captured=captured,
        auth_result=[
            AuthCheckResult("googledrive", True, "Google Drive credentials are ready.")
        ],
    )

    result = RUNNER.invoke(
        app,
        [
            "auth",
            "check",
            str(descriptor),
            "--include",
            "googledrive",
            "--format",
            "json",
        ],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert '"adapter": "googledrive"' in result.stdout
    assert captured["selector"] == ["googledrive"]


def test_auth_check_parses_comma_separated_include(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    _patch_catalog(
        monkeypatch,
        "sharedrive.commands.auth",
        captured=captured,
        auth_result=[AuthCheckResult("googledrive", True, "ok")],
    )

    result = RUNNER.invoke(
        app,
        [
            "auth",
            "check",
            str(descriptor),
            "--include",
            "googledrive,sharepoint",
            "--format",
            "json",
        ],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert captured["selector"] == ["googledrive", "sharepoint"]


def test_auth_check_uses_checked_out_descriptor_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    _patch_catalog(
        monkeypatch,
        "sharedrive.commands.auth",
        captured=captured,
        auth_result=[
            AuthCheckResult("googledrive", True, "Google Drive credentials are ready.")
        ],
    )

    checkout_result = RUNNER.invoke(
        app, ["checkout", "resources/descriptor.yaml"], prog_name="sharedrive"
    )
    assert checkout_result.exit_code == 0

    result = RUNNER.invoke(
        app,
        ["auth", "check", "--include", "googledrive", "--format", "json"],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert captured["descriptor"] == Path("resources/descriptor.yaml")
    assert captured["selector"] == ["googledrive"]


def test_checkout_sets_global_descriptor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    _write_descriptor(descriptor)

    result = RUNNER.invoke(
        app, ["checkout", "resources/descriptor.yaml"], prog_name="sharedrive"
    )

    store = json.loads(
        (tmp_path / ".sharedrive" / "sharedrive_set.json").read_text(encoding="utf-8")
    )
    assert result.exit_code == 0
    assert store["global"]["descriptor"] == "resources/descriptor.yaml"


def test_checkout_rejects_missing_descriptor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    result = RUNNER.invoke(app, ["checkout", "missing.yaml"], prog_name="sharedrive")

    assert result.exit_code != 0
    assert "does not exist" in result.output


def test_auth_check_exits_nonzero_on_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)

    _patch_catalog(
        monkeypatch,
        "sharedrive.commands.auth",
        auth_result=[
            AuthCheckResult(
                "sharepoint", False, "SharePoint authentication failed: bad config"
            )
        ],
    )

    result = RUNNER.invoke(
        app, ["auth", "check", str(descriptor)], prog_name="sharedrive"
    )

    assert result.exit_code == 1
    assert "sharepoint: failed" in result.stdout.lower()


def test_auth_login_gdrive_uses_user_oauth_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class DummyConfig:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.oauth_token_path = kwargs.get("oauth_token_path")

        def to_auth(self):
            captured["build_called"] = True
            return object()

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

    class DummyConfig:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.auth_mode = SimpleNamespace(value=kwargs.get("auth_mode", "app_only"))
            self.host_url = kwargs.get("host_url", "norc.sharepoint.com")

        def to_auth(self):
            captured["build_called"] = True
            return object()

    monkeypatch.setattr("sharedrive.auth.settings.MicrosoftAuthConfig", DummyConfig)
    monkeypatch.setattr(
        "sharedrive.auth.settings.MicrosoftAuthMode", lambda value: value
    )

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

    class DummyConfig:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.auth_mode = SimpleNamespace(value=kwargs.get("auth_mode", "app_only"))
            self.host_url = kwargs.get("host_url", "norc.sharepoint.com")

        def to_auth(self):
            captured["build_called"] = True
            return object()

    monkeypatch.setattr("sharedrive.auth.settings.MicrosoftAuthConfig", DummyConfig)
    monkeypatch.setattr(
        "sharedrive.auth.settings.MicrosoftAuthMode", lambda value: value
    )

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


def test_download_passes_check_auth_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    _patch_catalog(
        monkeypatch,
        "sharedrive.commands.transfer",
        captured=captured,
        download_result=SimpleNamespace(ok=True),
    )

    result = RUNNER.invoke(
        app,
        ["download", "--descriptor", str(descriptor), "--check-auth", "--dry-run"],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert captured["check_auth"] is True


def test_download_defaults_to_all_when_include_is_omitted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    _patch_catalog(
        monkeypatch,
        "sharedrive.commands.transfer",
        captured=captured,
        download_result=SimpleNamespace(ok=True),
    )

    result = RUNNER.invoke(
        app,
        ["download", "my-package", "--descriptor", str(descriptor), "--dry-run"],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert captured["selector"] == "my-package"


def test_download_uses_checked_out_entity_and_saved_output_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    _patch_catalog(
        monkeypatch,
        "sharedrive.commands.transfer",
        captured=captured,
        download_result=SimpleNamespace(ok=True),
    )

    # checkout sets both the active descriptor and the checked-out entity
    checkout_result = RUNNER.invoke(
        app,
        ["checkout", "resources/descriptor.yaml", "my-package"],
        prog_name="sharedrive",
    )
    assert checkout_result.exit_code == 0

    # set provides defaults like output_dir (not selectors)
    set_result = RUNNER.invoke(
        app,
        ["set", "resources/descriptor.yaml", "--output-dir", "exports"],
        prog_name="sharedrive",
    )
    assert set_result.exit_code == 0

    result = RUNNER.invoke(
        app, ["download", "--check-auth", "--dry-run"], prog_name="sharedrive"
    )

    assert result.exit_code == 0
    assert captured["descriptor"] == Path("resources/descriptor.yaml")
    assert captured["output_dir"] == Path("exports")
    assert captured["check_auth"] is True
    assert captured["selector"] == "my-package"


def test_download_exits_nonzero_when_descriptor_is_missing(tmp_path: Path) -> None:
    descriptor = tmp_path / "missing.yaml"

    result = RUNNER.invoke(
        app,
        ["download", "my-package", "--descriptor", str(descriptor), "--dry-run"],
        prog_name="sharedrive",
    )

    assert result.exit_code == 1
    assert "does not exist" in result.output


def test_download_supports_json_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)

    _patch_catalog(
        monkeypatch,
        "sharedrive.commands.transfer",
        download_result=SimpleNamespace(
            total_resources=2,
            downloaded=1,
            skipped=0,
            dry_run_actions=1,
            failures=0,
            ok=True,
        ),
    )

    result = RUNNER.invoke(
        app,
        ["download", "--descriptor", str(descriptor), "--dry-run", "--format", "json"],
        prog_name="sharedrive",
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["descriptor"] == descriptor.as_posix()
    assert payload["summary"]["ok"] is True
    assert payload["summary"]["total_resources"] == 2


def test_fetch_passes_descriptor_and_dry_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    _patch_catalog(
        monkeypatch,
        "sharedrive.commands.transfer",
        captured=captured,
        fetch_result=[
            SimpleNamespace(
                resource_name="census-package", generated_resources=2, dry_run=True
            )
        ],
    )

    result = RUNNER.invoke(
        app,
        ["fetch", "census-package", "--descriptor", str(descriptor), "--dry-run"],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert captured["descriptor"] == descriptor
    assert captured["selector"] == "census-package"
    assert captured["dry_run"] is True
    assert "googledrive_client_factory" not in captured
    assert "sharepoint_client_factory" not in captured


def test_fetch_supports_json_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)

    _patch_catalog(
        monkeypatch,
        "sharedrive.commands.transfer",
        fetch_result=[
            SimpleNamespace(
                resource_name="research",
                generated_resources=3,
                dry_run=True,
                changed=False,
                failures=0,
                errors=[],
                ok=True,
            )
        ],
    )

    result = RUNNER.invoke(
        app,
        ["fetch", "--descriptor", str(descriptor), "--dry-run", "--format", "json"],
        prog_name="sharedrive",
    )

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["descriptor"] == descriptor.as_posix()
    assert payload["summaries"][0]["resource_name"] == "research"
    assert payload["summaries"][0]["generated_resources"] == 3


def test_fetch_uses_checked_out_descriptor_when_omitted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    _patch_catalog(
        monkeypatch,
        "sharedrive.commands.transfer",
        captured=captured,
        fetch_result=[
            SimpleNamespace(
                resource_name="census-package", generated_resources=1, dry_run=True
            )
        ],
    )

    checkout_result = RUNNER.invoke(
        app, ["checkout", "resources/descriptor.yaml"], prog_name="sharedrive"
    )
    assert checkout_result.exit_code == 0

    result = RUNNER.invoke(
        app, ["fetch", "census-package", "--dry-run"], prog_name="sharedrive"
    )

    assert result.exit_code == 0
    assert captured["descriptor"] == Path("resources/descriptor.yaml")


def test_fetch_uses_checked_out_entity_when_selector_omitted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    _patch_catalog(
        monkeypatch,
        "sharedrive.commands.transfer",
        captured=captured,
        fetch_result=[
            SimpleNamespace(
                resource_name="nested-package", generated_resources=1, dry_run=True
            )
        ],
    )

    checkout_result = RUNNER.invoke(
        app,
        ["checkout", "resources/descriptor.yaml", "archived.nested-package"],
        prog_name="sharedrive",
    )
    assert checkout_result.exit_code == 0

    result = RUNNER.invoke(app, ["fetch", "--dry-run"], prog_name="sharedrive")

    assert result.exit_code == 0
    assert captured["descriptor"] == Path("resources/descriptor.yaml")
    assert captured["selector"] == "archived.nested-package"


def test_checkout_with_entity_stores_entity_and_bare_checkout_clears_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    _write_descriptor(descriptor)

    result = RUNNER.invoke(
        app,
        ["checkout", "resources/descriptor.yaml", "research.archive"],
        prog_name="sharedrive",
    )
    assert result.exit_code == 0
    store = json.loads(
        (tmp_path / ".sharedrive" / "sharedrive_set.json").read_text(encoding="utf-8")
    )
    assert store["global"]["entity"] == "research.archive"
    assert "research.archive" in result.output

    # A bare checkout (no entity) should clear the stored entity
    result2 = RUNNER.invoke(
        app, ["checkout", "resources/descriptor.yaml"], prog_name="sharedrive"
    )
    assert result2.exit_code == 0
    store2 = json.loads(
        (tmp_path / ".sharedrive" / "sharedrive_set.json").read_text(encoding="utf-8")
    )
    assert "entity" not in store2["global"]


def test_fetch_with_selector_arg_prepends_checked_out_entity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    _patch_catalog(
        monkeypatch,
        "sharedrive.commands.transfer",
        captured=captured,
        fetch_result=[
            SimpleNamespace(
                resource_name="archive", generated_resources=1, dry_run=False
            )
        ],
    )

    RUNNER.invoke(
        app,
        ["checkout", "resources/descriptor.yaml", "research"],
        prog_name="sharedrive",
    )

    result = RUNNER.invoke(
        app,
        ["fetch", "archive", "--descriptor", str(descriptor)],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert captured["selector"] == "research.archive"


def test_fetch_with_comma_selector_arg_scopes_each_selector(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    _patch_catalog(
        monkeypatch,
        "sharedrive.commands.transfer",
        captured=captured,
        fetch_result=[
            SimpleNamespace(
                resource_name="archive", generated_resources=1, dry_run=False
            )
        ],
    )
    RUNNER.invoke(
        app,
        ["checkout", "resources/descriptor.yaml", "research"],
        prog_name="sharedrive",
    )

    result = RUNNER.invoke(
        app,
        ["fetch", "archive,nested-package", "--descriptor", str(descriptor)],
        prog_name="sharedrive",
    )

    assert result.exit_code == 0
    assert captured["selector"] == "research.archive,research.nested-package"


def test_fetch_selector_all_ignores_checked_out_entity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    _patch_catalog(
        monkeypatch,
        "sharedrive.commands.transfer",
        captured=captured,
        fetch_result=[
            SimpleNamespace(resource_name="root", generated_resources=1, dry_run=False)
        ],
    )
    RUNNER.invoke(
        app,
        ["checkout", "resources/descriptor.yaml", "research"],
        prog_name="sharedrive",
    )

    result = RUNNER.invoke(
        app, ["fetch", "all", "--descriptor", str(descriptor)], prog_name="sharedrive"
    )

    assert result.exit_code == 0
    assert captured["selector"] is None


def test_fetch_without_entity_and_without_selector_fetches_from_descriptor_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    _write_descriptor(descriptor)
    captured: dict[str, object] = {}

    _patch_catalog(
        monkeypatch,
        "sharedrive.commands.transfer",
        captured=captured,
        fetch_result=[
            SimpleNamespace(
                resource_name="census-package", generated_resources=1, dry_run=False
            )
        ],
    )

    # Ensure no entity is checked out
    RUNNER.invoke(
        app, ["checkout", "resources/descriptor.yaml"], prog_name="sharedrive"
    )

    result = RUNNER.invoke(
        app, ["fetch", "--descriptor", str(descriptor)], prog_name="sharedrive"
    )

    assert result.exit_code == 0
    assert captured["selector"] is None
    assert "Fetching all metadata" in result.output


def test_list_command_renders_descriptor_tree_with_paths_and_sources(
    tmp_path: Path,
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)

    result = RUNNER.invoke(app, ["list", str(descriptor)], prog_name="sharedrive")

    assert result.exit_code == 0
    assert descriptor.name in result.output
    assert "sharepoint-spec (resource)" in result.output
    assert "sharepoint-spec /resources/0" in result.output
    assert "path=downloads/spec.xlsx" in result.output
    assert "archived.nested-package /catalogs/0/packages/0" in result.output


def test_list_command_supports_json_output(tmp_path: Path) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)

    result = RUNNER.invoke(
        app, ["list", str(descriptor), "--format", "json"], prog_name="sharedrive"
    )

    payload = json.loads(result.output)
    entity_paths = {entity["path"]: entity for entity in payload["entities"]}

    assert result.exit_code == 0
    assert payload["descriptor"] == descriptor.as_posix()
    assert entity_paths["drive-export"]["jsonPointer"] == "/resources/1"
    assert entity_paths["drive-export"]["resourcePath"] == "downloads/export.csv"
    assert entity_paths["archived.nested-package"]["type"] == "package"


def test_removed_raw_adapter_commands_fail() -> None:
    for args in (
        ["gdrive", "list"],
        [
            "sharepoint",
            "get",
            "https://example.sharepoint.com/sites/Test/Shared%20Documents/spec.xlsx",
        ],
        ["s3", "cp", "s3://bucket/file.csv", "resources/file.csv"],
    ):
        result = RUNNER.invoke(app, args, prog_name="sharedrive")
        assert result.exit_code != 0


def test_fetch_command_exits_nonzero_on_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)

    _patch_catalog(
        monkeypatch,
        "sharedrive.commands.transfer",
        fetch_error=ValueError("Entity 'missing' was not found in descriptor."),
    )

    result = RUNNER.invoke(
        app,
        ["fetch", "missing", "--descriptor", str(descriptor)],
        prog_name="sharedrive",
    )

    assert result.exit_code == 1
    assert "was not found" in result.output


def test_fetch_command_exits_nonzero_on_auth_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "descriptor.yaml"
    _write_descriptor(descriptor)

    _patch_catalog(
        monkeypatch,
        "sharedrive.commands.transfer",
        fetch_error=GoogleAuthError("Failed during user OAuth flow: invalid_grant"),
    )

    result = RUNNER.invoke(
        app,
        ["fetch", "census-package", "--descriptor", str(descriptor)],
        prog_name="sharedrive",
    )

    assert result.exit_code == 1
    assert "invalid_grant" in result.output


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


def test_set_command_saves_global_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    descriptor = tmp_path / "resources" / "descriptor.yaml"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    _write_descriptor(descriptor)

    result = RUNNER.invoke(
        app,
        [
            "set",
            "--global",
            "--descriptor",
            "resources/descriptor.yaml",
            "--output-dir",
            "exports",
        ],
        prog_name="sharedrive",
    )

    store_path = tmp_path / ".sharedrive" / "sharedrive_set.json"
    store = json.loads(store_path.read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert store == {
        "global": {"descriptor": "resources/descriptor.yaml", "output_dir": "exports"},
        "descriptors": {},
    }


def test_add_uses_saved_global_descriptor_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
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
