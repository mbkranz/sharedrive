from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, TypeVar

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Core registry
# ---------------------------------------------------------------------------

_registry: dict[str, type] = {}


def provider(name: str) -> Callable[[type[T]], type[T]]:
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


# ---------------------------------------------------------------------------
# Backward-compatible API
# ---------------------------------------------------------------------------

ClientFactory = Callable[[], Any]
AuthCheck = Callable[[], None]


@dataclass(frozen=True, slots=True)
class ServiceAdapter:
    """Kept for backward compatibility.

    Prefer :func:`get_provider` for new code.
    """

    build_client: ClientFactory | None = None
    check_auth: AuthCheck | None = None


def build_service_registry(
    *,
    sharepoint_client_factory: ClientFactory | None = None,
    googledrive_client_factory: ClientFactory | None = None,
    s3_auth_checker: Callable[[], None] | None = None,
) -> dict[str, ServiceAdapter]:
    """Build a ``{name: ServiceAdapter}`` dict.

    .. deprecated::
        Prefer :func:`get_provider` for new code.  This function is retained
        for backward compatibility and for existing callers that monkey-patch
        it in tests.
    """
    # Import lazily so that the @provider decorators in the client modules
    # have already fired before we dereference the classes.
    from sharedrive.clients.aws import S3Adapter  # noqa: F401 – ensures registration
    from sharedrive.clients.googledrive import GoogleDriveClient  # noqa: F401
    from sharedrive.clients.sharepoint import SharepointClient  # noqa: F401

    sp_factory = sharepoint_client_factory or SharepointClient.build_default
    gd_factory = googledrive_client_factory or GoogleDriveClient.build_default

    def _sp_check() -> None:
        if sharepoint_client_factory is not None:
            sharepoint_client_factory()
        else:
            SharepointClient.check_auth()

    def _gd_check() -> None:
        if googledrive_client_factory is not None:
            client = googledrive_client_factory()
            ensure_valid = getattr(client, "_ensure_valid_credentials", None)
            if callable(ensure_valid):
                ensure_valid()
            else:
                _ = client._hdrs
        else:
            GoogleDriveClient.check_auth()

    s3_cls = get_provider("s3")
    return {
        "sharepoint": ServiceAdapter(build_client=sp_factory, check_auth=_sp_check),
        "googledrive": ServiceAdapter(build_client=gd_factory, check_auth=_gd_check),
        "s3": ServiceAdapter(
            check_auth=s3_auth_checker or (s3_cls.check_auth if s3_cls else None),
        ),
    }


__all__ = [
    "ClientFactory",
    "ServiceAdapter",
    "build_service_registry",
    "get_provider",
    "list_providers",
    "provider",
]