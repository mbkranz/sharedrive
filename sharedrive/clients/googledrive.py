from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar, Dict, Literal, Optional, Union

import requests
from google.auth.credentials import Credentials
from sharedrive.item import DriveItem

from sharedrive.auth.google import GoogleAuth
from sharedrive.clients.base import BaseClient
from sharedrive.exceptions import GoogleApiError, GoogleDriveError
from sharedrive.registry import provider


class GoogleBaseClient(BaseClient):
    """Shared Google client base: auth lifecycle and HTTP transport helpers.

    Provides the Bearer-token header, a unified ``_request()`` method with
    structured error handling, and stream-to-disk / stream-to-bytes helpers.
    Concrete subclasses supply ``api_error_cls`` to choose which exception is
    raised on HTTP failures.

    Design note: this class intentionally separates low-level HTTP transport
    from drive-specific business logic so that non-Drive Google APIs (Sheets,
    etc.) could extend it without carrying Drive-specific state.
    """

    api_error_cls = GoogleApiError

    # Satisfy BaseClient abstract requirements at the intermediate level so
    # that direct subclasses only need to override if they want custom behaviour.
    auth_methods: ClassVar[list[str]] = ["adc", "service_account", "user_oauth"]

    def __init__(
        self,
        auth: GoogleAuth | None = None,
        *,
        credentials: Credentials | None = None,
        session: requests.Session | None = None,
        timeout: int = 120,
    ) -> None:

        self.session = session or requests.Session()
        self.timeout = timeout

        if auth is not None and credentials is not None:
            raise ValueError("Provide either auth or credentials, not both.")

        if credentials is not None:
            self._auth = GoogleAuth(credentials)
        elif auth is not None:
            self._auth = auth
        else:
            raise ValueError(
                "GoogleBaseClient requires either auth or credentials."
            )

    @property
    def _hdrs(self) -> dict[str, str]:
        self._auth.ensure_valid()
        return {"Authorization": f"Bearer {self._auth.credentials.token}"}

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        headers = kwargs.pop("headers", {})
        merged_headers = {**self._hdrs, **headers}

        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=merged_headers,
                timeout=self.timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise self.api_error_cls(f"HTTP request failed: {exc}") from exc

        if response.ok:
            return response

        try:
            payload = response.json()
        except ValueError:
            payload = None

        message = f"Google API request failed with status {response.status_code}"
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict) and error.get("message"):
                message = f"{message}: {error['message']}"

        raise self.api_error_cls(
            message,
            status_code=response.status_code,
            response_text=response.text,
            response_json=payload,
        )

    @staticmethod
    def _write_stream_to_path(resp: requests.Response, output_path: str | Path) -> str:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as handle:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
        return str(destination)

    @staticmethod
    def _read_stream_to_bytes(resp: requests.Response) -> bytes:
        return b"".join(
            chunk for chunk in resp.iter_content(chunk_size=1024 * 1024) if chunk
        )

    @classmethod
    def build_default(cls) -> "GoogleBaseClient":
        """Construct from environment variables / settings.

        Reads ``GOOGLE_AUTH_MODE`` (and associated credentials) from the
        environment or a ``.env`` file.  Override in concrete subclasses to
        return the exact subclass type.
        """
        return cls(auth=GoogleAuth.from_settings())

    @classmethod
    def check_auth(cls) -> None:
        """Validate that Google credentials are available.

        Calls :meth:`~sharedrive.auth.google.GoogleAuth.from_settings` which
        raises :class:`~sharedrive.exceptions.GoogleAuthError` if the
        credentials are missing or invalid.
        """
        GoogleAuth.from_settings()


DRIVE_URL = "https://www.googleapis.com/drive/v3"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"

FOLDER_MIME = "application/vnd.google-apps.folder"


class GoogleMimeTypes(Enum):
    """Google-native MIME types."""

    DOC = "application/vnd.google-apps.document"
    SHEET = "application/vnd.google-apps.spreadsheet"
    SLIDE = "application/vnd.google-apps.presentation"
    DRAW = "application/vnd.google-apps.drawing"
    FORM = "application/vnd.google-apps.form"
    JAM = "application/vnd.google-apps.jam"
    APP = "application/vnd.google-apps.script"
    SHORT = "application/vnd.google-apps.shortcut"


