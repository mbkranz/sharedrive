from __future__ import annotations

from pathlib import Path

import requests
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request

from sharedrive.auth.base import CredentialStrategy
from sharedrive.exceptions import GoogleApiError, GoogleAuthError


class GoogleBaseClient:
    """Shared Google client base for auth lifecycle and HTTP transport helpers."""

    api_error_cls = GoogleApiError

    def __init__(
        self,
        *,
        credential_strategy: CredentialStrategy | None = None,
        credentials: Credentials | None = None,
        session: requests.Session | None = None,
        timeout: int = 120,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout

        if credentials is not None and credential_strategy is not None:
            raise ValueError(
                "Provide either credentials or credential_strategy, not both."
            )

        self._credential_strategy = credential_strategy

        if credentials is not None:
            self._creds = credentials
        elif self._credential_strategy is not None:
            self._creds = self._credential_strategy.build()
        else:
            raise ValueError(
                "GoogleBaseClient requires either credentials or credential_strategy."
            )

    def _ensure_valid_credentials(self) -> None:
        if self._creds.valid and self._creds.token:
            return

        try:
            self._creds.refresh(Request())
        except Exception as refresh_error:
            if self._credential_strategy is None:
                raise GoogleAuthError(
                    f"Failed to refresh Google credentials: {refresh_error}"
                ) from refresh_error
            try:
                self._creds = self._credential_strategy.build()
            except Exception as build_error:
                raise GoogleAuthError(
                    f"Failed to obtain valid Google credentials: {build_error}"
                ) from build_error

        if not self._creds.valid or not self._creds.token:
            raise GoogleAuthError("Credentials are missing a valid access token.")

    @property
    def _hdrs(self) -> dict[str, str]:
        self._ensure_valid_credentials()
        return {"Authorization": f"Bearer {self._creds.token}"}

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        headers = kwargs.pop("headers", {})
        merged_headers = {**self._hdrs, **headers}

        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=merged_headers,
                timeout=self.timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise self.api_error_cls(f"HTTP request failed: {exc}") from exc

        if response.ok:
            return response

        try:
            payload = response.json()
        except ValueError:
            payload = None

        message = f"Google API request failed with status {response.status_code}"
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict) and error.get("message"):
                message = f"{message}: {error['message']}"

        raise self.api_error_cls(
            message,
            status_code=response.status_code,
            response_text=response.text,
            response_json=payload,
        )

    @staticmethod
    def _write_stream_to_path(resp: requests.Response, output_path: str | Path) -> str:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as handle:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
        return str(destination)

    @staticmethod
    def _read_stream_to_bytes(resp: requests.Response) -> bytes:
        return b"".join(
            chunk for chunk in resp.iter_content(chunk_size=1024 * 1024) if chunk
        )
