from __future__ import annotations
from functools import cached_property
import json
from pathlib import Path
import re
from enum import Enum
from typing import Any, ClassVar, Dict, Literal, Optional, Union

import requests
from pydantic import BaseModel
from google.auth.credentials import Credentials
from sharedrive.item import  ServiceItem

from sharedrive.auth.google import GoogleAuth
from sharedrive.clients.base import AdapterCapabilities, BaseClient
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
    capabilities: ClassVar[AdapterCapabilities] = AdapterCapabilities(
        supports_fetch=True,
        supports_download=True,
        supports_auth_check=True,
        supports_write=False,
    )

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
        if not self._auth._creds.valid:
            self.refresh()
        return {"Authorization": f"Bearer {self._auth.credentials.token}"}

    def refresh(self) -> None:
        self._auth.refresh()

    def get_from_weburl(self, url: str):
        raise NotImplementedError

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

class GDriveApiFile(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    mimeType: Optional[str] = None
    parents: Optional[list[str]] = None
    driveId: Optional[str] = None
    webViewLink: Optional[str] = None
    webContentLink: Optional[str] = None
    exportLinks: Optional[dict[str, str]] = None
    modifiedTime: Optional[str] = None
    createdTime: Optional[str] = None
    size: Optional[int] = None
    md5Checksum: Optional[str] = None
    trashed: Optional[bool] = None

class GDriveApiFolderFiles(BaseModel):
    files: list[GDriveApiFile] = []

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

    api_error_cls = GoogleDriveError
    file_fields = [
        "id",
        "name",
        "mimeType",
        "parents",
        "driveId",
        "webViewLink",
        "webContentLink",
        "exportLinks",
        "modifiedTime",
        "createdTime",
        "size",
        "md5Checksum",
        "trashed"
    ]

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

    @staticmethod
    def _is_google_workspace_file(file_mime_type: str) -> bool:
        return file_mime_type in {mime.value for mime in GoogleMimeTypes}

    def list_files(
        self,
        folder_file_id: str,
        page_size: int = 100,
    ) -> list[GDriveApiFile]:
        """List all files the authenticated user has access to."""
        files = []
        page_token = None

        while True:
            params = {
                "pageSize": page_size,
                "fields": f"nextPageToken, files({', '.join(self.file_fields)})",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
                "query":f"'{folder_file_id}' in parents and trashed = false",
            }
            if page_token:
                params["pageToken"] = page_token

            resp = self._request("GET", f"{DRIVE_URL}/files", params=params).json()
            files.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return [GDriveApiFile(**f) for f in files]

    def get_file(self, file_id: str, **kwargs) -> GDriveApiFile:
        endpoint = f"{DRIVE_URL}/files/{file_id}"
        response = self._request(
            "GET", endpoint, params={"supportsAllDrives": "true", **kwargs}
        )
        return GDriveApiFile(**response.json())

    def infer_export_mime_type(self, file_id: str) -> Optional[str]:
        file_metadata = self.get_file(file_id, fields="mimeType")
        source_mime = file_metadata.mimeType or ""
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
        file_mime_type = file_metadata.mimeType or ""

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
            f"{DRIVE_URL}/files/{str(file_id)}",
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
            f"{DRIVE_URL}/files/{str(file_id)}/export",
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

    def get_from_weburl(self, url: str) -> GDriveItem:
        """Return metadata for a Google Drive file or folder given a web URL,
        mapped to the unified :class:`GDriveItem` model.
        """
        file_id = self._extract_id_from_url(str(url))
        metadata = self.get_file(file_id)
        return GDriveItem.from_api_response(api_metadata=metadata,client=self)

    def download_from_weburl(self, url: str, **kwargs) -> Union[bytes, str]:
        #TODO: deprecate given ServiceItem now handles?
        file_id = self._extract_id_from_url(url)
        return self.download_file(file_id, **kwargs)

    def export_from_weburl(
        self, url: str, mime_type: Optional[str] = None, **kwargs
    ) -> Union[bytes, str]:
        file_id = self._extract_id_from_url(url)
        return self.export_file(file_id, mime_type, **kwargs)

    def update_from_weburl(self, url: str, **kwargs) -> Dict[str, Any]:
        file_id = self._extract_id_from_url(url)
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


class GDriveItem(ServiceItem):
    """A Google Drive file or folder item backed by the Drive REST API.

    Whether an instance represents a file or a directory is determined at
    runtime by :attr:`is_directory` (based on ``mimeType``). 
    
    
    TODO: split to GDriveFile and GDriveFolder and then make GDriveItem a union type?
    TODO: have capability of event driven workflows: https://developers.google.com/workspace/events/guides/events-drive
    
    
    API Resource References
    -------
    https://developers.google.com/workspace/drive/api/reference/rest/v3/files#File
    """
    serviceType = "GoogleDrive"
    def __init__(
        self,
        client: "GoogleDriveClient",
        metadata: dict[str, Any] | None = None,
        basepath: str | None = None,
        path: str | None = None,
        id: str | None = None,
        name: str | None = None,
        source_url: str | None = None,
        parent_id: str | None = None,
        service_id: str | None = None,
        mime_type: str | None = None,
    ):
        self._client = client
        self._metadata = metadata
        self._basepath = basepath
        self._path = path
        self._id = id
        self._name = name
        self._source_url = source_url
        self._parent_id = parent_id
        self._service_id = service_id
        self._mime_type = mime_type

    _resolved_path: Optional[str] = None
    _resolved_path_depth: Optional[int] = None
    _resolved_path_root_id: Optional[str] = None

    @classmethod
    def from_weburl(cls, url: str, client: "GoogleDriveClient") -> "GDriveItem":
        return client.get_from_weburl(url)

    @classmethod
    def from_api_response(cls, api_metadata: Union[GDriveApiFile, GDriveApiFolderFiles], client: "GoogleDriveClient", basepath: Optional[str] = None) -> "GDriveItem":
        
        parents = api_metadata.parents or [None]
        if len(parents) > 1:
            raise ValueError(f"Item {api_metadata.name} has multiple parents, which is not supported by GDriveItem model")
        else:
            _parent_id = parents[0]
            
        if isinstance(api_metadata, GDriveApiFile):
            paths = dict(basepath = basepath,path = api_metadata.name)
        elif isinstance(api_metadata, GDriveApiFolderFiles):
            paths = dict(basepath = f"{basepath}/{api_metadata.name}" if basepath else api_metadata.name,path = api_metadata.name)
        else:
            raise ValueError(f"Unexpected child metadata type: {type(api_metadata)}. Expected GDriveApiFile or GDriveApiFolderFiles.")
        
        return cls(
            client=client,  
            path=api_metadata.name,
            service_id=api_metadata.id,
            parent_id=_parent_id,
            mime_type=api_metadata.mimeType,
            source_url=api_metadata.webViewLink,
            **paths
        )

    @property
    def parent(self) -> Optional["GDriveItem"]:
        if self._parent_id:
            parent_metadata = self._client.get_file(self._parent_id)
            return GDriveItem.from_api_response(api_metadata=parent_metadata, client=self._client)
        return None

    @property
    def resolved_path(self) -> Optional[str]:
        return self._resolved_path

    @property
    def resolved_path_depth(self) -> Optional[int]:
        return self._resolved_path_depth

    def resolve_path(self, depth: Optional[int] = None) -> str:
        current_node: GDriveItem = self
        path_parts = [self.name]
        current_depth = 0
        
        while current_node._parent_id:
            if depth is not None and current_depth >= depth:
                break
            # the parent is a GDriveItem, we can fetch it via `.parent` property
            parent_node = current_node.parent
            if parent_node is None:
                break
            
            path_parts.insert(0, parent_node.name)
            current_node = parent_node
            current_depth += 1
            
        self._resolved_path = "/".join([p for p in path_parts if p is not None])
        self._resolved_path_depth = current_depth
        self._resolved_path_root_id = current_node._service_id
        return self._resolved_path

    @cached_property
    def children(self) -> list["GDriveItem"]:
        """Direct children of this directory; empty list for files."""
        if not self.is_directory:
            return []
        
        children = self._client.list_files(folder_file_id=self._service_id) 
        return [GDriveItem.from_api_response(api_metadata=child, client=self._client) for child in children]

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def path(self) -> str:
        return self._path
    
    @path.setter
    def path(self, new_path: str) -> None:
        self._path = new_path

    @property
    def source_url(self) -> str:
        return self._source_url

    @property
    def is_directory(self) -> bool:
        return self._mime_type == FOLDER_MIME



        
    def refresh(self, *, include_children: bool = True) -> "GDriveItem":
        """Re-fetch raw metadata (and optionally children) from the API."""
        refreshed = self.client.get_file(
            self.id,
            fields="id,name,mimeType,parents,webViewLink",
        )
        # Update attributes directly
        self._name = refreshed.name
        self._path = refreshed.name # usually path corresponds to name if not fully resolved
        self._mime_type = refreshed.mimeType
        self._source_url = refreshed.webViewLink
        if refreshed.parents and len(refreshed.parents) > 0:
            self._parent_id = refreshed.parents[0]

        if self.is_directory and include_children:
            # simply trigger a cache flush if cached_property supports it
            if 'children' in self.__dict__:
                del self.__dict__['children']
                
        return self
    
    def export(self, target_mime_type: Optional[str] = None, output_path: Optional[str] = None) -> Union[bytes, str]:
        """Export this item if it's a Google Workspace file, otherwise download it.

        Google Workspace files are exported to their default format or to
        *target_mime_type* if provided.  Non-Google files are downloaded as-is.
        """
        if not self._is_google_workspace_file(self.raw.get("mimeType", "")):
            return self.download(target_dir=output_path) if output_path else self.client.download_file(self.id)

        return self.client.export_file(
            file_id=self.id,
            mime_type=target_mime_type,
            output_path=output_path,
        )
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
