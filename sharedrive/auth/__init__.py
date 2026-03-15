from sharedrive.auth.base import CredentialStrategy, TokenStore
from sharedrive.auth.google import (
    DEFAULT_DRIVE_READONLY_SCOPES,
    DEFAULT_DRIVE_SCOPES,
    AdcStrategy,
    ChainedStrategy,
    ServiceAccountStrategy,
    UserOAuthStrategy,
    default_drive_strategy,
    normalize_google_scopes,
)
from sharedrive.auth.microsoft import (
    AppOnlyStrategy,
    DEFAULT_MICROSOFT_GRAPH_SCOPES,
    DelegatedStrategy,
    MicrosoftTokenStrategy,
    normalize_microsoft_scopes,
)
from sharedrive.auth.settings import (
    GoogleAuthConfig,
    GoogleAuthMode,
    MicrosoftAuthConfig,
    MicrosoftAuthMode,
    SharepointAuthConfig,
    SharepointAuthMode,
    make_google_drive_client_from_settings,
    make_sharepoint_client_from_microsoft_auth,
    make_sharepoint_client_from_settings,
)
from sharedrive.auth.token_store import JsonTokenStore

DEFAULT_SHAREPOINT_SCOPES = DEFAULT_MICROSOFT_GRAPH_SCOPES
SharepointTokenStrategy = MicrosoftTokenStrategy
normalize_sharepoint_scopes = normalize_microsoft_scopes

__all__ = [
    "AppOnlyStrategy",
    "AdcStrategy",
    "ChainedStrategy",
    "CredentialStrategy",
    "DEFAULT_DRIVE_READONLY_SCOPES",
    "DEFAULT_DRIVE_SCOPES",
    "DEFAULT_MICROSOFT_GRAPH_SCOPES",
    "DEFAULT_SHAREPOINT_SCOPES",
    "DelegatedStrategy",
    "GoogleAuthConfig",
    "GoogleAuthMode",
    "JsonTokenStore",
    "MicrosoftAuthConfig",
    "MicrosoftAuthMode",
    "MicrosoftTokenStrategy",
    "SharepointAuthConfig",
    "SharepointAuthMode",
    "SharepointTokenStrategy",
    "ServiceAccountStrategy",
    "TokenStore",
    "UserOAuthStrategy",
    "default_drive_strategy",
    "make_google_drive_client_from_settings",
    "make_sharepoint_client_from_microsoft_auth",
    "make_sharepoint_client_from_settings",
    "normalize_google_scopes",
    "normalize_microsoft_scopes",
    "normalize_sharepoint_scopes",
]
