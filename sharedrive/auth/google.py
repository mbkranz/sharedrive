from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import google.auth
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow

from sharedrive.auth.base import CredentialStrategy, TokenStore
from sharedrive.exceptions import GoogleAuthError

DEFAULT_DRIVE_SCOPES = ("https://www.googleapis.com/auth/drive",)
DEFAULT_DRIVE_READONLY_SCOPES = (
    "https://www.googleapis.com/auth/drive.readonly",
)


def normalize_google_scopes(
    scopes: Sequence[str] | str | None,
    *,
    default: Sequence[str] = DEFAULT_DRIVE_SCOPES,
) -> list[str]:
    if scopes is None:
        return list(default)
    if isinstance(scopes, str):
        return [scopes]
    normalized = [scope for scope in scopes if scope]
    return normalized or list(default)


@dataclass(slots=True)
class AdcStrategy(CredentialStrategy):
    scopes: Sequence[str] | str | None = None

    def build(self) -> Credentials:
        normalized_scopes = normalize_google_scopes(self.scopes)
        try:
            creds, _project = google.auth.default(scopes=normalized_scopes)
            if getattr(creds, "requires_scopes", False) and hasattr(
                creds, "with_scopes"
            ):
                creds = creds.with_scopes(normalized_scopes)
            return creds
        except Exception as exc:
            raise GoogleAuthError(
                f"Failed to load Application Default Credentials: {exc}"
            ) from exc


@dataclass(slots=True)
class ServiceAccountStrategy(CredentialStrategy):
    credentials_path: str | Path
    scopes: Sequence[str] | str | None = None

    def build(self) -> Credentials:
        normalized_scopes = normalize_google_scopes(self.scopes)
        try:
            return service_account.Credentials.from_service_account_file(
                str(self.credentials_path),
                scopes=normalized_scopes,
            )
        except Exception as exc:
            raise GoogleAuthError(
                f"Failed to load service account credentials from {self.credentials_path}: {exc}"
            ) from exc


@dataclass(slots=True)
class UserOAuthStrategy(CredentialStrategy):
    client_secrets_path: str | Path
    scopes: Sequence[str] | str | None = None
    token_store: TokenStore | None = None
    use_local_server: bool = True

    def build(self) -> Credentials:
        normalized_scopes = normalize_google_scopes(self.scopes)
        creds = self.token_store.load() if self.token_store else None

        try:
            if creds and creds.valid:
                return creds

            if creds and getattr(creds, "expired", False):
                creds.refresh(Request())
                if self.token_store:
                    self.token_store.save(creds)
                return creds

            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.client_secrets_path),
                normalized_scopes,
            )
            if self.use_local_server:
                creds = flow.run_local_server(port=0)
            else:
                creds = flow.run_console()

            if self.token_store:
                self.token_store.save(creds)
            return creds
        except Exception as exc:
            raise GoogleAuthError(f"Failed during user OAuth flow: {exc}") from exc


@dataclass(slots=True)
class ChainedStrategy(CredentialStrategy):
    strategies: Sequence[CredentialStrategy]

    def build(self) -> Credentials:
        errors: list[str] = []
        for strategy in self.strategies:
            try:
                return strategy.build()
            except Exception as exc:
                errors.append(f"{strategy.__class__.__name__}: {exc}")

        details = "; ".join(errors) if errors else "No strategies were provided."
        raise GoogleAuthError(f"All credential strategies failed. Details: {details}")


def default_drive_strategy(
    credentials_path: str | Path | None = None,
    scopes: Sequence[str] | str | None = None,
) -> CredentialStrategy:
    if credentials_path:
        return ServiceAccountStrategy(
            credentials_path=credentials_path,
            scopes=normalize_google_scopes(scopes),
        )
    return AdcStrategy(scopes=normalize_google_scopes(scopes))
