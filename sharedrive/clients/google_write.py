from __future__ import annotations

from sharedrive.clients.base import AdapterCapabilities
from sharedrive.clients.googledrive import GoogleDriveClient


class GoogleDriveWriteClient(GoogleDriveClient):
    """Experimental Google Drive write surface kept separate from stable retrieval flows."""

    capabilities = AdapterCapabilities(
        supports_fetch=True,
        supports_download=True,
        supports_auth_check=True,
        supports_write=True,
    )


__all__ = ["GoogleDriveWriteClient"]
