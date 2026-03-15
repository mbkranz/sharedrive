from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Sequence, Union

import requests
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request

from sharedrive.auth.base import CredentialStrategy
from sharedrive.auth.google import default_drive_strategy, normalize_google_scopes
from sharedrive.exceptions import GoogleApiError, GoogleAuthError, GoogleDriveError


class GoogleBaseClient:
    """Shared Google client base for auth lifecycle and HTTP transport helpers."""

    api_error_cls = GoogleApiError

    def __init__(
        self,
        *,
        credential_strategy: CredentialStrategy | None = None,
        credentials: Credentials | None = None,
        session: requests.Session | None = None,
        timeout: int = 120,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout

        if credentials is not None and credential_strategy is not None:
            raise ValueError(
                "Provide either credentials or credential_strategy, not both."
            )

        self._credential_strategy = credential_strategy

        if credentials is not None:
            self._creds = credentials
        elif self._credential_strategy is not None:
            self._creds = self._credential_strategy.build()
        else:
            raise ValueError(
                "GoogleBaseClient requires either credentials or credential_strategy."
            )

    def _ensure_valid_credentials(self) -> None:
        if self._creds.valid and self._creds.token:
            return

        try:
            self._creds.refresh(Request())
        except Exception as refresh_error:
            if self._credential_strategy is None:
                raise GoogleAuthError(
                    f"Failed to refresh Google credentials: {refresh_error}"
                ) from refresh_error
            try:
                self._creds = self._credential_strategy.build()
            except Exception as build_error:
                raise GoogleAuthError(
                    f"Failed to obtain valid Google credentials: {build_error}"
                ) from build_error

        if not self._creds.valid or not self._creds.token:
            raise GoogleAuthError("Credentials are missing a valid access token.")

    @property
    def _hdrs(self) -> dict[str, str]:
        self._ensure_valid_credentials()
        return {"Authorization": f"Bearer {self._creds.token}"}

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


class GoogleDriveClient(GoogleBaseClient):
    """
    Minimal Google Drive client (ID-first) with read/write and full export coverage for Google-native files.
    Uses ADC (google-auth). Works with My Drive and Shared Drives.

    For local dev with a service account, use:
        1. gcloud auth application-default login --impersonate-service-account <service-account-email>
        2. Or set the GOOGLE_APPLICATION_CREDENTIALS env var to point to a service account JSON key file.
    """

    api_error_cls = GoogleDriveError

    def __init__(
        self,
        credentials_path: str | None = None,
        scope: Sequence[str] | str | None = None,
        *,
        credential_strategy: CredentialStrategy | None = None,
        credentials: Credentials | None = None,
        session: requests.Session | None = None,
        timeout: int = 120,
    ):
        self.scopes = normalize_google_scopes(scope)
        self._credentials_path = credentials_path
        resolved_strategy = credential_strategy
        if credentials is None and resolved_strategy is None:
            resolved_strategy = default_drive_strategy(
                credentials_path=credentials_path,
                scopes=self.scopes,
            )

        super().__init__(
            credential_strategy=resolved_strategy,
            credentials=credentials,
            session=session,
            timeout=timeout,
        )

    @staticmethod
    def _is_google_workspace_file(file_mime_type: str) -> bool:
        return file_mime_type in {mime.value for mime in GoogleMimeTypes}

    def list_files(self):
        """List all files the authenticated user has access to."""
        files = []
        page_token = None

        while True:
            params = {
                "pageSize": 100,
                "fields": "nextPageToken, files(id, name, mimeType, parents)",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            if page_token:
                params["pageToken"] = page_token

            resp = self._request("GET", f"{DRIVE_URL}/files", params=params).json()
            files.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return files

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

    def get_from_weburl(self, web_url: str, fields: str = "*") -> Dict[str, Any]:
        file_id = self._extract_id_from_url(web_url)
        return self.get_file(file_id, fields=fields)

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
]
