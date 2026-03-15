from __future__ import annotations

from sharedrive.auth.settings import (
    MicrosoftAuthConfig,
    MicrosoftAuthMode,
    SharepointAuthConfig,
    SharepointAuthMode,
    make_sharepoint_client_from_microsoft_auth,
    make_sharepoint_client_from_settings,
)


class SpoConfig(SharepointAuthConfig):
    @property
    def scope(self) -> list[str]:
        return self.scopes

    @property
    def user_delegated_access(self) -> bool:
        return self.auth_mode == SharepointAuthMode.DELEGATED

    def to_client(self):
        return make_sharepoint_client_from_microsoft_auth(self)


__all__ = [
    "MicrosoftAuthConfig",
    "MicrosoftAuthMode",
    "SharepointAuthConfig",
    "SharepointAuthMode",
    "SpoConfig",
    "make_sharepoint_client_from_microsoft_auth",
    "make_sharepoint_client_from_settings",
]
