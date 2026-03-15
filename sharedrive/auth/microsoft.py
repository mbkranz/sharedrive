from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import msal

from sharedrive.exceptions import GraphAuthError

DEFAULT_MICROSOFT_GRAPH_SCOPES = ("https://graph.microsoft.com/.default",)


def normalize_microsoft_scopes(
    scopes: Sequence[str] | str | None,
    *,
    default: Sequence[str] = DEFAULT_MICROSOFT_GRAPH_SCOPES,
) -> list[str]:
    if scopes is None:
        return list(default)
    if isinstance(scopes, str):
        normalized = [scope.strip() for scope in scopes.split(",") if scope.strip()]
        return normalized or list(default)
    normalized = [scope for scope in scopes if scope]
    return normalized or list(default)


def _extract_access_token(result: dict[str, object]) -> str:
    token = result.get("access_token")
    if isinstance(token, str) and token:
        return token
    raise GraphAuthError(f"Token error: {result.get('error_description')}")


@dataclass(slots=True)
class MicrosoftTokenStrategy:
    tenant_id: str
    client_id: str
    scopes: Sequence[str] | str | None = None

    @property
    def normalized_scopes(self) -> list[str]:
        return normalize_microsoft_scopes(self.scopes)


@dataclass(slots=True)
class DelegatedStrategy(MicrosoftTokenStrategy):
    def build(self) -> str:
        authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        app = msal.PublicClientApplication(self.client_id, authority=authority)
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(self.normalized_scopes, account=accounts[0])
            if result and "access_token" in result:
                return _extract_access_token(result)
        result = app.acquire_token_interactive(scopes=self.normalized_scopes)
        return _extract_access_token(result)


@dataclass(slots=True)
class AppOnlyStrategy(MicrosoftTokenStrategy):
    client_secret: str | None = None

    def build(self) -> str:
        if not self.client_secret:
            raise GraphAuthError(
                "AZURE_CLIENT_SECRET is required for Microsoft app_only mode."
            )

        authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        app = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=authority,
        )
        result = app.acquire_token_for_client(scopes=self.normalized_scopes)
        return _extract_access_token(result)


__all__ = [
    "AppOnlyStrategy",
    "DEFAULT_MICROSOFT_GRAPH_SCOPES",
    "DelegatedStrategy",
    "MicrosoftTokenStrategy",
    "normalize_microsoft_scopes",
]