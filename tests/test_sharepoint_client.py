from __future__ import annotations

from pathlib import Path

import pytest

from sharedrive.auth.microsoft import MicrosoftAuth
from sharedrive.clients.sharepoint import SharepointClient
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
