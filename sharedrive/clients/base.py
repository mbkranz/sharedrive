from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from sharedrive.item import DriveItem


class BaseClient(ABC):
    """Abstract base for all drive service clients.

    Every concrete client must declare:

    - :attr:`auth_methods`: the authentication modes the client supports
      (e.g. ``["adc", "service_account"]`` for Google Drive).
    - :meth:`build_default`: construct an instance from the current environment
      / settings (reads from ``.env`` or OS environment variables).
    - :meth:`check_auth`: validate that credentials are available; raises on
      failure with an actionable error message.

    The :func:`~sharedrive.registry.provider` decorator registers a concrete
    client class under a provider name so that other parts of the library can
    look up and instantiate clients by name without hard-coded imports::

        @provider("googledrive")
        class GoogleDriveClient(BaseClient):
            auth_methods = ["adc", "service_account", "user_oauth"]

            @classmethod
            def build_default(cls) -> "GoogleDriveClient":
                return cls(auth=GoogleAuth.from_settings())

            @classmethod
            def check_auth(cls) -> None:
                GoogleAuth.from_settings()

    Design note: ``auth_methods`` names mirror the ``auth_mode`` enum values in
    :mod:`sharedrive.auth.settings` (``GoogleAuthMode`` / ``MicrosoftAuthMode``).
    """

    auth_methods: ClassVar[list[str]] = []

    @classmethod
    @abstractmethod
    def build_default(cls) -> "BaseClient":
        """Construct this client from the current environment / settings.

        Reads provider-specific credentials from environment variables or a
        ``.env`` file (via the corresponding ``*AuthConfig`` pydantic-settings
        model).  Raises a provider-specific auth error when required variables
        are missing or invalid.
        """
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def check_auth(cls) -> None:
        """Validate that credentials for this provider are available.

        Raises a provider-specific exception with an actionable error message
        when the required credentials are missing or invalid.  Callers use this
        as a lightweight pre-flight check before attempting a download or fetch.
        """
        raise NotImplementedError

    @abstractmethod
    def get_from_weburl(self, url: str) -> DriveItem:
        """Retrieve a single item (file or directory) from its web URL.

        The returned :class:`~sharedrive.item.DriveItem` is the stable,
        unified entry-point for all further operations (refresh, download,
        to_resource, …).

        Args:
            url: The web-facing URL of the item (e.g. a Google Drive share
                 link or a SharePoint web URL).

        Returns:
            A :class:`~sharedrive.item.DriveItem` representing the remote
            file or directory.
        """
        raise NotImplementedError


__all__ = ["BaseClient"]

