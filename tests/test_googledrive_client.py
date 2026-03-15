from __future__ import annotations

import json

import pytest

from sharedrive.clients.googledrive import FOLDER_MIME, GoogleBaseClient, GoogleDriveClient
from sharedrive.exceptions import GoogleDriveError


class DummyCreds:
    def __init__(self, *, valid: bool = True, token: str | None = "token") -> None:
        self.valid = valid
        self.token = token
        self.refresh_calls = 0

    def refresh(self, _request) -> None:
        self.refresh_calls += 1
        self.valid = True
        self.token = "refreshed-token"


class DummyStrategy:
    def __init__(self, creds) -> None:
        self.creds = creds
        self.build_calls = 0

    def build(self):
        self.build_calls += 1
        return self.creds


class DummyResponse:
    def __init__(
        self,
        *,
        ok: bool = True,
        status_code: int = 200,
        payload: dict | None = None,
        text: str = "",
        chunks: list[bytes] | None = None,
    ) -> None:
        self.ok = ok
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or json.dumps(self._payload)
        self._chunks = chunks or []

    def json(self):
        return self._payload

    def iter_content(self, chunk_size: int = 0):
        del chunk_size
        yield from self._chunks


class DummySession:
    def __init__(self, responses: list[DummyResponse]) -> None:
        self.responses = list(responses)
        self.calls = []

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


class DummyGoogleClient(GoogleBaseClient):
    pass


def test_client_uses_explicit_strategy() -> None:
    creds = DummyCreds(valid=True)
    strategy = DummyStrategy(creds)

    client = GoogleDriveClient(credential_strategy=strategy)

    assert client._creds is creds
    assert strategy.build_calls == 1


def test_client_legacy_constructor_uses_default_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    creds = DummyCreds(valid=True)
    strategy = DummyStrategy(creds)

    monkeypatch.setattr("sharedrive.clients.googledrive.default_drive_strategy", lambda **kwargs: strategy)

    client = GoogleDriveClient(credentials_path="service-account.json", scope=["scope-a"])

    assert client._creds is creds
    assert strategy.build_calls == 1


def test_request_refreshes_credentials_before_call() -> None:
    creds = DummyCreds(valid=False, token=None)
    response = DummyResponse(payload={"id": "123"})
    session = DummySession([response])
    client = GoogleDriveClient(credentials=creds, session=session)

    result = client.get_file("123")

    assert result == {"id": "123"}
    assert creds.refresh_calls == 1
    method, url, kwargs = session.calls[0]
    assert method == "GET"
    assert url.endswith("/files/123")
    assert kwargs["headers"]["Authorization"] == "Bearer refreshed-token"


def test_request_wraps_drive_errors() -> None:
    creds = DummyCreds(valid=True)
    response = DummyResponse(
        ok=False,
        status_code=404,
        payload={"error": {"message": "File not found"}},
    )
    session = DummySession([response])
    client = GoogleDriveClient(credentials=creds, session=session)

    with pytest.raises(GoogleDriveError) as exc_info:
        client.get_file("missing")

    assert exc_info.value.status_code == 404
    assert "File not found" in str(exc_info.value)


def test_download_from_weburl_returns_output_path(tmp_path) -> None:
    creds = DummyCreds(valid=True)
    metadata_response = DummyResponse(payload={"mimeType": "application/pdf"})
    file_response = DummyResponse(chunks=[b"abc", b"123"])
    session = DummySession([metadata_response, file_response])
    client = GoogleDriveClient(credentials=creds, session=session)

    output_path = tmp_path / "result.pdf"
    result = client.download_from_weburl(
        "https://drive.google.com/file/d/file123/view",
        output_path=str(output_path),
    )

    assert result == str(output_path)
    assert output_path.read_bytes() == b"abc123"


def test_extract_id_from_url_supports_spreadsheets() -> None:
    assert (
        GoogleDriveClient._extract_id_from_url(
            "https://docs.google.com/spreadsheets/d/sheet123/edit#gid=0"
        )
        == "sheet123"
    )


def test_google_base_client_requires_credentials_or_strategy() -> None:
    with pytest.raises(ValueError):
        DummyGoogleClient()


def test_google_base_client_uses_generic_google_api_error() -> None:
    creds = DummyCreds(valid=True)
    response = DummyResponse(
        ok=False,
        status_code=500,
        payload={"error": {"message": "backend error"}},
    )
    session = DummySession([response])
    client = DummyGoogleClient(credentials=creds, session=session)

    with pytest.raises(Exception) as exc_info:
        client._request("GET", "https://example.test")

    assert exc_info.value.__class__.__name__ == "GoogleApiError"
    assert "backend error" in str(exc_info.value)


def test_list_folder_files_recursive_returns_relative_paths() -> None:
    creds = DummyCreds(valid=True)
    folder_metadata = DummyResponse(payload={"id": "folder123", "mimeType": FOLDER_MIME})
    root_children = DummyResponse(
        payload={
            "files": [
                {
                    "id": "child-folder",
                    "name": "reports",
                    "mimeType": FOLDER_MIME,
                    "parents": ["folder123"],
                },
                {
                    "id": "file-1",
                    "name": "summary.csv",
                    "mimeType": "text/csv",
                    "parents": ["folder123"],
                },
            ]
        }
    )
    nested_children = DummyResponse(
        payload={
            "files": [
                {
                    "id": "file-2",
                    "name": "detail.csv",
                    "mimeType": "text/csv",
                    "parents": ["child-folder"],
                }
            ]
        }
    )
    session = DummySession([folder_metadata, root_children, nested_children])
    client = GoogleDriveClient(credentials=creds, session=session)

    results = client.list_folder_files("folder123", recursive=True)

    assert sorted(results, key=lambda item: item["relative_path"]) == [
        {
            "id": "file-2",
            "name": "detail.csv",
            "mimeType": "text/csv",
            "parents": ["child-folder"],
            "relative_path": "reports/detail.csv",
        },
        {
            "id": "file-1",
            "name": "summary.csv",
            "mimeType": "text/csv",
            "parents": ["folder123"],
            "relative_path": "summary.csv",
        },
    ]
    assert session.calls[1][2]["params"]["q"] == "'folder123' in parents and trashed = false"
    assert session.calls[2][2]["params"]["q"] == "'child-folder' in parents and trashed = false"


def test_list_folder_files_rejects_non_folder() -> None:
    creds = DummyCreds(valid=True)
    metadata_response = DummyResponse(payload={"id": "file123", "mimeType": "text/csv"})
    session = DummySession([metadata_response])
    client = GoogleDriveClient(credentials=creds, session=session)

    with pytest.raises(ValueError, match="not a folder"):
        client.list_folder_files("file123")
