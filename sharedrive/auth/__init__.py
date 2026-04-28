from sharedrive.auth.google import (
    DEFAULT_DRIVE_READONLY_SCOPES,
    DEFAULT_DRIVE_SCOPES,
    GoogleAuth,
    normalize_google_scopes,
)
from sharedrive.auth.microsoft import (
    DEFAULT_MICROSOFT_GRAPH_SCOPES,
    MicrosoftAuth,
    normalize_microsoft_scopes,
)
from sharedrive.auth.settings import (
    GoogleAuthConfig,
    GoogleAuthMode,
    MicrosoftAuthConfig,
    MicrosoftAuthMode,
)
from sharedrive.auth.token_store import JsonTokenStore, TokenStore

DEFAULT_SHAREPOINT_SCOPES = DEFAULT_MICROSOFT_GRAPH_SCOPES
normalize_sharepoint_scopes = normalize_microsoft_scopes

__all__ = [
    "DEFAULT_DRIVE_READONLY_SCOPES",
    "DEFAULT_DRIVE_SCOPES",
    "DEFAULT_MICROSOFT_GRAPH_SCOPES",
    "DEFAULT_SHAREPOINT_SCOPES",
    "GoogleAuth",
    "GoogleAuthConfig",
    "GoogleAuthMode",
    "JsonTokenStore",
    "MicrosoftAuth",
    "MicrosoftAuthConfig",
    "MicrosoftAuthMode",
    "TokenStore",
    "normalize_google_scopes",
    "normalize_microsoft_scopes",
    "normalize_sharepoint_scopes",
]
