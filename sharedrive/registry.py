from __future__ import annotations

from typing import Callable, TypeVar

T = TypeVar("T")

# Maps provider name → registered client class (populated by @provider decorator).
_registry: dict[str, type] = {}


def provider(name: str) -> Callable[[type[T]], type[T]]:
    """Class decorator that self-registers a client under *name*.

    Every registered class must be a :class:`~sharedrive.clients.base.BaseClient`
    subclass and expose:

    - ``auth_methods: ClassVar[list[str]]`` — the auth modes the client supports.
    - ``build_default(cls) -> <ClientType>`` — construct from env / settings.
    - ``check_auth(cls) -> None`` — raise if credentials are unavailable.

    Usage::

        @provider("googledrive")
        class GoogleDriveClient(BaseClient):
            auth_methods = ["adc", "service_account", "user_oauth"]

            @classmethod
            def build_default(cls) -> "GoogleDriveClient":
                return cls(auth=GoogleAuth.from_settings())

            @classmethod
            def check_auth(cls) -> None:
                GoogleAuth.from_settings()

    Retrieve a registered class with :func:`get_provider`.
    """

    def decorator(cls: type[T]) -> type[T]:
        _registry[name] = cls
        return cls

    return decorator


def get_provider(name: str) -> type | None:
    """Return the registered provider class for *name*, or ``None`` if unknown."""
    return _registry.get(name)


def list_providers() -> list[str]:
    """Return the names of all registered providers."""
    return list(_registry.keys())


__all__ = [
    "get_provider",
    "list_providers",
    "provider",
]
