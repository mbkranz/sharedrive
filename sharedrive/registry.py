from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, TypeVar

_registry: dict[str, type] = {}


def provider(name: str) -> Client:
    """Class decorator that self-registers a client/adapter under *name*.

    Each registered class should expose two classmethods::

        @classmethod
        def build_default(cls) -> <ClientType>:
            ...  # construct from environment / settings

        @classmethod
        def check_auth(cls) -> None:
            ...  # raise if credentials are not available

    Usage::

        @provider("googledrive")
        class GoogleDriveClient:
            ...

    Callers can then do::

        import sharedrive
        client = sharedrive.providers("googledrive").build_default()
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