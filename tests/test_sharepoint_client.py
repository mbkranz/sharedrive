from __future__ import annotations

from pathlib import Path

import pytest

from sharedrive.auth.microsoft import MicrosoftAuth
from sharedrive.clients.sharepoint import SharepointClient, SharepointItem
from sharedrive.exceptions import GraphApiDriveError


class DummyResponse:
    def __init__(
        self,
        *,
        status_code: int,
        reason: str = "Error",
        text: str = "",
        content: bytes = b"",
        headers: dict[str, str] | None = None,
        ok: bool | None = None,
    ) -> None:
        self.status_code = status_code
        self.reason = reason
        self.text = text
        self.content = content
        self.headers = headers or {}
        self.ok = status_code == 200 if ok is None else ok

    def json(self) -> dict[str, str]:
        return {"status": "ok"}


def test_sharepoint_client_accepts_microsoft_auth() -> None:
    auth = MicrosoftAuth("my-bearer-token")
    client = SharepointClient(auth=auth, host_url="contoso.sharepoint.com")

    assert client.access_token == "my-bearer-token"
    assert client.host_url == "contoso.sharepoint.com"


def test_sharepoint_client_rejects_both_auth_and_access_token() -> None:
    auth = MicrosoftAuth("token")
    with pytest.raises(ValueError, match="either auth or access_token"):
        SharepointClient(auth=auth, access_token="token")


def test_sharepoint_client_requires_auth_or_access_token() -> None:
    with pytest.raises(ValueError):
        SharepointClient()


def test_download_content_requires_identifiers_or_download_url() -> None:
    client = SharepointClient(access_token="token")

    with pytest.raises(GraphApiDriveError, match="Need drive_id and item_id"):
        client.download_content()


def test_download_content_raises_graph_error_for_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SharepointClient(access_token="token")

    monkeypatch.setattr(
        "sharedrive.clients.sharepoint.requests.get",
        lambda *_args, **_kwargs: DummyResponse(
            status_code=503, reason="Service Unavailable", text="upstream down"
        ),
    )

    with pytest.raises(GraphApiDriveError) as exc_info:
        client.download_content(drive_id="drive-1", item_id="item-1")

    assert exc_info.value.status_code == 503
    assert exc_info.value.response_text == "upstream down"


