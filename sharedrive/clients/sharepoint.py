from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import unquote, urlparse


import requests

from sharedrive.clients.base import AdapterCapabilities, BaseClient
from sharedrive.exceptions import GraphApiDriveError, GraphApiSiteError
from sharedrive.item import ServiceItem
from sharedrive.registry import provider

if TYPE_CHECKING:
    from sharedrive.auth.microsoft import MicrosoftAuth


@provider("sharepoint")
class SharepointClient(BaseClient):
    """SharePoint / OneDrive client backed by the Microsoft Graph API.

    Supports both app-only (client credentials) and delegated auth via
    :class:`~sharedrive.auth.microsoft.MicrosoftAuth`.

    Instantiate via a :class:`~sharedrive.auth.microsoft.MicrosoftAuth` object::

        auth = MicrosoftAuth.from_app_only(tenant_id, client_id, client_secret)
        client = SharepointClient(auth, host_url="contoso.sharepoint.com")

        # Or from environment variables / .env file:
        client = SharepointClient.build_default()

    The *access_token* keyword argument is a low-level escape hatch kept for
    tests only; prefer :class:`~sharedrive.auth.microsoft.MicrosoftAuth` in all
    production code.

    The class is registered as the ``"sharepoint"`` provider via the
    :func:`~sharedrive.registry.provider` decorator; use
    :func:`~sharedrive.registry.build_service_registry` to obtain a
    :class:`~sharedrive.registry.ServiceAdapter` for it.

    Microsoft Graph API reference:
        https://learn.microsoft.com/en-us/graph/api/resources/onedrive?view=graph-rest-1.0
    """

    auth_methods: ClassVar[list[str]] = ["app_only", "delegated"]
    capabilities: ClassVar[AdapterCapabilities] = AdapterCapabilities(
        supports_fetch=True,
        supports_download=True,
        supports_auth_check=True,
        supports_write=False,
    )

    def __init__(
        self,
        auth: "MicrosoftAuth | None" = None,
        host_url: str = "norc.sharepoint.com",
        *,
        access_token: str | None = None,
    ):
        self.host_url = host_url or "norc.sharepoint.com"

        if auth is not None and access_token is not None:
            raise ValueError("Provide either auth or access_token, not both.")

        if access_token is not None:
            self.access_token = access_token
        elif auth is not None:
            self.access_token = auth.access_token
        else:
            raise ValueError(
                "SharepointClient requires either auth or access_token."
            )

        self.auth_header = {"Authorization": f"Bearer {self.access_token}"}

    @classmethod
    def build_default(cls) -> "SharepointClient":
        """Construct from environment variables / settings.

        Reads ``SHAREPOINT_AUTH_MODE``, ``AZURE_TENANT_ID``, ``AZURE_CLIENT_ID``,
        ``AZURE_CLIENT_SECRET``, and ``SHAREPOINT_HOST_URL`` from the environment
        or a ``.env`` file via
        :class:`~sharedrive.auth.settings.MicrosoftAuthConfig`.
        """
        from sharedrive.auth.settings import MicrosoftAuthConfig

        config = MicrosoftAuthConfig()
        auth = config.to_auth()
        return cls(auth=auth, host_url=config.host_url)

    @classmethod
    def check_auth(cls) -> None:
        """Validate that Microsoft Graph credentials are available.

        Raises :class:`~sharedrive.exceptions.GraphAuthError` if the
        credentials configured in the environment are missing or invalid.
        """
        from sharedrive.auth.settings import MicrosoftAuthConfig

        config = MicrosoftAuthConfig()
        config.to_auth()

    def _request_json(
        self, endpoint: str, *, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            response = requests.get(endpoint, headers=self.auth_header, params=params)
            response.raise_for_status()
        except requests.exceptions.HTTPError as http_err:
            raise GraphApiDriveError(
                f"HTTP error while calling Microsoft Graph\n"
                f"URL: {response.url}\n"
                f"Status: {response.status_code} - {response.reason}\n"
                f"Details: {response.text}",
                status_code=response.status_code,
                response_text=response.text,
            ) from http_err
        except requests.exceptions.RequestException as req_err:
            raise GraphApiDriveError(
                f"Request error when calling {endpoint}: {req_err}"
            ) from req_err

        response_json = response.json()

        # Handle pagination for collection endpoints (e.g., drives, children)
        if "@odata.nextLink" in response_json:
            current_json = response_json
            while "@odata.nextLink" in current_json:
                next_link = current_json["@odata.nextLink"]
                try:
                    next_resp = requests.get(next_link, headers=self.auth_header)
                    next_resp.raise_for_status()
                except requests.exceptions.HTTPError as http_err:
                    raise GraphApiDriveError(
                        f"HTTP error while calling Microsoft Graph (pagination)\n"
                        f"URL: {next_resp.url}\n"
                        f"Status: {next_resp.status_code} - {next_resp.reason}\n"
                        f"Details: {next_resp.text}",
                        status_code=next_resp.status_code,
                        response_text=next_resp.text,
                    ) from http_err
                except requests.exceptions.RequestException as req_err:
                    raise GraphApiDriveError(
                        f"Request error when calling {next_link}: {req_err}"
                    ) from req_err

                current_json = next_resp.json()
                # Aggregate items if "value" array exists
                if "value" in response_json and "value" in current_json:
                    response_json["value"].extend(current_json.get("value", []))

            # Remove the nextLink from final aggregated response
            response_json.pop("@odata.nextLink", None)

        return response_json

    def get_site_id(self, site_name):
        endpoint = (
            f"https://graph.microsoft.com/v1.0/sites/{self.host_url}:/sites/{site_name}"
        )
        try:
            response = requests.get(endpoint, headers=self.auth_header)
            response.raise_for_status()
            site_data = response.json()
        except requests.exceptions.HTTPError as http_err:
            raise GraphApiSiteError(
                f"HTTP error fetching site ID for '{site_name}'\n"
                f"URL: {endpoint}\n"
                f"Status: {response.status_code} - {response.reason}\n"
                f"Details: {response.text}"
            ) from http_err
        except requests.exceptions.RequestException as req_err:
            raise GraphApiDriveError(
                f"Request error when calling {endpoint}: {req_err}"
            ) from req_err

        if "id" not in site_data:
            raise GraphApiDriveError(
                f"Site found but no 'id' returned.\n"
                f"Site Name: {site_name}\n"
                f"Response JSON: {json.dumps(site_data, indent=2)}"
            )

        return site_data["id"]

    def list_site_drives(self, site_id: str) -> list[dict[str, Any]]:
        data = self._request_json(
            f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
        )
        value = data.get("value", [])
        if not isinstance(value, list):
            raise GraphApiDriveError(f"Unexpected drives response for site '{site_id}'")
        return value

    def get_drive_id(self, site_id, drive_name: str | None = None):
        """
        Retrieves the default document drive associated with a SharePoint site.
        """
        if drive_name is not None:
            normalized_drive_name = drive_name.strip().strip("/")
            for drive in self.list_site_drives(site_id):
                drive_id = drive.get("id")
                if not isinstance(drive_id, str) or not drive_id.strip():
                    continue

                candidate_names = {
                    str(drive.get("name", "")).strip(),
                    str(drive.get("driveType", "")).strip(),
                }
                web_url = str(drive.get("webUrl", "")).strip()
                if web_url:
                    # Unquote the path to convert %20 back to spaces
                    decoded_path = unquote(urlparse(web_url).path)
                    candidate_names.add(Path(decoded_path).name)

                if normalized_drive_name in {
                    value for value in candidate_names if value
                }:
                    return drive_id

            raise GraphApiDriveError(
                f"Drive '{normalized_drive_name}' was not found for site '{site_id}'."
            )

        endpoint = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"

        try:
            response = requests.get(endpoint, headers=self.auth_header)
            response.raise_for_status()
            drive_data = response.json()
        except requests.exceptions.HTTPError as http_err:
            raise GraphApiDriveError(
                f"HTTP error while retrieving drive for site '{site_id}'\n"
                f"URL: {endpoint}\n"
                f"Status: {response.status_code} - {response.reason}\n"
                f"Details: {response.text}"
            ) from http_err
        except requests.exceptions.RequestException as req_err:
            raise GraphApiDriveError(
                f"Request error calling {endpoint}: {req_err}"
            ) from req_err

        if "id" not in drive_data:
            raise GraphApiDriveError(
                f"Drive request succeeded but no 'id' field was returned.\n"
                f"Site ID: {site_id}\n"
                f"Response JSON:\n{json.dumps(drive_data, indent=2)}"
            )

        return drive_data["id"]

    def get_item_metadata(
        self,
        drive: str,
        *,
        item_path: str | None = None,
        item_id: str | None = None,
        fields: list[str] | None = None,
    ):
        """
        get item metadata based on relative file path or item id within the drive
        """
        if fields is None:
            fields = [
                "id",
                "name",
                "folder",
                "file",
                "parentReference",
                "webUrl",
                "lastModifiedDateTime",
            ]

        select_query = ",".join(fields)

        if item_id:
            endpoint = f"https://graph.microsoft.com/v1.0/drives/{drive}/items/{item_id}?$select={select_query}"
            children_endpoint = f"https://graph.microsoft.com/v1.0/drives/{drive}/items/{item_id}/children?$select={select_query}"
        else:
            normalized_itempath = str(item_path).strip() if item_path else "/"
            if not normalized_itempath:
                normalized_itempath = "/"
            if normalized_itempath == "/":
                endpoint = f"https://graph.microsoft.com/v1.0/drives/{drive}/root?$select={select_query}"
                children_endpoint = f"https://graph.microsoft.com/v1.0/drives/{drive}/root/children?$select={select_query}"
            else:
                if not normalized_itempath.startswith("/"):
                    normalized_itempath = f"/{normalized_itempath}"
                endpoint = f"https://graph.microsoft.com/v1.0/drives/{drive}/root:{normalized_itempath}?$select={select_query}"
                children_endpoint = f"https://graph.microsoft.com/v1.0/drives/{drive}/root:{normalized_itempath}:/children?$select={select_query}"

        metadata = self._request_json(endpoint)
        has_children = metadata.get("folder", {}).get("childCount", 0) > 0
        if has_children:
            list_of_children = self._request_json(children_endpoint).get("value", [])
            metadata["children"] = [
                self.get_item_metadata(drive, item_id=child["id"], fields=fields)
                for child in list_of_children
            ]

        # TODO: return other container types (bundles,lists, etc)

        return metadata

    def get_from_weburl(self, url: str) -> "SharepointItem":
        from sharedrive.clients.sharepoint import SharepointItem
        return SharepointItem.from_weburl(url, self)

    def resolve_weburl(self, url: str) -> dict[str, str]:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid SharePoint URL: {url}")

        self.host_url = parsed.hostname or self.host_url
        path_parts = [
            part for part in Path(unquote(parsed.path)).parts if part not in {"/", ""}
        ]

        site_name = None
        for index, part in enumerate(path_parts):
            if part.lower() == "sites" and index + 1 < len(path_parts):
                site_name = path_parts[index + 1]
                drive_name = (
                    path_parts[index + 2]
                    if index + 2 < len(path_parts)
                    else "Shared Documents"
                )
                item_path_parts = path_parts[index + 3 :]
                break
        else:
            raise ValueError(
                f"Could not extract site and library from SharePoint URL: {url}"
            )

        site_id = self.get_site_id(site_name)
        drive_id = self.get_drive_id(site_id, drive_name=drive_name)
        item_path = "/" + "/".join(item_path_parts) if item_path_parts else "/"
        return {
            "site_name": site_name,
            "site_id": site_id,
            "drive_name": drive_name,
            "drive_id": drive_id,
            "item_path": item_path,
        }

    def download_content(self, drive_id=None, item_id=None, download_url=None):
        """takes in the components needed to download content --

        drive id and item id -- uses Oauth to download
        download_url -- uses a presigned url (note: if on VPN, need to use this option - I think)

        """

        if download_url:
            url = download_url
            response = requests.get(url)
        else:
            if drive_id and item_id:
                url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/content"
                response = requests.get(url, headers=self.auth_header)
            else:
                raise GraphApiDriveError(
                    "Need drive_id and item_id if not using download_url"
                )

        if response.status_code != 200:
            raise GraphApiDriveError(
                f"Failed to download file. Status code: {response.status_code} - {response.reason}",
                status_code=response.status_code,
                response_text=response.text,
            )
        return response.content

    def get_file(self, site_name, file_path, metadata_only=False):
        """

        gets file item metadata and file

        """

        site_id = self.get_site_id(site_name)
        drive_id = self.get_drive_id(site_id)
        item_metadata = self.get_item_metadata(drive_id, item_path=file_path)

        if not item_metadata or "id" not in item_metadata:
            raise FileNotFoundError(
                f"File not found at path: {file_path} in site: {site_name}"
            )

        item = {"metadata": item_metadata}

        if metadata_only:
            return item
        else:
            item_content = SharepointItem(item_metadata, client=self).download(Path(file_path))

            item["content"] = item_content

            return item

    def get_folder(self, site_name: str, path: str):
        """
        Retrieve the contents of a folder, with optional recursion depth.

        Args:
            site_name (str): The name of the SharePoint site.
            path (str): The path to the folder.

        Returns:
            dict: A dictionary containing the folder's contents.
        """
        raise NotImplementedError(
            "get_folder has been deprecated in favor of `get_from_weburl` or `get_item_metadata` with options for recursion"
        )

    def upload_new_content(self, site_name, folder_path, local_file_path):
        """
        [IN DEVELOPMENT] Uploads a file to a specified SharePoint folder with proper Content-Type.
        """
        site_id = self.get_site_id(site_name)
        drive_id = self.get_drive_id(site_id)

        file_name = Path(local_file_path).name

        upload_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:{folder_path}/{file_name}:/content"

        # Determine the content type based on the file extension
        content_type, _ = mimetypes.guess_type(local_file_path)
        headers = self.auth_header.copy()
        if content_type:
            headers["Content-Type"] = content_type
        else:
            headers["Content-Type"] = (
                "application/octet-stream"  # Fallback binary stream
            )

        with open(local_file_path, "rb") as file_stream:
            response = requests.put(upload_url, headers=headers, data=file_stream)

        if response.status_code in (200, 201):
            print(
                f"File '{file_name}' uploaded successfully to '{folder_path}' with Content-Type '{headers['Content-Type']}'."
            )
            return response.json()
        else:
            print(f"Failed to upload file: {response.status_code}")
            print(response.text)
            response.raise_for_status()

    def update_content(
        self, site_name, folder_path, local_file_path, create_if_missing=False
    ):
        """
        [IN DEVELOPMENT] Updates an existing file in SharePoint, or creates it if not found (optional).
        """
        site_id = self.get_site_id(site_name)
        drive_id = self.get_drive_id(site_id)
        file_name = Path(local_file_path).name
        file_path = f"{folder_path}/{file_name}"

        content_type, _ = mimetypes.guess_type(local_file_path)
        headers = self.auth_header.copy()
        headers["Content-Type"] = content_type or "application/octet-stream"

        # Attempt to get file metadata
        try:
            file_metadata = self.get_item_metadata(drive_id, item_path=file_path)
            file_id = file_metadata.get("id")
        except GraphApiDriveError as e:
            if e.status_code == 404:
                file_id = None
            else:
                raise

        # Choose upload target based on existence
        if file_id:
            upload_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/content"
            action = "updated"
        elif create_if_missing:
            upload_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:{folder_path}/{file_name}:/content"
            action = "created"
        else:
            raise FileNotFoundError(
                f"File '{file_name}' not found and `create_if_missing` is False."
            )

        with open(local_file_path, "rb") as file_stream:
            response = requests.put(upload_url, headers=headers, data=file_stream)

        if response.status_code in (200, 201):
            print(f"File '{file_name}' {action} successfully in '{folder_path}'.")
            return response.json()
        else:
            print(f"Failed to {action} file: {response.status_code}")
            print(response.text)
            response.raise_for_status()


__all__ = ["SharepointClient", "SharepointItem", "SharepointFile", "SharepointFolder"]


class SharepointItem(ServiceItem):
    """A SharePoint file or folder item backed by the Graph API.

    Whether an instance represents a file or a directory is determined at
    runtime by :attr:`is_directory` (``"folder"`` key present in raw
    metadata), so a single class handles both cases.  The previous
    ``SharepointFile`` / ``SharepointFolder`` split has been consolidated
    here; backward-compatible aliases are kept at module level.
    """

    def __init__(
        self,
        client: "SharepointClient",
        raw_metadata: dict[str, Any] | None = None,
        basepath: str | None = None,
        path: str | None = None,
        id: str | None = None,
        name: str | None = None,
        source_url: str | None = None,
        parent_id: str | None = None,
        service_id: str | None = None,
        is_folder: bool = False,
        current_rel_path: str = "",
        scope_root: bool = False,
    ):
        self.client = client
        self.raw = raw_metadata or {}
        self._basepath = basepath
        self._path = path
        self._id = id
        self._name = name
        self._source_url = source_url
        self._parent_id = parent_id
        self._service_id = service_id
        self._is_folder = is_folder
        
        self._current_rel_path = current_rel_path
        self._scope_root = scope_root
        
    _resolved_path: str | None = None
    _resolved_path_depth: int | None = None
    _resolved_path_root_id: str | None = None

    @classmethod
    def from_weburl(cls, url: str, client: "SharepointClient") -> "SharepointItem":
        resolved = client.resolve_weburl(url)
        metadata = client.get_item_metadata(
            resolved["drive_id"], item_path=resolved["item_path"]
        )
        return cls.from_api_response(api_metadata=metadata, client=client, scope_root=True)

    @classmethod
    def from_api_response(
        cls,
        api_metadata: dict[str, Any],
        client: "SharepointClient",
        current_rel_path: str = "",
        scope_root: bool = False,
    ) -> "SharepointItem":
        is_folder = "folder" in api_metadata
        parent_id = api_metadata.get("parentReference", {}).get("id")
        
        relative_path = str(api_metadata.get("relative_path", "")).strip()
        path = relative_path if relative_path else api_metadata.get("name", "")
        if current_rel_path:
             path = f"{current_rel_path}/{path}".strip("/")

        return cls(
            client=client,
            raw_metadata=api_metadata,
            id=api_metadata.get("id"),
            name=api_metadata.get("name"),
            path=path,
            source_url=api_metadata.get("webUrl"),
            parent_id=parent_id,
            service_id=api_metadata.get("id"),
            is_folder=is_folder,
            current_rel_path=current_rel_path,
            scope_root=scope_root,
        )

    @property
    def parent(self) -> SharepointItem | None:
        if self._parent_id:
            drive_id = self.raw.get("parentReference", {}).get("driveId")
            if drive_id:
                parent_metadata = self.client.get_item_metadata(drive_id, item_id=self._parent_id)
                return SharepointItem.from_api_response(api_metadata=parent_metadata, client=self.client)
        return None

    @property
    def resolved_path(self) -> str | None:
        return self._resolved_path

    @property
    def resolved_path_depth(self) -> int | None:
        return self._resolved_path_depth

    def resolve_path(self, depth: int | None = None) -> str:
        current_node: SharepointItem = self
        path_parts = [self.name]
        current_depth = 0
        
        while current_node._parent_id:
            if depth is not None and current_depth >= depth:
                break
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

    @property
    def id(self) -> str:
        return self._id or ""

    @property
    def name(self) -> str:
        return self._name or ""

    @property
    def path(self) -> str:
        return self._path or ""
        
    @path.setter
    def path(self, new_path: str) -> None:
        self._path = new_path

    @property
    def service_type(self) -> str:
        return "SharePoint"

    @property
    def source_url(self) -> str:
        return self._source_url or ""

    @property
    def is_directory(self) -> bool:
        return self._is_folder

    @property
    def children(self) -> list["SharepointItem"]:
        """Direct children of this directory; empty list for files."""
        if not self.is_directory:
            return []
        contents = self.raw.get("children")
        if contents is None:
            drive_id = self.raw.get("parentReference", {}).get("driveId")
            if not drive_id:
                raise ValueError("Missing driveId in SharePoint folder metadata")
            refreshed = self.client.get_item_metadata(drive_id, item_id=self.id)
            contents = refreshed.get("children", [])
            self.raw.update(refreshed)

        next_rel_path = "" if self._scope_root else self.path
        return [
            SharepointItem.from_api_response(
                child_raw, client=self.client, current_rel_path=next_rel_path, scope_root=False
            )
            for child_raw in contents
        ]

    def refresh(self, *, include_children: bool = True) -> "SharepointItem":
        """Re-fetch raw metadata (and optionally children) from the Graph API."""
        drive_id = self.raw.get("parentReference", {}).get("driveId")
        if not drive_id:
            raise ValueError(
                f"Missing driveId in SharePoint "
                f"{'folder' if self.is_directory else 'item'} metadata"
            )
        refreshed = self.client.get_item_metadata(drive_id, item_id=self.id)
        if self.is_directory and not include_children and "children" in self.raw:
            refreshed["children"] = self.raw["children"]
        self.raw = refreshed
        self._name = refreshed.get("name")
        self._id = refreshed.get("id")
        self._source_url = refreshed.get("webUrl")
        self._is_folder = "folder" in refreshed
        self._parent_id = refreshed.get("parentReference", {}).get("id")
        return self

    def export(self, target_mime_type: str | None = None, output_path: str | None = None) -> bytes | str:
        """Export this item if possible, otherwise download it."""
        # Microsoft Graph API allows exporting via PDF. 
        # Example format: pdf
        # https://learn.microsoft.com/en-us/graph/api/driveitem-get-content-format?view=graph-rest-1.0&tabs=http
        if target_mime_type == "application/pdf":
            # Just add format=pdf to the download url basically.
            # But the most robust way via graph is to hit /content?format=pdf
            pass # fallthrough below for now to regular download if not supported
            
            if self.is_directory:
                 raise NotImplementedError("Cannot export a directory")
            
            drive_id = self.raw.get("parentReference", {}).get("driveId")
            if drive_id:
                url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{self.id}/content?format=pdf"
                
                target = Path(output_path) if output_path else None
                if target and target.is_dir():
                    target = target / (str(Path(self.name).with_suffix(".pdf")))
                elif target:
                    target.parent.mkdir(parents=True, exist_ok=True)
                
                response = requests.get(url, headers=self.client.auth_header, stream=True)
                if response.status_code == 302:
                    redirect_url = response.headers.get("Location")
                    if redirect_url:
                        response = requests.get(redirect_url, stream=True)
                response.raise_for_status()
                
                if target:
                    with open(target, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    return ""
                return response.content

        return self.download(target_dir=output_path) if output_path else b""

    def download(self, target_dir: str | Path) -> None:
        """Download this item.

        Directories are walked recursively via :meth:`iter_files` and each
        leaf file is written relative to *target_dir*.  Files are fetched via
        their Graph API download URL or a presigned URL.
        """
        if self.is_directory:
            super().download(target_dir)
            return
        target = Path(target_dir)
        if target.is_dir():
            target = target / self.name

        target.parent.mkdir(parents=True, exist_ok=True)
        drive_id = self.raw.get("parentReference", {}).get("driveId")
        if not drive_id:
            raise ValueError("Missing driveId in Sharepoint item metadata")

        url = self.raw.get(
            "@microsoft.graph.downloadUrl",
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{self.id}/content",
        )

        response = requests.get(url, headers=self.client.auth_header, stream=True)
        if response.status_code == 302:
            redirect_url = response.headers.get("Location")
            if redirect_url:
                response = requests.get(redirect_url, stream=True)
        response.raise_for_status()

        with open(target, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)


# ---------------------------------------------------------------------------
# Backward-compatible aliases
# ---------------------------------------------------------------------------
# Old code that imports or subclasses ``SharepointFile`` / ``SharepointFolder``
# will continue to work because these names now point to ``SharepointItem``.
SharepointFile = SharepointItem
SharepointFolder = SharepointItem
