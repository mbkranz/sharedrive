from __future__ import annotations

import pytest

from sharedrive.clients.base import BaseClient
from sharedrive.clients.googledrive import GoogleDriveClient
from sharedrive.clients.sharepoint import SharepointClient
from sharedrive.registry import (
    ServiceAdapter,
    build_service_registry,
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


# ---------------------------------------------------------------------------
# ServiceAdapter dataclass
# ---------------------------------------------------------------------------


def test_service_adapter_defaults() -> None:
    adapter = ServiceAdapter()
    assert adapter.build_client is None
    assert adapter.check_auth is None
    assert adapter.auth_methods == []


def test_service_adapter_with_values() -> None:
    def my_build():
        return object()

    def my_check() -> None:
        pass

    adapter = ServiceAdapter(
        build_client=my_build,
        check_auth=my_check,
        auth_methods=["env"],
    )
    assert adapter.build_client is my_build
    assert adapter.check_auth is my_check
    assert adapter.auth_methods == ["env"]


# ---------------------------------------------------------------------------
# build_service_registry
# ---------------------------------------------------------------------------


def test_build_service_registry_includes_all_adapters() -> None:
    registry = build_service_registry()
    assert "googledrive" in registry
    assert "sharepoint" in registry
    assert "s3" in registry


def test_build_service_registry_adapters_have_auth_methods() -> None:
    registry = build_service_registry()
    assert registry["googledrive"].auth_methods == GoogleDriveClient.auth_methods
    assert registry["sharepoint"].auth_methods == SharepointClient.auth_methods
    assert registry["s3"].auth_methods == ["env"]


def test_build_service_registry_uses_factory_overrides() -> None:
    sentinel = object()

    def my_factory():
        return sentinel

    registry = build_service_registry(
        googledrive_client_factory=my_factory,
        sharepoint_client_factory=my_factory,
    )
    assert registry["googledrive"].build_client is my_factory
    assert registry["sharepoint"].build_client is my_factory


def test_build_service_registry_factory_used_as_check_auth() -> None:
    """When a factory is provided it is used as check_auth (calling it validates auth)."""
    calls: list[str] = []

    def sp_factory():
        calls.append("called")
        return object()

    registry = build_service_registry(sharepoint_client_factory=sp_factory)
    registry["sharepoint"].check_auth()

    assert calls == ["called"]


def test_build_service_registry_s3_check_auth_override() -> None:
    called = []

    def fake_s3_check() -> None:
        called.append(True)

    registry = build_service_registry(s3_auth_checker=fake_s3_check)
    registry["s3"].check_auth()

    assert called == [True]
