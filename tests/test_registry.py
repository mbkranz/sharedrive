from __future__ import annotations

import pytest

from sharedrive.clients.base import BaseClient
from sharedrive.clients.googledrive import GoogleDriveClient
from sharedrive.clients.sharepoint import SharepointClient
from sharedrive.registry import (
    get_provider,
    list_providers,
    provider,
)


# ---------------------------------------------------------------------------
# provider decorator / registry lookup
# ---------------------------------------------------------------------------


def test_get_provider_returns_googledrive_class() -> None:
    # The @provider("googledrive") decorator runs when the module is imported.
    cls = get_provider("googledrive")
    assert cls is GoogleDriveClient


def test_get_provider_returns_sharepoint_class() -> None:
    cls = get_provider("sharepoint")
    assert cls is SharepointClient


def test_get_provider_returns_none_for_unknown() -> None:
    assert get_provider("nonexistent_provider_xyz") is None


def test_list_providers_includes_registered_clients() -> None:
    names = list_providers()
    assert "googledrive" in names
    assert "sharepoint" in names


def test_provider_decorator_registers_class() -> None:
    """@provider on a local class adds it to the registry."""

    @provider("test-provider-xyz")
    class _TestClient(BaseClient):
        auth_methods = ["test"]

        @classmethod
        def build_default(cls) -> "_TestClient":
            raise NotImplementedError

        @classmethod
        def check_auth(cls) -> None:
            raise NotImplementedError

    assert get_provider("test-provider-xyz") is _TestClient
    assert "test-provider-xyz" in list_providers()


# ---------------------------------------------------------------------------
# BaseClient abstract interface
# ---------------------------------------------------------------------------


def test_google_drive_client_is_base_client() -> None:
    assert issubclass(GoogleDriveClient, BaseClient)


def test_sharepoint_client_is_base_client() -> None:
    assert issubclass(SharepointClient, BaseClient)


def test_google_drive_client_auth_methods() -> None:
    assert "adc" in GoogleDriveClient.auth_methods
    assert "service_account" in GoogleDriveClient.auth_methods
    assert "user_oauth" in GoogleDriveClient.auth_methods


def test_sharepoint_client_auth_methods() -> None:
    assert "app_only" in SharepointClient.auth_methods
    assert "delegated" in SharepointClient.auth_methods


def test_base_client_cannot_be_instantiated_directly() -> None:
    """BaseClient is abstract; direct instantiation must raise TypeError."""
    with pytest.raises(TypeError):
        BaseClient()  # type: ignore[abstract]

