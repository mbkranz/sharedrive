"""sharedrive – shared-drive adapters for SharePoint, Google Drive, and S3.

Quick start::

    import sharedrive

    # Instantiate a provider using environment-variable config:
    client = sharedrive.providers("googledrive").build_default()
    client = sharedrive.providers("sharepoint").build_default()
    client = sharedrive.providers("s3").build_default()
"""

from sharedrive.registry import get_provider, list_providers

#: Alias for :func:`~sharedrive.registry.get_provider`.
#: Returns the registered provider class for the given name, e.g.::
#:
#:     sharedrive.providers("googledrive").build_default()
providers = get_provider

__all__ = ["get_provider", "list_providers", "providers"]
