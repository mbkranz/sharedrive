from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from sharedrive.auth.google import AdcStrategy, ServiceAccountStrategy, UserOAuthStrategy
from sharedrive.auth.settings import (
    GoogleAuthConfig,
    GoogleAuthMode,
    make_google_drive_client_from_settings,
)
from sharedrive.auth.token_store import JsonTokenStore


def _clear_google_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "GOOGLE_AUTH_MODE",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS",
        "GOOGLE_OAUTH_CREDENTIALS",
        "GOOGLE_OAUTH_TOKEN_PATH",
        "GOOGLE_SCOPES",
        "GOOGLE_OAUTH_USE_LOCAL_SERVER",
    ):
        monkeypatch.delenv(name, raising=False)


def test_google_auth_config_defaults_to_adc_strategy(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_google_auth_env(monkeypatch)
    config = GoogleAuthConfig(_env_file=None)

    strategy = config.to_strategy()

    assert config.auth_mode == GoogleAuthMode.ADC
    assert isinstance(strategy, AdcStrategy)


def test_google_auth_config_normalizes_comma_separated_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_google_auth_env(monkeypatch)
    config = GoogleAuthConfig(scopes="scope-a, scope-b", _env_file=None)

    assert config.scopes == ["scope-a", "scope-b"]


def test_google_auth_config_supports_service_account_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_google_auth_env(monkeypatch)
    config = GoogleAuthConfig(
        auth_mode=GoogleAuthMode.SERVICE_ACCOUNT,
        GOOGLE_APPLICATION_CREDENTIALS="service-account.json",
        _env_file=None,
    )

    strategy = config.to_strategy()

    assert isinstance(strategy, ServiceAccountStrategy)
    assert strategy.credentials_path == Path("service-account.json")


def test_google_auth_config_requires_service_account_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_google_auth_env(monkeypatch)
    with pytest.raises(ValidationError):
        GoogleAuthConfig(auth_mode=GoogleAuthMode.SERVICE_ACCOUNT, _env_file=None)


def test_google_auth_config_requires_oauth_secrets_for_user_oauth(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_google_auth_env(monkeypatch)
    with pytest.raises(ValidationError):
        GoogleAuthConfig(auth_mode=GoogleAuthMode.USER_OAUTH, _env_file=None)


def test_google_auth_config_builds_user_oauth_strategy_with_token_store(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_google_auth_env(monkeypatch)
    config = GoogleAuthConfig(
        auth_mode=GoogleAuthMode.USER_OAUTH,
        oauth_client_secrets=Path("oauth-client.json"),
        oauth_token_path=Path("oauth-token.json"),
        scopes=["scope-a"],
        use_local_server=False,
        _env_file=None,
    )

    strategy = config.to_strategy()

    assert isinstance(strategy, UserOAuthStrategy)
    assert isinstance(strategy.token_store, JsonTokenStore)
    assert strategy.client_secrets_path == Path("oauth-client.json")
    assert strategy.use_local_server is False


def test_google_auth_config_builds_user_oauth_strategy_without_token_store(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_google_auth_env(monkeypatch)
    config = GoogleAuthConfig(
        auth_mode=GoogleAuthMode.USER_OAUTH,
        oauth_client_secrets=Path("oauth-client.json"),
        _env_file=None,
    )

    strategy = config.to_strategy()

    assert isinstance(strategy, UserOAuthStrategy)
    assert strategy.token_store is None


def test_make_google_drive_client_from_settings_uses_strategy(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_google_auth_env(monkeypatch)
    captured: dict[str, object] = {}

    class DummyClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("sharedrive.clients.google.GoogleDriveClient", DummyClient)

    config = GoogleAuthConfig(auth_mode=GoogleAuthMode.ADC, _env_file=None)
    make_google_drive_client_from_settings(config)

    assert isinstance(captured["credential_strategy"], AdcStrategy)