def test_download_raises_graph_error_before_writing_failed_response(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = SharepointClient(access_token="token")
    target = tmp_path / "report.csv"

    monkeypatch.setattr(
        "sharedrive.clients.sharepoint.requests.get",
        lambda *_args, **_kwargs: DummyResponse(
            status_code=500, reason="Server Error", text="bad gateway", ok=False
        ),
    )

    metadata = {"file": {}, "id": "item-1", "parentReference": {"driveId": "drive-1"}}

    with pytest.raises(GraphApiDriveError) as exc_info:
        client.download(metadata, target)

    assert exc_info.value.status_code == 500
    assert not target.exists()


def test_update_content_treats_graph_404_as_missing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = SharepointClient(access_token="token")
    local_file = tmp_path / "report.csv"
    local_file.write_text("report", encoding="utf-8")
    captured: dict[str, object] = {}

    monkeypatch.setattr(client, "get_site_id", lambda _site_name: "site-1")
    monkeypatch.setattr(client, "get_drive_id", lambda _site_id: "drive-1")

    def fake_get_item_metadata(
        _drive_id: str, *, item_path: str | None = None, item_id: str | None = None
    ):
        raise GraphApiDriveError("missing", status_code=404)

    def fake_put(url: str, *, headers: dict[str, str], data) -> DummyResponse:
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = data.read()
        return DummyResponse(status_code=201, ok=True)

    monkeypatch.setattr(client, "get_item_metadata", fake_get_item_metadata)
    monkeypatch.setattr("sharedrive.clients.sharepoint.requests.put", fake_put)

    result = client.update_content(
        "site-name", "/Shared Documents", local_file, create_if_missing=True
    )

    assert result == {"status": "ok"}
    assert captured["url"] == (
        "https://graph.microsoft.com/v1.0/drives/drive-1/root:/Shared Documents/report.csv:/content"
    )
    assert captured["body"] == b"report"


def test_sharepoint_item_iter_files_paths_are_relative_to_weburl_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SharepointClient(access_token="token")
    root_metadata = {
        "id": "root",
        "name": "Approvals",
        "folder": {},
        "webUrl": "https://contoso.sharepoint.com/sites/Test/Shared Documents/Approvals",
        "parentReference": {"id": "parent", "driveId": "drive-1"},
        "children": [
            {
                "id": "folder-1",
                "name": "01-proposal-process",
                "folder": {},
                "parentReference": {"id": "root", "driveId": "drive-1"},
                "children": [
                    {
                        "id": "file-1",
                        "name": "approval.docx",
                        "file": {},
                        "webUrl": (
                            "https://contoso.sharepoint.com/sites/Test/"
                            "Shared Documents/Approvals/01-proposal-process/"
                            "approval.docx"
                        ),
                        "parentReference": {
                            "id": "folder-1",
                            "driveId": "drive-1",
                        },
                    }
                ],
            }
        ],
    }

    monkeypatch.setattr(client, "get_site_id", lambda _site_name: "site-1")
    monkeypatch.setattr(client, "get_drive_id", lambda *_args, **_kwargs: "drive-1")
    monkeypatch.setattr(
        client, "get_item_metadata", lambda *_args, **_kwargs: root_metadata
    )

    root = SharepointItem.from_weburl(
        "https://contoso.sharepoint.com/sites/Test/Shared Documents/Approvals",
        client,
    )
    files = list(root.iter_files())

    assert root.path == ""
    assert len(files) == 1
    assert files[0].path == "01-proposal-process/approval.docx"


def test_sharepoint_item_from_path_resolves_library_relative_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SharepointClient(access_token="token")
    calls: dict[str, object] = {}
    metadata = {
        "id": "file-1",
        "name": "approval.docx",
        "file": {},
        "webUrl": "https://contoso.sharepoint.com/sites/Test/Shared Documents/folder/approval.docx",
        "parentReference": {"id": "folder-1", "driveId": "drive-1"},
    }

    monkeypatch.setattr(client, "get_site_id", lambda site_name: f"site:{site_name}")

    def fake_get_drive_id(site_id: str, drive_name: str | None = None) -> str:
        calls["site_id"] = site_id
        calls["drive_name"] = drive_name
        return "drive-1"

    def fake_get_item_metadata(drive_id: str, *, item_path: str | None = None, **_kwargs):
        calls["drive_id"] = drive_id
        calls["item_path"] = item_path
        return metadata

    monkeypatch.setattr(client, "get_drive_id", fake_get_drive_id)
    monkeypatch.setattr(client, "get_item_metadata", fake_get_item_metadata)

    item = SharepointItem.from_path(
        site_name="Test",
        item_path="Shared Documents/folder/approval.docx",
        client=client,
    )

    assert calls == {
        "site_id": "site:Test",
        "drive_name": "Shared Documents",
        "drive_id": "drive-1",
        "item_path": "/folder/approval.docx",
    }
    assert item.path == "folder/approval.docx"
    assert not item.is_directory


def test_sharepoint_item_from_path_resolves_library_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SharepointClient(access_token="token")
    calls: dict[str, object] = {}
    metadata = {
        "id": "root",
        "name": "Shared Documents",
        "folder": {},
        "webUrl": "https://contoso.sharepoint.com/sites/Test/Shared Documents",
        "parentReference": {"id": "site-root", "driveId": "drive-1"},
    }

    monkeypatch.setattr(client, "get_site_id", lambda _site_name: "site-1")

    def fake_get_drive_id(_site_id: str, drive_name: str | None = None) -> str:
        calls["drive_name"] = drive_name
        return "drive-1"

    def fake_get_item_metadata(drive_id: str, *, item_path: str | None = None, **_kwargs):
        calls["drive_id"] = drive_id
        calls["item_path"] = item_path
        return metadata

    monkeypatch.setattr(client, "get_drive_id", fake_get_drive_id)
    monkeypatch.setattr(client, "get_item_metadata", fake_get_item_metadata)

    item = SharepointItem.from_path(
        site_name="Test",
        item_path="Shared Documents/",
        client=client,
    )

    assert calls["drive_name"] == "Shared Documents"
    assert calls["drive_id"] == "drive-1"
    assert calls["item_path"] == "/"
    assert item.path == ""
    assert item.is_directory
