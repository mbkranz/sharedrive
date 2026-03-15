from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from sharedrive.actions.fetch import AuthCheckResult
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