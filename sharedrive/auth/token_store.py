from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from google.auth.credentials import Credentials
from google.oauth2.credentials import Credentials as UserCredentials

from sharedrive.exceptions import GoogleAuthError


@runtime_checkable
class TokenStore(Protocol):
    def load(self) -> Credentials | None:
        ...

    def save(self, creds: Credentials) -> None:
        ...


class JsonTokenStore:
    """Persist authorized-user OAuth credentials as JSON on disk."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> Credentials | None:
        if not self.path.exists():
            return None

        try:
            return UserCredentials.from_authorized_user_file(str(self.path))
        except Exception as exc:  # pragma: no cover - defensive path
            raise GoogleAuthError(
                f"Failed to load OAuth token from {self.path}: {exc}"
            ) from exc

    def save(self, creds: Credentials) -> None:
        if not isinstance(creds, UserCredentials):
            raise GoogleAuthError(
                "JSON token storage only supports authorized-user OAuth credentials."
            )

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(creds.to_json(), encoding="utf-8")


__all__ = ["JsonTokenStore", "TokenStore"]