DEFAULT_EXPORTS = {
    GoogleMimeTypes.DOC.value: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    GoogleMimeTypes.SHEET.value: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    GoogleMimeTypes.SLIDE.value: "application/pdf",
    GoogleMimeTypes.DRAW.value: "application/pdf",
    GoogleMimeTypes.FORM.value: "application/pdf",
    GoogleMimeTypes.JAM.value: "application/pdf",
    GoogleMimeTypes.APP.value: "application/zip",
}

ALT_EXPORTS = {
    "docx": "application/pdf",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "pdf": "application/pdf",
}


@provider("googledrive")
class GoogleDriveClient(GoogleBaseClient):
    """Google Drive client (ID-first) with read/write and full export coverage.

    Supports My Drive and Shared Drives via the Drive REST API v3.

    Instantiate via a :class:`~sharedrive.auth.google.GoogleAuth` object::

        auth = GoogleAuth.from_adc()
        client = GoogleDriveClient(auth)

        # Or from environment variables / .env file:
        client = GoogleDriveClient.build_default()

    The *credentials* keyword argument is a low-level escape hatch kept for
    tests only; prefer :class:`~sharedrive.auth.google.GoogleAuth` in all
    production code.

    The class is registered as the ``"googledrive"`` provider via the
    :func:`~sharedrive.registry.provider` decorator; use
    :func:`~sharedrive.registry.build_service_registry` to obtain a
    :class:`~sharedrive.registry.ServiceAdapter` for it.
    """

    auth_methods: ClassVar[list[str]] = ["adc", "service_account", "user_oauth"]
    api_error_cls = GoogleDriveError

    def __init__(
        self,
        auth: GoogleAuth | None = None,
        *,
        credentials: Credentials | None = None,
        session: requests.Session | None = None,
        timeout: int = 120,
    ):
        super().__init__(
            auth=auth,
            credentials=credentials,
            session=session,
            timeout=timeout,
        )

    @classmethod
    def build_default(cls) -> "GoogleDriveClient":
        """Construct from environment variables / settings.

        Reads ``GOOGLE_AUTH_MODE`` (and associated credential paths) from the
        environment or a ``.env`` file via
        :class:`~sharedrive.auth.settings.GoogleAuthConfig`.
        """
        return cls(auth=GoogleAuth.from_settings())

    @classmethod
    def check_auth(cls) -> None:
        """Validate that Google credentials are available.

        Raises :class:`~sharedrive.exceptions.GoogleAuthError` if the
        credentials configured in the environment are missing or invalid.
        """
        GoogleAuth.from_settings()

    @staticmethod
    def _is_google_workspace_file(file_mime_type: str) -> bool:
        return file_mime_type in {mime.value for mime in GoogleMimeTypes}

    def list_files(
        self,
        *,
        query: str | None = None,
        fields: str = "id, name, mimeType, parents",
        page_size: int = 100,
    ):
        """List all files the authenticated user has access to."""
        files = []
        page_token = None

        while True:
            params = {
                "pageSize": page_size,
                "fields": f"nextPageToken, files({fields})",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            if query:
                params["q"] = query
            if page_token:
                params["pageToken"] = page_token

            resp = self._request("GET", f"{DRIVE_URL}/files", params=params).json()
            files.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return files


    def list_folder_contents(
        self,
        folder_id: str,
        *,
        recursive: bool = False,
    ) -> list[Dict[str, Any]]:
        """List folder descendants and annotate each entry with a relative_path."""
        folder_metadata = self.get_file(folder_id, fields="id, name, mimeType")
        if folder_metadata.get("mimeType") != FOLDER_MIME:
            raise ValueError(f"Google Drive source is not a folder: {folder_id}")

        results: list[Dict[str, Any]] = []

        def walk(parent_folder_id: str, relative_root: PurePosixPath) -> None:
            children = self.list_files(
                query=f"'{parent_folder_id}' in parents and trashed = false",
                fields="id, name, mimeType, parents",
            )
            for child in children:
                child_name = str(child.get("name", child.get("id", ""))).strip()
                if not child_name:
                    child_name = str(child.get("id", "item"))
                relative_path = relative_root / child_name
                child_with_path = dict(child)
                child_with_path["relative_path"] = relative_path.as_posix()
                results.append(child_with_path)

                if recursive and child.get("mimeType") == FOLDER_MIME:
                    walk(str(child.get("id", "")), relative_path)

        walk(folder_id, PurePosixPath())
        return results

    def list_folder_files(
        self,
        folder_id: str,
        *,
        recursive: bool = True,
    ) -> list[Dict[str, Any]]:
        """List files contained in a folder, optionally descending into child folders."""
        return [
            entry
            for entry in self.list_folder_contents(folder_id, recursive=recursive)
            if entry.get("mimeType") != FOLDER_MIME
        ]

    def list_folder_files_from_weburl(
        self,
        web_url: str,
        *,
        recursive: bool = True,
    ) -> list[Dict[str, Any]]:
        """Resolve a folder URL and list files contained within it."""
        folder_id = self._extract_id_from_url(web_url)
        return self.list_folder_files(folder_id, recursive=recursive)

    def get_file(self, file_id: str, **kwargs) -> Dict[str, Any]:
        endpoint = f"{DRIVE_URL}/files/{file_id}"
        response = self._request(
            "GET", endpoint, params={"supportsAllDrives": "true", **kwargs}
        )
        return response.json()

    def infer_export_mime_type(self, file_id: str) -> Optional[str]:
        file_metadata = self.get_file(file_id, fields="mimeType")
        source_mime = file_metadata.get("mimeType", "")
        return DEFAULT_EXPORTS.get(source_mime)

    def download_file(
        self,
        file_id: str,
        output_path: Optional[str] = None,
        mime_type: Optional[str] = None,
        acknowledge_abuse: bool = False,
        byte_range: Optional[str] = None,
        supports_all_drives: bool = True,
        **kwargs,
    ) -> Union[bytes, str]:
        def build_params():
            params = {
                "alt": "media",
                "supportsAllDrives": str(supports_all_drives).lower(),
            }
            if acknowledge_abuse:
                params["acknowledgeAbuse"] = "true"
            return params

        def build_headers():
            headers = dict(self._hdrs)
            if byte_range:
                headers["Range"] = byte_range
            return headers

        file_metadata = self.get_file(file_id, fields="mimeType")
        file_mime_type = file_metadata.get("mimeType", "")

        if self._is_google_workspace_file(file_mime_type):
            return self.export_file(
                file_id=file_id,
                mime_type=mime_type,
                output_path=output_path,
                supports_all_drives=supports_all_drives,
                **kwargs,
            )

        response = self._request(
            "GET",
            f"{DRIVE_URL}/files/{file_id}",
            headers=build_headers(),
            params=build_params(),
            stream=True,
        )

        if output_path:
            return self._write_stream_to_path(response, output_path)

        return self._read_stream_to_bytes(response)

    def export_file(
        self,
        file_id: str,
        mime_type: Optional[str] = None,
        output_path: Optional[str] = None,
        supports_all_drives: bool = True,
        **kwargs,
    ) -> Union[bytes, str]:
        def build_params(target_mime: str):
            return {
                "mimeType": target_mime,
                "supportsAllDrives": str(supports_all_drives).lower(),
            }

        if mime_type is None:
            inferred_mime = self.infer_export_mime_type(file_id)
            if inferred_mime is None:
                raise ValueError(
                    f"Could not infer export MIME type for file {file_id}. "
                    "Please provide mime_type parameter explicitly."
                )
            mime_type = inferred_mime

        response = self._request(
            "GET",
            f"{DRIVE_URL}/files/{file_id}/export",
            params=build_params(mime_type),
            stream=True,
        )

        if output_path:
            return self._write_stream_to_path(response, output_path)

        return self._read_stream_to_bytes(response)

    def create_file(
        self,
        parent_folder_id: str,
        file_in_bytes: Optional[bytes] = None,
        mime_type: Optional[str] = None,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        supports_all_drives: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        def build_metadata():
            if not name:
                raise ValueError("Must provide name parameter")

            file_metadata = {"name": name, "parents": [parent_folder_id]}
            if metadata:
                file_metadata.update(metadata)
            return file_metadata

        def build_multipart_body(media, file_metadata, mime_type):
            boundary = "END_OF_PART_1234567890"
            headers = {
                **self._hdrs,
                "Content-Type": f"multipart/related; boundary={boundary}",
            }

            body = (
                f"--{boundary}\r\n"
                "Content-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{json.dumps(file_metadata)}\r\n"
                f"--{boundary}\r\n"
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode("utf-8") + media + f"\r\n--{boundary}--\r\n".encode("utf-8")

            return headers, body

        def build_params():
            return {
                "uploadType": "multipart",
                "supportsAllDrives": str(supports_all_drives).lower(),
            }

        if not file_in_bytes:
            raise ValueError("Must provide file_in_bytes")

        mime_type = mime_type or "application/octet-stream"
        file_metadata = build_metadata()
        headers, body = build_multipart_body(file_in_bytes, file_metadata, mime_type)
        params = build_params()

        response = self._request(
            "POST", UPLOAD_URL, headers=headers, params=params, data=body
        )
        return response.json()

    def update_file(
        self,
        file_id: str,
        file_in_bytes_or_path: Optional[Union[str, bytes]] = None,
        mime_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        def params_metadata_and_media(
            media,
            metadata,
            mime_type,
            upload_type: Literal["multipart", "resumable"] = "multipart",
        ):
            boundary = "END_OF_PART_1234567890"
            headers = {
                **self._hdrs,
                "Content-Type": f"multipart/related; boundary={boundary}",
            }

            data = (
                f"--{boundary}\r\n"
                "Content-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{json.dumps(metadata)}\r\n"
                f"--{boundary}\r\n"
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode("utf-8") + media + f"\r\n--{boundary}--\r\n".encode("utf-8")

            params = {"uploadType": upload_type, "supportsAllDrives": True}
            return {"headers": headers, "data": data, "params": params}

        def params_metadata_only(metadata):
            headers = {**self._hdrs, "Content-Type": "application/json"}
            return {
                "headers": headers,
                "json": metadata,
                "params": {"supportsAllDrives": True},
            }

        def params_media_only(media, mime_type):
            headers = {**self._hdrs, "Content-Type": mime_type}
            return {
                "headers": headers,
                "data": media,
                "params": {"supportsAllDrives": True, "uploadType": "media"},
            }

        file_in_bytes: bytes | None = None
        if isinstance(file_in_bytes_or_path, str):
            with open(file_in_bytes_or_path, "rb") as handle:
                file_in_bytes = handle.read()
        elif isinstance(file_in_bytes_or_path, bytes):
            file_in_bytes = file_in_bytes_or_path

        if file_in_bytes and metadata:
            mime_type = mime_type or "application/octet-stream"
            request_params = params_metadata_and_media(file_in_bytes, metadata, mime_type)
        elif file_in_bytes and not metadata:
            mime_type = mime_type or "application/octet-stream"
            request_params = params_media_only(file_in_bytes, mime_type)
        elif file_in_bytes is None and metadata:
            request_params = params_metadata_only(metadata)
        else:
            raise ValueError("Must provide either file_in_bytes or metadata (or both)")

        response = self._request(
            "PATCH", f"{UPLOAD_URL}/{file_id}", **request_params
        )
        return response.json()

    def create_folder(self, parent_folder_id: str, name: str) -> Dict[str, Any]:
        headers = {**self._hdrs, "Content-Type": "application/json; charset=UTF-8"}
        payload = {
            "name": name,
            "mimeType": FOLDER_MIME,
            "parents": [parent_folder_id],
        }
        response = self._request(
            "POST",
            f"{DRIVE_URL}/files",
            headers=headers,
            params={"supportsAllDrives": "true"},
            data=json.dumps(payload),
        )
        return response.json()

    def get_from_weburl(self, web_url: str, fields: str = "*") -> "GDriveItem":
        """Return metadata for a Google Drive file or folder given a web URL,
        mapped to the unified :class:`GDriveItem` model.
        """
        file_id = self._extract_id_from_url(web_url)
        metadata = self.get_file(file_id, fields=fields + ",mimeType,webViewLink")
        return self._to_item(metadata, scope_root=True)

    def _to_item(
        self,
        raw_metadata: dict[str, Any],
        *,
        current_rel_path: str = "",
        scope_root: bool = False,
    ) -> "GDriveItem":
        return GDriveItem(
            raw_metadata=raw_metadata,
            client=self,
            current_rel_path=current_rel_path,
            scope_root=scope_root,
        )

    def download_from_weburl(self, web_url: str, **kwargs) -> Union[bytes, str]:
        file_id = self._extract_id_from_url(web_url)
        return self.download_file(file_id, **kwargs)

    def export_from_weburl(
        self, web_url: str, mime_type: Optional[str] = None, **kwargs
    ) -> Union[bytes, str]:
        file_id = self._extract_id_from_url(web_url)
        return self.export_file(file_id, mime_type, **kwargs)

    def update_from_weburl(self, web_url: str, **kwargs) -> Dict[str, Any]:
        file_id = self._extract_id_from_url(web_url)
        return self.update_file(file_id, **kwargs)

    @staticmethod
    def _extract_id_from_url(url: str) -> str:
        patterns = [
            r"/document/d/([a-zA-Z0-9_-]+)",
            r"/spreadsheets/d/([a-zA-Z0-9_-]+)",
            r"/presentation/d/([a-zA-Z0-9_-]+)",
            r"/file/d/([a-zA-Z0-9_-]+)",
            r"/folders/([a-zA-Z0-9_-]+)",
            r"(?:\?|&)id=([a-zA-Z0-9_-]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        raise ValueError(f"Could not extract Google Drive ID from URL: {url}")


GoogleApiDriveError = GoogleDriveError


__all__ = [
    "GoogleBaseClient",
    "GoogleDriveClient",
    "GDriveItem",
    "GDriveFile",
    "GDriveFolder",
]


class GDriveItem(DriveItem):
    """A Google Drive file or folder item backed by the Drive REST API.

    Whether an instance represents a file or a directory is determined at
    runtime by :attr:`is_directory` (based on ``mimeType``), so a single
    class handles both cases.  The previous ``GDriveFile`` / ``GDriveFolder``
    split has been consolidated here; backward-compatible aliases are kept at
    module level.
    """

    def __init__(
        self,
        raw_metadata: dict[str, Any],
        client: "GoogleDriveClient",
        current_rel_path: str = "",
        scope_root: bool = False,
    ):
        self.raw = raw_metadata
        self.client = client
        self._current_rel_path = current_rel_path
        self._scope_root = scope_root

    @property
    def id(self) -> str:
        return self.raw.get("id", "")

    @property
    def name(self) -> str:
        return self.raw.get("name", "")

    @property
    def path(self) -> str:
        relative_path = str(self.raw.get("relative_path", "")).strip()
        if relative_path:
            if self._current_rel_path:
                return f"{self._current_rel_path}/{relative_path}".strip("/")
            return relative_path
        if self._current_rel_path:
            return f"{self._current_rel_path}/{self.name}"
        return self.name

    @property
    def service_type(self) -> str:
        return "GoogleDrive"

    @property
    def source_url(self) -> str:
        return self.raw.get("webViewLink") or f"https://drive.google.com/open?id={self.id}"

    @property
    def is_directory(self) -> bool:
        return self.raw.get("mimeType") == FOLDER_MIME

    @property
    def children(self) -> list["GDriveItem"]:
        """Direct children of this directory; empty list for files."""
        if not self.is_directory:
            return []
        contents = self.raw.get("contents")
        if contents is None:
            contents = self.client.list_folder_contents(self.id, recursive=False)
            self.raw["contents"] = contents

        next_rel_path = "" if self._scope_root else self.path
        return [
            self.client._to_item(
                child_raw,
                current_rel_path=next_rel_path,
                scope_root=False,
            )
            for child_raw in contents
        ]

    def refresh(self, *, include_children: bool = True) -> "GDriveItem":
        """Re-fetch raw metadata (and optionally children) from the API."""
        refreshed = self.client.get_file(
            self.id,
            fields="id,name,mimeType,parents,webViewLink",
        )
        if self.is_directory:
            if include_children:
                refreshed["contents"] = self.client.list_folder_contents(
                    self.id,
                    recursive=False,
                )
            elif "contents" in self.raw:
                refreshed["contents"] = self.raw["contents"]
        self.raw = refreshed
        return self

    def download(self, target_dir: str | Path) -> None:
        """Download this item.

        Directories are walked recursively via :meth:`iter_files` and each
        leaf file is written relative to *target_dir*.  Files are written
        directly; Google Workspace files are exported to their default format.
        """
        if self.is_directory:
            super().download(target_dir)
            return
        target = Path(target_dir)
        if target.is_dir():
            target = target / self.name

        target.parent.mkdir(parents=True, exist_ok=True)
        content = self.client.download_file(self.id)
        if isinstance(content, bytes):
            with open(target, "wb") as f:
                f.write(content)
        else:
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)


# ---------------------------------------------------------------------------
# Backward-compatible aliases
# ---------------------------------------------------------------------------
# Old code that imports or subclasses ``GDriveFile`` / ``GDriveFolder`` will
# continue to work because these names now point to the unified ``GDriveItem``.
GDriveFile = GDriveItem
GDriveFolder = GDriveItem
