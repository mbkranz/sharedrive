from sharedrive.auth import microsoft as _microsoft

msal = _microsoft.msal

AppOnlyStrategy = _microsoft.AppOnlyStrategy
DEFAULT_SHAREPOINT_SCOPES = _microsoft.DEFAULT_MICROSOFT_GRAPH_SCOPES
DelegatedStrategy = _microsoft.DelegatedStrategy
SharepointTokenStrategy = _microsoft.MicrosoftTokenStrategy
normalize_sharepoint_scopes = _microsoft.normalize_microsoft_scopes


__all__ = [
    "AppOnlyStrategy",
    "DEFAULT_SHAREPOINT_SCOPES",
    "DelegatedStrategy",
    "SharepointTokenStrategy",
    "normalize_sharepoint_scopes",
]