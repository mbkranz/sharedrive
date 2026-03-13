from __future__ import annotations

from pathlib import Path

import pytest
from google.oauth2.credentials import Credentials as UserCredentials

from sharedrive.auth.google import (
    AdcStrategy,
    ChainedStrategy,
    ServiceAccountStrategy,
    UserOAuthStrategy,
    default_drive_strategy,
    normalize_google_scopes,
)
from sharedrive.auth.token_store import JsonTokenStore
from sharedrive.exceptions import GoogleAuthError


class DummyCreds:
    def __init__(self, *, valid: bool = True, token: str | None = "token") -> None:
        self.valid = valid
        self.token = token
        self.expired = not valid
        self.refresh_count = 0

    def refresh(self, _request) -> None:
        self.refresh_count += 1
        self.valid = True
        self.expired = False
        self.token = "refreshed-token"


class DummyStore:
    def __init__(self, creds=None):
        self.creds = creds
        self.saved = []

    def load(self):
        return self.creds

    def save(self, creds) -> None:
        self.saved.append(creds)


class FailStrategy:
    def build(self):
        raise GoogleAuthError("nope")


class SuccessStrategy:
    def __init__(self, creds):
        self.creds = creds

    def build(self):
        return self.creds


def test_normalize_google_scopes_supports_none_string_and_sequence() -> None:
    assert normalize_google_scopes(None) == ["https://www.googleapis.com/auth/drive"]
    assert normalize_google_scopes("scope-a") == ["scope-a"]
    assert normalize_google_scopes(["scope-a", "scope-b"]) == [
        "scope-a",
        "scope-b",
    ]


def test_default_drive_strategy_selects_expected_strategy_types() -> None:
    assert isinstance(default_drive_strategy(), AdcStrategy)
    assert isinstance(
        default_drive_strategy(credentials_path="service-account.json"),
        ServiceAccountStrategy,
    )


def test_json_token_store_round_trip(tmp_path: Path) -> None:
    token_path = tmp_path / "token.json"
    store = JsonTokenStore(token_path)
    creds = UserCredentials.from_authorized_user_info(
        {
            "client_id": "client-id",
            "client_secret": "client-secret",
            "refresh_token": "refresh-token",
            "token": "access-token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": ["https://www.googleapis.com/auth/drive.readonly"],
        }
    )

    store.save(creds)
    loaded = store.load()

    assert loaded is not None
    assert loaded.refresh_token == "refresh-token"
    assert loaded.client_id == "client-id"


def test_user_oauth_strategy_returns_valid_stored_credentials() -> None:
    creds = DummyCreds(valid=True)
    store = DummyStore(creds)
    strategy = UserOAuthStrategy(
        client_secrets_path="oauth.json",
        scopes=["scope-a"],
        token_store=store,
    )

    assert strategy.build() is creds
    assert store.saved == []


def test_user_oauth_strategy_refreshes_expired_credentials() -> None:
    creds = DummyCreds(valid=False, token=None)
    creds.refresh_token = "refresh-token"
    store = DummyStore(creds)
    strategy = UserOAuthStrategy(
        client_secrets_path="oauth.json",
        scopes=["scope-a"],
        token_store=store,
    )

    result = strategy.build()

    assert result is creds
    assert creds.refresh_count == 1
    assert store.saved == [creds]


def test_user_oauth_strategy_runs_flow_when_store_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    issued_creds = DummyCreds(valid=True)
    store = DummyStore()

    class DummyFlow:
        def run_local_server(self, port: int = 0):
            assert port == 0
            return issued_creds

    monkeypatch.setattr(
        "sharedrive.auth.google.InstalledAppFlow.from_client_secrets_file",
        lambda path, scopes: DummyFlow(),
    )

    strategy = UserOAuthStrategy(
        client_secrets_path="oauth.json",
        scopes=["scope-a"],
        token_store=store,
    )

    assert strategy.build() is issued_creds
    assert store.saved == [issued_creds]


def test_chained_strategy_returns_first_successful_credentials() -> None:
    creds = DummyCreds(valid=True)
    strategy = ChainedStrategy([FailStrategy(), SuccessStrategy(creds)])

    assert strategy.build() is creds


def test_chained_strategy_raises_when_all_fail() -> None:
    strategy = ChainedStrategy([FailStrategy(), FailStrategy()])

    with pytest.raises(GoogleAuthError):
        strategy.build()
