from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

from sharedrive.clients.aws import check_s3_credentials

ClientFactory = Callable[[], Any]
AuthCheck = Callable[[], None]


@dataclass(frozen=True, slots=True)
class ServiceAdapter:
    build_client: ClientFactory | None = None
    check_auth: AuthCheck | None = None


def _default_sharepoint_client_factory() -> Any:
    from sharedrive.auth.settings import make_sharepoint_client_from_microsoft_auth

    return make_sharepoint_client_from_microsoft_auth()


def _default_googledrive_client_factory() -> Any:
    from sharedrive.auth.google import default_drive_strategy
    from sharedrive.clients.googledrive import GoogleDriveClient

    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    return GoogleDriveClient(
        credential_strategy=default_drive_strategy(credentials_path=credentials_path)
    )


def _check_googledrive_auth(factory: ClientFactory) -> None:
    client = factory()
    ensure_valid = getattr(client, "_ensure_valid_credentials", None)
    if callable(ensure_valid):
        ensure_valid()
    else:
        _ = client._hdrs


def _check_sharepoint_auth(factory: ClientFactory) -> None:
    factory()


def build_service_registry(
    *,
    sharepoint_client_factory: ClientFactory | None = None,
    googledrive_client_factory: ClientFactory | None = None,
    s3_auth_checker: Callable[[], None] | None = None,
) -> dict[str, ServiceAdapter]:
    sharepoint_factory = sharepoint_client_factory or _default_sharepoint_client_factory
    googledrive_factory = googledrive_client_factory or _default_googledrive_client_factory

    return {
        "sharepoint": ServiceAdapter(
            build_client=sharepoint_factory,
            check_auth=lambda: _check_sharepoint_auth(sharepoint_factory),
        ),
        "googledrive": ServiceAdapter(
            build_client=googledrive_factory,
            check_auth=lambda: _check_googledrive_auth(googledrive_factory),
        ),
        "s3": ServiceAdapter(
            check_auth=s3_auth_checker or check_s3_credentials,
        ),
    }


__all__ = ["ClientFactory", "ServiceAdapter", "build_service_registry"]