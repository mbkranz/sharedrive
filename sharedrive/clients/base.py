from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Any

if TYPE_CHECKING:
    from sharedrive.item import ServiceItem


@dataclass(frozen=True)
class AdapterCapabilities:
    supports_fetch: bool = True
    supports_download: bool = True
    supports_auth_check: bool = True
    supports_write: bool = False


class BaseClient(ABC):
    """Abstract base for all drive service clients.

    Concrete providers define:

    - ``auth_methods``: supported auth-mode identifiers.
    - ``capabilities``: supported adapter operations.

    Implementations must provide:

    - ``build_default`` to construct a client from environment/settings.
    - ``check_auth`` to validate credentials without performing a transfer.
    - ``get_from_weburl`` to resolve a remote locator into a runtime ServiceItem.
    """

    auth_methods: ClassVar[list[str]] = []
    capabilities: ClassVar[AdapterCapabilities] = AdapterCapabilities()

    @classmethod
    @abstractmethod
    def build_default(cls) -> "BaseClient":
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def check_auth(cls) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_from_weburl(self, url: str) -> ServiceItem:
        raise NotImplementedError
    
    @abstractmethod
    def update_file(self, id: str, metadata: dict[str, Any], **kwargs) -> ServiceItem:
        """Update file metadata."""
        raise NotImplementedError
    
    @abstractmethod
    def create_file(self, name: str, parent_id: str, content: bytes, **kwargs) -> ServiceItem:
        """Create a new file with the given name, parent folder, and content."""
        raise NotImplementedError


__all__ = ["AdapterCapabilities", "BaseClient"]
