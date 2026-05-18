from __future__ import annotations

from sharedrive.clients.base import AdapterCapabilities
from sharedrive.clients.sharepoint import SharepointClient


class SharepointWriteClient(SharepointClient):
    """Experimental SharePoint write surface kept separate from stable retrieval flows."""

    capabilities = AdapterCapabilities(
        supports_fetch=True,
        supports_download=True,
        supports_auth_check=True,
        supports_write=True,
    )


__all__ = ["SharepointWriteClient"]
