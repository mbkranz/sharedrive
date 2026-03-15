from __future__ import annotations

import pytest
from pydantic import ValidationError

from sharedrive.auth.settings import (
    MicrosoftAuthConfig,
    MicrosoftAuthMode,
    make_sharepoint_client_from_microsoft_auth,
    make_sharepoint_client_from_settings,
)
from sharedrive.auth.microsoft import AppOnlyStrategy, DelegatedStrategy


def _clear_sharepoint_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "SHAREPOINT_AUTH_MODE",
        "AZURE_TENANT_ID",
        "AZURE_CLIENT_ID",
        "AZURE_CLIENT_SECRET",
        "SHAREPOINT_HOST_URL",
        "SHAREPOINT_SCOPES",
        "AZURE_HOST_URL",
        "AZURE_SCOPES",
    ):
        monkeypatch.delenv(name, raising=False)


def test_sharepoint_auth_config_defaults_to_app_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_sharepoint_auth_env(monkeypatch)
    config = MicrosoftAuthConfig(
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        _env_file=None,
    )

    strategy = config.to_strategy()

    assert config.auth_mode == MicrosoftAuthMode.APP_ONLY
    assert isinstance(strategy, AppOnlyStrategy)


def test_sharepoint_auth_config_normalizes_scope_string(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_sharepoint_auth_env(monkeypatch)
    config = MicrosoftAuthConfig(
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        scopes="scope-a, scope-b",
        _env_file=None,
    )

    assert config.scopes == ["scope-a", "scope-b"]


def test_sharepoint_auth_config_requires_secret_for_app_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_sharepoint_auth_env(monkeypatch)
    with pytest.raises(ValidationError):
        MicrosoftAuthConfig(
            tenant_id="tenant",
            client_id="client",
            auth_mode=MicrosoftAuthMode.APP_ONLY,
            _env_file=None,
        )


def test_sharepoint_auth_config_builds_delegated_strategy(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_sharepoint_auth_env(monkeypatch)
    config = MicrosoftAuthConfig(
        tenant_id="tenant",
        client_id="client",
        auth_mode=MicrosoftAuthMode.DELEGATED,
        _env_file=None,
    )

    strategy = config.to_strategy()

    assert isinstance(strategy, DelegatedStrategy)


def test_make_sharepoint_client_from_settings_uses_strategy(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_sharepoint_auth_env(monkeypatch)
    captured: dict[str, object] = {}

    class DummyClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("sharedrive.clients.sharepoint.SharepointClient", DummyClient)

    config = MicrosoftAuthConfig(
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        host_url="tenant.sharepoint.com",
        _env_file=None,
    )
    make_sharepoint_client_from_microsoft_auth(config)

    assert str(captured["host_url"]) == "tenant.sharepoint.com"
    assert isinstance(captured["token_strategy"], AppOnlyStrategy)


def test_make_sharepoint_client_from_settings_is_compatibility_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_sharepoint_auth_env(monkeypatch)
    captured: dict[str, object] = {}

    class DummyClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("sharedrive.clients.sharepoint.SharepointClient", DummyClient)

    config = MicrosoftAuthConfig(
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        host_url="tenant.sharepoint.com",
        _env_file=None,
    )
    make_sharepoint_client_from_settings(config)

    assert str(captured["host_url"]) == "tenant.sharepoint.com"
    assert isinstance(captured["token_strategy"], AppOnlyStrategy)


def test_sharepoint_auth_config_aliases_microsoft_config(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_sharepoint_auth_env(monkeypatch)

    from sharedrive.auth.settings import SharepointAuthConfig, SharepointAuthMode

    config = SharepointAuthConfig(
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        _env_file=None,
    )

    assert isinstance(config, MicrosoftAuthConfig)
    assert SharepointAuthMode is MicrosoftAuthMode