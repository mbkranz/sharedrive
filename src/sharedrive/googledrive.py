import re
import json
import requests
from enum import Enum
from typing import Dict, Any, List, Literal, Optional, Union
import google.auth

# Google Auth SDK 
from google.auth.transport.requests import Request
import google

class GoogleApiError(Exception):
    """Custom exception for Google API errors."""
    def __init__(self, message, status_code=None, response_text=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text

class GoogleAuthError(GoogleApiError):
    """Custom exception for Google authentication errors."""
    pass

class GoogleApiDriveError(GoogleApiError):
    """Custom exception for Google Drive API errors."""
    pass



DRIVE_URL = "https://www.googleapis.com/drive/v3"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"

FOLDER_MIME = "application/vnd.google-apps.folder"

# Google-native MIME types

class GoogleMimeTypes(Enum):
    """Google-native MIME types."""
    DOC   = "application/vnd.google-apps.document"
    SHEET = "application/vnd.google-apps.spreadsheet"
    SLIDE = "application/vnd.google-apps.presentation"
    DRAW  = "application/vnd.google-apps.drawing"
    FORM  = "application/vnd.google-apps.form"
    JAM   = "application/vnd.google-apps.jam"
    APP   = "application/vnd.google-apps.script"
    SHORT = "application/vnd.google-apps.shortcut"


# Handy default export targets by Google-native type
DEFAULT_EXPORTS = {
    GoogleMimeTypes.DOC.value:   "application/vnd.openxmlformats-officedocument.wordprocessingml.document",                             # alt: application/vnd.openxmlformats-officedocument.wordprocessingml.document
    GoogleMimeTypes.SHEET.value: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # alt: text/csv (per-sheet)
    GoogleMimeTypes.SLIDE.value: "application/pdf",                             # alt: application/vnd.openxmlformats-officedocument.presentationml.presentation
    GoogleMimeTypes.DRAW.value:  "application/pdf",                             # alt: image/png, image/jpeg, image/svg+xml
    GoogleMimeTypes.FORM.value:  "application/pdf",
    GoogleMimeTypes.JAM.value:   "application/pdf",
    GoogleMimeTypes.APP.value:   "application/zip",                             # exports Apps Script project as ZIP
}

# Common alternates you might want
ALT_EXPORTS = {
    "docx": "application/pdf",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv":  "text/csv",
    "pdf":  "application/pdf",
    # "png":  "image/png",
    # "jpeg": "image/jpeg",
    # "svg":  "image/svg+xml",
    # "zip":  "application/zip",
}


class GoogleDriveClient:
    """
    Minimal Google Drive client (ID-first) with read/write and full export coverage for Google-native files.
    Uses ADC (google-auth). Works with My Drive and Shared Drives.

    For local dev with a service account, use:
        1. gcloud auth application-default login --impersonate-service-account <service-account-email>
        2. Or set the GOOGLE_APPLICATION_CREDENTIALS env var to point to a service account JSON key file.
    """

    def __init__(self, credentials_path: str, scope: Optional[List[str]] = None):
        # For read+write, 'drive.file' is a good least-privilege default.
        self.scopes = scope or ["https://www.googleapis.com/auth/drive"]

        if credentials_path:
            self._creds = google.auth.load_credentials_from_file(credentials_path, scopes=self.scopes,default_scopes=self.scopes)[0]
        else:
            self._creds, _ = google.auth.default()
            self._creds = self._creds.with_scopes(self.scopes)

        self._creds.refresh(Request())
        self._token = self._creds.token

    @property
    def _hdrs(self):
        return {"Authorization": f"Bearer {self._token}"}

    # ----------------------------------------------------------------------
    # Metadata / listing
    # ----------------------------------------------------------------------

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

            r = requests.get(f"{DRIVE_URL}/files", headers=self._hdrs, params=params)
            r.raise_for_status()
            resp = r.json()
            files.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return files


    def get_file(self, file_id: str, **kwargs) -> Dict[str, Any]:
        endpoint = f"{DRIVE_URL}/files/{file_id}"
        r = requests.get(endpoint, headers=self._hdrs, params={"supportsAllDrives": "true", **kwargs})
        r.raise_for_status()
        return r.json()
    
    def infer_export_mime_type(self, file_id: str) -> Optional[str]:
        """
        Infer the best export MIME type for a Google Workspace file based on its native type.
        
        Args:
            file_id: The ID of the file to check.
            
        Returns:
            Recommended export MIME type from DEFAULT_EXPORTS, or None if not a Google Workspace file.
        """
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
        **kwargs
    ) -> Union[bytes, str]:
        """
        Download file content (handles both regular files and Google Workspace documents automatically).
        
        This method intelligently detects the file type:
        - Google Workspace files (Docs, Sheets, Slides, etc.) → automatically exports to appropriate format
        - Regular files (PDFs, images, videos, etc.) → downloads directly

        Note:
            Download (binary/original) vs Export (google-native)
            - Use download_file for regular files (returns original content).
            - Use export_file (or download_file which delegates) for Google Workspace native files, which must be exported.

        Args:
            file_id: The ID of the file to download.
            output_path: Optional path to save file to disk. If provided, streams to disk (memory-efficient).
                        If None, returns file content as bytes (loads entire file into memory).
            mime_type: For Google Workspace files, the target export format (e.g., 'application/pdf').
                      If not provided for Google Workspace files, will auto-select from DEFAULT_EXPORTS.
                      Ignored for regular file downloads.
            acknowledge_abuse: Set to True to acknowledge risk of downloading potentially harmful content.
            byte_range: Partial download range (e.g., "bytes=500-999"). Only works for regular files.
            supports_all_drives: Whether to include shared drive items.
            **kwargs: Additional parameters (reserved for future use).
            
        Returns:
            If output_path is None: File content as bytes.
            If output_path is provided: Path to the downloaded file (str).
            
        Raises:
            requests.HTTPError: If the request fails.
            ValueError: If Google Workspace file type cannot determine export format.
            
        Note:
            For large files, provide output_path to avoid loading entire file into memory.
            For small files (<10MB), either approach works fine.
            
        Examples:
            # Google Doc → auto-exports to .docx
            doc_bytes = client.download_file(doc_id)
            
            # Google Sheet → auto-exports to .xlsx
            client.download_file(sheet_id, output_path="data.xlsx")
            
            # Regular PDF → downloads as-is
            pdf_bytes = client.download_file(pdf_id)
            
            # Override export format for Google files
            pdf_bytes = client.download_file(doc_id, mime_type="application/pdf")
        """
        
        def is_google_workspace_file(file_mime_type: str) -> bool:
            """Check if file is a Google Workspace native type."""
            return file_mime_type in [mime.value for mime in GoogleMimeTypes]
        
        def build_params():
            """Build request parameters for download."""
            params = {
                "alt": "media",
                "supportsAllDrives": str(supports_all_drives).lower()
            }
            if acknowledge_abuse:
                params["acknowledgeAbuse"] = "true"
            return params
        
        def build_headers():
            """Build request headers for download."""
            headers = dict(self._hdrs)
            if byte_range:
                headers["Range"] = byte_range
            return headers
        
        # Check file type to determine download vs export
        file_metadata = self.get_file(file_id, fields="mimeType")
        file_mime_type = file_metadata.get("mimeType", "")
        
        # If it's a Google Workspace file, use export instead
        if is_google_workspace_file(file_mime_type):
            # Delegate to export_file with all relevant parameters
            return self.export_file(
                file_id=file_id,
                mime_type=mime_type,
                output_path=output_path,
                supports_all_drives=supports_all_drives,
                **kwargs
            )
        else:
            
            # Regular file download
            r = requests.get(
                f"{DRIVE_URL}/files/{file_id}",
                headers=build_headers(),
                params=build_params(),
                stream=True,
            )
            r.raise_for_status()
            
            # Stream to file if output_path provided (memory-efficient)
            if output_path:
                with open(output_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return output_path
            
            # Return as bytes if no output_path (loads into memory)
            return b"".join(chunk for chunk in r.iter_content(chunk_size=8192) if chunk)

    def export_file(
        self,
        file_id: str,
        mime_type: Optional[str] = None,
        output_path: Optional[str] = None,
        supports_all_drives: bool = True,
        **kwargs
    ) -> Union[bytes, str]:
        """
        Export Google Workspace document content to a specific format.
        
        Args:
            file_id: The ID of the Google Workspace file to export.
            mime_type: Target MIME type for export (e.g., 'application/pdf'). 
                      If not provided, will infer from DEFAULT_EXPORTS based on file type.
            output_path: Optional path to save exported file to disk.
                        If None, returns file content as bytes.
            supports_all_drives: Whether to include shared drive items.
            **kwargs: Additional parameters (reserved for future use).
            
        Returns:
            If output_path is None: Exported file content as bytes (limited to 10 MB by Google).
            If output_path is provided: Path to the exported file (str).
            
        Raises:
            ValueError: If mime_type cannot be inferred and is not provided.
            requests.HTTPError: If the request fails.
            
        Note:
            Use DEFAULT_EXPORTS or ALT_EXPORTS constants for common conversions.
            If mime_type is not specified, the method will automatically select the
            best export format based on the file's native Google Workspace type.
            Google Drive exports are limited to 10MB, so memory usage is not a concern.
        """
        
        def build_params(target_mime: str):
            """Build request parameters for export."""
            return {
                "mimeType": target_mime, 
                "supportsAllDrives": str(supports_all_drives).lower()
            }
        
        # Infer MIME type if not provided
        if mime_type is None:
            inferred_mime = self.infer_export_mime_type(file_id)
            if inferred_mime is None:
                raise ValueError(
                    f"Could not infer export MIME type for file {file_id}. "
                    "Please provide mime_type parameter explicitly."
                )
            mime_type = inferred_mime
        
        # Execute request
        r = requests.get(
            f"{DRIVE_URL}/files/{file_id}/export",
            headers=self._hdrs,
            params=build_params(mime_type),
            stream=True,
        )
        r.raise_for_status()
        
        # Stream to file if output_path provided
        if output_path:
            with open(output_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return output_path
        
        # Return as bytes if no output_path
        return b"".join(chunk for chunk in r.iter_content(chunk_size=8192) if chunk)

    # ----------------------------------------------------------------------
    # Upload / Create / Update (write)
    # ----------------------------------------------------------------------

    def create_file(
        self,
        parent_folder_id: str,
        file_in_bytes: Optional[bytes] = None,
        mime_type: Optional[str] = None,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        supports_all_drives: bool = True,
        # use_content_as_indexable_text: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a new file via multipart upload (for files ≤5MB).
        
        Args:
            parent_folder_id: ID of the parent folder.
            file_in_bytes: File content as bytes.
            mime_type: MIME type (defaults to 'application/octet-stream' if not provided).
            name: File name (required).
            metadata: Additional metadata fields (description, properties, etc.).
            supports_all_drives: Whether to include shared drive items.
            use_content_as_indexable_text: Add file content to Drive's search index.
            **kwargs: Additional parameters (reserved for future use).
            
        Returns:
            File metadata as dict with 'id', 'name', 'mimeType', etc.
            
        Raises:
            ValueError: If file_in_bytes or name is not provided.
            requests.HTTPError: If the request fails.
        """
        
        def build_metadata():
            """Build file metadata with parent folder."""
            if not name:
                raise ValueError("Must provide name parameter")
            
            file_metadata = {"name": name, "parents": [parent_folder_id]}
            if metadata:
                file_metadata.update(metadata)
            return file_metadata
        
        def build_multipart_body(media, file_metadata, mime_type):
            """Build multipart request body with metadata and media."""
            boundary = "END_OF_PART_1234567890"
            headers = {**self._hdrs, "Content-Type": f"multipart/related; boundary={boundary}"}
            
            body = (
                f"--{boundary}\r\n"
                "Content-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{json.dumps(file_metadata)}\r\n"
                f"--{boundary}\r\n"
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode("utf-8") + media + f"\r\n--{boundary}--\r\n".encode("utf-8")
            
            return headers, body
        
        def build_params():
            """Build request parameters."""
            params = {"uploadType": "multipart", "supportsAllDrives": str(supports_all_drives).lower()}
            # if use_content_as_indexable_text:
            #     params["useContentAsIndexableText"] = "true"
            return params
        
        # Validate and prepare
        if not file_in_bytes:
            raise ValueError("Must provide file_in_bytes")
        
        mime_type = mime_type or "application/octet-stream"
        file_metadata = build_metadata()
        headers, body = build_multipart_body(file_in_bytes, file_metadata, mime_type)
        params = build_params()
        
        # Execute request
        r = requests.post(UPLOAD_URL, headers=headers, params=params, data=body)
        r.raise_for_status()
        return r.json()

    def update_file(
        self, 
        file_id: str, 
        file_in_bytes_or_path: Optional[Union[str, bytes]] = None,
        mime_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Update file content and/or metadata.
        
        Args:
            file_id: ID of the file to update.
            file_in_bytes: New file content as bytes (optional).
            mime_type: MIME type (defaults to 'application/octet-stream' if not provided).
            metadata: File metadata to update (name, description, properties, etc.).
            **kwargs: Additional parameters (reserved for future use).

        Returns:
            Updated file metadata as dict.
            
        Raises:
            ValueError: If neither file_in_bytes nor metadata is provided.
            requests.HTTPError: If the request fails.
        """

        def params_metadata_and_media(media, metadata, mime_type, upload_type: Literal["multipart", "resumable"] = "multipart"):
            """Build request params for combined metadata + media update."""
            boundary = "END_OF_PART_1234567890"
            headers = {**self._hdrs, "Content-Type": f"multipart/related; boundary={boundary}"}
            
            data = (
                f"--{boundary}\r\n"
                "Content-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{json.dumps(metadata)}\r\n"
                f"--{boundary}\r\n"
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode("utf-8") + media + f"\r\n--{boundary}--\r\n".encode("utf-8")

            params = {
                "uploadType": upload_type,
                "supportsAllDrives": True
            }
            return {"headers": headers, "data": data, "params": params}

        def params_metadata_only(metadata):
            """Build request params for metadata-only update."""
            headers = {**self._hdrs, "Content-Type": "application/json"}
            return {"headers": headers, "json": metadata, "params": {"supportsAllDrives": True}}

        def params_media_only(media, mime_type):
            """Build request params for media-only update."""
            headers = {**self._hdrs, "Content-Type": mime_type}
            return {"headers": headers, "data": media, "params": {
                "supportsAllDrives": True,
                "uploadType": "media"}}

        # Determine update type and build request params

        if isinstance(file_in_bytes_or_path, str):
            with open(file_in_bytes_or_path, 'rb') as f:
                file_in_bytes = f.read()


        if file_in_bytes and metadata:
            # Both media and metadata
            mime_type = mime_type or "application/octet-stream"
            request_params = params_metadata_and_media(file_in_bytes, metadata, mime_type)
        elif file_in_bytes and not metadata:
            # Media only
            mime_type = mime_type or "application/octet-stream"
            request_params = params_media_only(file_in_bytes, mime_type)
        elif file_in_bytes is None and metadata:
            # Metadata only
            request_params = params_metadata_only(metadata)
        else:
            # Neither provided
            raise ValueError("Must provide either file_in_bytes or metadata (or both)")
        
        # Execute request
        r = requests.patch(f"{UPLOAD_URL}/{file_id}", **request_params)
        r.raise_for_status()
        return r.json()


    def create_folder(self, parent_folder_id: str, name: str) -> Dict[str, Any]:
        """Create a folder under a parent folder ID."""
        headers = {**self._hdrs, "Content-Type": "application/json; charset=UTF-8"}
        payload = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_folder_id]}
        r = requests.post(
            f"{DRIVE_URL}/files",
            headers=headers,
            params={"supportsAllDrives": "true"},
            data=json.dumps(payload),
        )
        r.raise_for_status()
        return r.json()

    # ----------------------------------------------------------------------
    # Web URL wrappers
    # ----------------------------------------------------------------------

    def get_from_weburl(self, web_url: str, fields: str = "*") -> Dict[str, Any]:
        """Extract ID from a Drive URL and return metadata."""
        file_id = self._extract_id_from_url(web_url)
        return self.get_file(file_id)

    def download_from_weburl(self, web_url: str, **kwargs) -> bytes:
        """
        Extract ID from a Drive URL and download.
        Forwards all kwargs to download_file() method.
        """
        file_id = self._extract_id_from_url(web_url)
        return self.download_file(file_id, **kwargs)

    def export_from_weburl(self, web_url: str, mime_type: Optional[str] = None, **kwargs) -> bytes:
        """
        Extract ID from a Drive URL and export to a specific MIME type.
        If mime_type is not provided, it will be inferred from DEFAULT_EXPORTS.
        Forwards all kwargs to export_file() method.
        """
        file_id = self._extract_id_from_url(web_url)
        return self.export_file(file_id, mime_type, **kwargs)
    
    def update_from_weburl(
        self, 
        web_url: str, 
        **kwargs
    ) -> Dict[str, Any]:
        """
        Extract ID from a Drive URL and update file content and/or metadata.
        Forwards all kwargs to update_file() method.
        """
        file_id = self._extract_id_from_url(web_url)
        return self.update_file(file_id, **kwargs)

    # ----------------------------------------------------------------------
    # Utilities
    # ----------------------------------------------------------------------

    @staticmethod
    def _extract_id_from_url(url: str) -> str:
        patterns = [
            r"/document/d/([a-zA-Z0-9_-]+)",
            r"/file/d/([a-zA-Z0-9_-]+)",
            r"/folders/([a-zA-Z0-9_-]+)",
            r"(?:\?|&)id=([a-zA-Z0-9_-]+)",
        ]
        for pat in patterns:
            m = re.search(pat, url)
            if m:
                return m.group(1)
        raise ValueError(f"Could not extract Google Drive ID from URL: {url}")
