from __future__ import annotations

"""Compatibility exports for SharePoint auth helpers.

SharePoint auth now reuses the Microsoft Graph auth implementation, but this
module path remains part of the public surface for callers importing
``sharedrive.auth.sharepoint`` directly.
"""

from sharedrive.auth.microsoft import (
    DEFAULT_MICROSOFT_GRAPH_SCOPES,
    AppOnlyStrategy,
    DelegatedStrategy,
    MicrosoftTokenStrategy,
    normalize_microsoft_scopes,
)

DEFAULT_SHAREPOINT_SCOPES = DEFAULT_MICROSOFT_GRAPH_SCOPES
SharepointTokenStrategy = MicrosoftTokenStrategy
normalize_sharepoint_scopes = normalize_microsoft_scopes

__all__ = [
    "AppOnlyStrategy",
    "DEFAULT_SHAREPOINT_SCOPES",
    "DelegatedStrategy",
    "SharepointTokenStrategy",
    "normalize_sharepoint_scopes",
]