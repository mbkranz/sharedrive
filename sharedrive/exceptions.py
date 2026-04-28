from __future__ import annotations

from typing import Any


class GoogleApiError(Exception):
    """Base exception for Google API failures."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_text: str | None = None,
        response_json: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text
        self.response_json = response_json


class GoogleAuthError(GoogleApiError):
    """Raised when Google credentials cannot be acquired or refreshed."""


class GoogleDriveError(GoogleApiError):
    """Raised when a Google Drive request fails."""


class GraphApiError(Exception):
    """Custom exception raised when fetching a SharePoint drive fails."""
    def __init__(self, message, status_code=None, response_text=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text

class GraphAuthError(GraphApiError):
    pass 

class GraphApiDriveError(GraphApiError):
    pass


class GraphApiSiteError(GraphApiError):
    pass


class S3Error(Exception):
    """Raised when an S3 operation fails."""

