from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

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

    Retrieve a registered class with :func:`get_provider` or build the full
    service registry with :func:`build_service_registry`.
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


@dataclass
class ServiceAdapter:
    """Thin descriptor for a drive service adapter used by actions.

    ``build_client`` is a zero-argument callable that returns a connected
    client instance.  ``check_auth`` validates that credentials are available
    without actually constructing a client.  ``auth_methods`` lists the
    authentication modes supported by the underlying provider class (mirrors
    ``BaseClient.auth_methods``).
    """

    build_client: Callable[[], Any] | None = None
    check_auth: Callable[[], None] | None = None
    auth_methods: list[str] = field(default_factory=list)


def build_service_registry(
    *,
    sharepoint_client_factory: Callable[[], Any] | None = None,
    googledrive_client_factory: Callable[[], Any] | None = None,
    s3_auth_checker: Callable[[], None] | None = None,
) -> dict[str, ServiceAdapter]:
    """Build a mapping from adapter name → :class:`ServiceAdapter`.

    Callers may supply factory overrides (primarily for tests).  When a factory
    is *not* supplied, the corresponding ``@provider``-registered class is used
    (``build_default`` / ``check_auth`` class methods).

    The client modules are imported inside this function so that the
    ``@provider`` decorators have run before the registry is consulted.  This
    means callers do not need to import the client modules explicitly.

    S3 has no registered client class; its auth check comes from
    :func:`~sharedrive.clients.aws.check_s3_credentials`.
    """
    # Trigger @provider registration by importing the client modules.
    import sharedrive.clients.googledrive  # noqa: F401
    import sharedrive.clients.sharepoint  # noqa: F401
    from sharedrive.clients.aws import check_s3_credentials

    result: dict[str, ServiceAdapter] = {}

    gdrive_cls = _registry.get("googledrive")
    if googledrive_client_factory is not None or gdrive_cls is not None:
        gdrive_build = googledrive_client_factory or (
            gdrive_cls.build_default if gdrive_cls is not None else None
        )
        # When a factory override is provided, calling it IS the auth check.
        # Otherwise, use the class-level check_auth which validates credentials
        # without constructing a full client.
        gdrive_auth_check: Callable[[], Any] | None = googledrive_client_factory or (
            getattr(gdrive_cls, "check_auth", None) if gdrive_cls is not None else None
        )
        result["googledrive"] = ServiceAdapter(
            build_client=gdrive_build,
            check_auth=gdrive_auth_check,
            auth_methods=list(getattr(gdrive_cls, "auth_methods", []))
            if gdrive_cls is not None
            else [],
        )

    sp_cls = _registry.get("sharepoint")
    if sharepoint_client_factory is not None or sp_cls is not None:
        sp_build = sharepoint_client_factory or (
            sp_cls.build_default if sp_cls is not None else None
        )
        sp_auth_check: Callable[[], Any] | None = sharepoint_client_factory or (
            getattr(sp_cls, "check_auth", None) if sp_cls is not None else None
        )
        result["sharepoint"] = ServiceAdapter(
            build_client=sp_build,
            check_auth=sp_auth_check,
            auth_methods=list(getattr(sp_cls, "auth_methods", []))
            if sp_cls is not None
            else [],
        )

    result["s3"] = ServiceAdapter(
        build_client=None,
        check_auth=s3_auth_checker if s3_auth_checker is not None else check_s3_credentials,
        auth_methods=["env"],
    )

    return result


__all__ = [
    "ServiceAdapter",
    "build_service_registry",
    "get_provider",
    "list_providers",
    "provider",
]
