from __future__ import annotations

import pytest

from sharedrive.auth.microsoft import (
    AppOnlyStrategy,
    DEFAULT_MICROSOFT_GRAPH_SCOPES,
    DelegatedStrategy,
    normalize_microsoft_scopes,
)
from sharedrive.auth.sharepoint import normalize_sharepoint_scopes
from sharedrive.exceptions import GraphAuthError


def test_normalize_microsoft_scopes_supports_none_string_and_sequence() -> None:
    assert normalize_microsoft_scopes(None) == list(DEFAULT_MICROSOFT_GRAPH_SCOPES)
    assert normalize_microsoft_scopes("scope-a, scope-b") == ["scope-a", "scope-b"]
    assert normalize_microsoft_scopes(["scope-a", "scope-b"]) == ["scope-a", "scope-b"]


def test_sharepoint_scope_normalizer_is_compatibility_alias() -> None:
    assert normalize_sharepoint_scopes("scope-a, scope-b") == ["scope-a", "scope-b"]


def test_delegated_strategy_uses_interactive_flow_when_no_cached_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class DummyApp:
        def get_accounts(self):
            return []

        def acquire_token_interactive(self, scopes):
            captured["scopes"] = scopes
            return {"access_token": "delegated-token"}

    monkeypatch.setattr(
        "sharedrive.auth.microsoft.msal.PublicClientApplication",
        lambda client_id, authority: DummyApp(),
    )

    strategy = DelegatedStrategy(tenant_id="tenant", client_id="client", scopes=["scope-a"])

    assert strategy.build() == "delegated-token"
    assert captured["scopes"] == ["scope-a"]


def test_app_only_strategy_uses_confidential_client(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class DummyApp:
        def acquire_token_for_client(self, scopes):
            captured["scopes"] = scopes
            return {"access_token": "app-token"}

    monkeypatch.setattr(
        "sharedrive.auth.microsoft.msal.ConfidentialClientApplication",
        lambda **kwargs: DummyApp(),
    )

    strategy = AppOnlyStrategy(
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        scopes=["scope-a"],
    )

    assert strategy.build() == "app-token"
    assert captured["scopes"] == ["scope-a"]


def test_app_only_strategy_requires_secret() -> None:
    strategy = AppOnlyStrategy(tenant_id="tenant", client_id="client", client_secret=None)

    with pytest.raises(GraphAuthError):
        strategy.build()