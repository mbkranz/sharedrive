from __future__ import annotations

from pathlib import Path
import json
import mimetypes
from typing import TYPE_CHECKING


import requests

from sharedrive.exceptions import GraphApiDriveError, GraphApiSiteError

if TYPE_CHECKING:
    from sharedrive.auth.microsoft import MicrosoftTokenStrategy


class SharepointClient:

    """ 
    TODO: look into for local dev: https://learn.microsoft.com/en-us/powershell/microsoftgraph/overview?view=graph-powershell-1.0
    
    
    """

    def __init__(
        self,
        tenant_id=None,
        client_id=None,
        client_secret=None,
        host_url="norc.sharepoint.com",
        scope=None,
        user_delegated_access=False,
        *,
        token_strategy: MicrosoftTokenStrategy | None = None,
        access_token: str | None = None,
    ):

        self.host_url = host_url or "norc.sharepoint.com"
        self.tenant_id = tenant_id
        self.scope = scope or ["https://graph.microsoft.com/.default"]
        self.client_id = client_id
        self.client_secret = client_secret

        if access_token is not None and token_strategy is not None:
            raise ValueError("Provide either access_token or token_strategy, not both.")

        if access_token is None:
            if token_strategy is not None:
                access_token = token_strategy.build()
            else:
                from sharedrive.auth.microsoft import AppOnlyStrategy, DelegatedStrategy

                if not tenant_id or not client_id:
                    raise ValueError(
                        "SharepointClient requires either token_strategy/access_token or tenant_id/client_id."
                    )

                strategy = DelegatedStrategy(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    scopes=self.scope,
                ) if user_delegated_access else AppOnlyStrategy(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    client_secret=client_secret,
                    scopes=self.scope,
                )
                access_token = strategy.build()

        self.access_token = access_token

        self.auth_header = {
            'Authorization': f'Bearer {self.access_token}'
        }



    def get_site_id(self,site_name):
        endpoint = f"https://graph.microsoft.com/v1.0/sites/{self.host_url}:/sites/{site_name}"
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
            raise GraphApiDriveError(f"Request error when calling {endpoint}: {req_err}") from req_err

        if "id" not in site_data:
            raise GraphApiDriveError(
                f"Site found but no 'id' returned.\n"
                f"Site Name: {site_name}\n"
                f"Response JSON: {json.dumps(site_data, indent=2)}"
            )

        return site_data["id"]

    def get_drive_id(self, site_id):
        """
        Retrieves the default document drive associated with a SharePoint site.
        """
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
            raise GraphApiDriveError(f"Request error calling {endpoint}: {req_err}") from req_err

        if "id" not in drive_data:
            raise GraphApiDriveError(
                f"Drive request succeeded but no 'id' field was returned.\n"
                f"Site ID: {site_id}\n"
                f"Response JSON:\n{json.dumps(drive_data, indent=2)}"
            )

        return drive_data["id"]

    def get_item_metadata(self,drive_id,itempath):

        """
        get item metadata based on relative file path within the drive

        """
        endpoint = f'https://graph.microsoft.com/v1.0/drives/{drive_id}/root:{itempath}'

        item_metadata = requests.get(endpoint,headers=self.auth_header).json()

        return item_metadata


    def download_content(self,drive_id=None,item_id=None,download_url=None):
        """ takes in the components needed to download content --

        drive id and item id -- uses Oauth to download
        download_url -- uses a presigned url (note: if on VPN, need to use this option - I think)

        """

        if download_url:
            url = download_url
            response = requests.get(url)
        else:
            if drive_id and item_id:
                url = f'https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/content'
                response = requests.get(url,headers=self.auth_header)
            else:
                raise Exception("Need drive_id and item_id if not using download_url")
        
        # Save the file
        if response.status_code == 200:
            print("File downloaded successfully.")
            return response.content
            
        else:
            print(f"Failed to download file. Status code: {response.status_code}")
            print(response.status_code)
            print(response.reason)
            return None

    def get_from_weburl(self, url):
        """
        Generic method to get a file or folder from a SharePoint URL.
        NOTE: this will work with both copying straight from browser address bar or from "copy link" option in SharePoint UI.
        
        Parses the SharePoint URL to extract:
        - site_name: The name of the SharePoint site
        - item_path: The path to the file or folder
        
        Args:
            url (str): The SharePoint URL (e.g., https://norc.sharepoint.com/sites/MySite/Shared Documents/folder/file.xlsx)
            metadata_only (bool): If True, only return metadata for files. Defaults to False.
            depth (int): For folders, the recursion depth. Defaults to 0 (immediate contents only).
        
        Returns:
            dict: Item metadata and content (for files) or folder contents (for folders)
        
        Raises:
            ValueError: If the URL cannot be parsed or is invalid
        """
        def _extract_endpoint(url):

            from urllib.parse import urlparse
            
            # Parse the URL and its query string
            parsed = urlparse(url)
            
            if parsed.hostname:
                self.host_url = parsed.hostname
            
            path = Path(parsed.path)

            for i, part in enumerate(path.parts):
                site_id = None
                drive_id = None
                if part.lower() == "sites":
                    site_name = path.parts[i + 1]
                    drive_name = path.parts[i + 2]
                    drive_path = "/".join(path.parts[i + 3:])
                    break

            site_id = self.get_site_id(site_name)
            drive_ids = requests.get(f'https://graph.microsoft.com/v1.0/sites/{site_id}/drives',headers=self.auth_header).json()
            for d in drive_ids.get('value',[]):
                if drive_name in d.get('webUrl'):
                    drive_id = d["id"]
                    break
            return drive_id, drive_path

        drive_id, itempath = _extract_endpoint(url)
        endpoint = f'https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{itempath}'
        item_metadata = requests.get(endpoint,headers=self.auth_header).json()

        return item_metadata

    def download_from_weburl(self, url,output_path,dry_run=True):
        if dry_run:
            print(f"Dry run: sharepoint download {url} -> {output_path}")
            return

        metadata = self.get_from_weburl(url)
        if "folder" in metadata and "file" not in metadata:
            raise ValueError(f"SharePoint source is a folder, not a file: {url}")
        
        if dry_run:
            print(f"Dry run: sharepoint download {url} -> {output_path}")
            print(f"Metadata: {json.dumps(metadata, indent=2)}")

        download_url = metadata.get("@microsoft.graph.downloadUrl")
        if download_url:
            content = self.download_content(download_url=download_url)
        else:
            # TODO: make pydantic classes for metadata and validate expected fields and types, and handle missing fields more gracefully
            # TODO: 
            # class ItemNotFoundResponse(BaseModel):
            #     error: {subclass with error details}
            
            drive_id = metadata.get("parentReference", {}).get("driveId")
            item_id = metadata.get("id")
            content = self.download_content(drive_id=drive_id, item_id=item_id)

        if content is None:
            raise RuntimeError(f"Failed to download content: {url}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(content)

    def get_file(self,site_name,file_path,metadata_only=False):
        """ 
        
        gets file item metadata and file 
        
        """ 
        
        site_id = self.get_site_id(site_name)
        drive_id = self.get_drive_id(site_id)
        item_metadata = self.get_item_metadata(drive_id,file_path)
        
        if not item_metadata or 'id' not in item_metadata:
            raise FileNotFoundError(f"File not found at path: {file_path} in site: {site_name}")
            
        item_id = item_metadata["id"]
        
        item = {"metadata":item_metadata}

        if metadata_only:
            return item
        else:

            if item_metadata.get('@microsoft.graph.downloadUrl'):
                item_content = self.download_content(download_url=item_metadata['@microsoft.graph.downloadUrl'])
            else:
                print("No Presigned URL detected...using drive id and item id")
                item_content = self.download_content(drive_id,item_id)

            item["content"] = item_content

            return item

    def get_folder(self, site_name: str, folder_path: str, depth: int = 0):
        """
        Retrieve the contents of a folder, with optional recursion depth.

        Args:
            site_name (str): The name of the SharePoint site.
            folder_path (str): The path to the folder.
            depth (int, optional): The depth for recursive fetching.
                                   - 0: Immediate contents only.
                                   - -1: Full recursion.
                                   - n > 0: Recurse n levels deep.
                                   Defaults to 0.

        Returns:
            dict: A dictionary containing the folder's contents.
        """
        site_id = self.get_site_id(site_name)
        drive_id = self.get_drive_id(site_id)
        
        # For SharePoint, the item-id of the folder is needed for recursive calls.
        # We can get this from the path.
        item_metadata = self.get_item_metadata(drive_id, folder_path)
        if not item_metadata or 'id' not in item_metadata:
            raise FileNotFoundError(f"Folder not found at path: {folder_path}")
        
        folder_id = item_metadata['id']

        return self._get_folder_contents_recursive(drive_id, folder_id, depth)

    def _get_folder_contents_recursive(self, drive_id: str, folder_id: str, depth: int):
        """Helper function to recursively get folder contents."""
        endpoint = f'https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{folder_id}/children'
        
        try:
            response = requests.get(endpoint, headers=self.auth_header)
            response.raise_for_status()
            result = response.json()
        except requests.exceptions.HTTPError as e:
            raise GraphApiDriveError(f"HTTP error while fetching folder contents for folder ID '{folder_id}'", e.response.status_code, e.response.text) from e

        if depth == 0:
            return result

        items = result.get('value', [])
        for item in items:
            if 'folder' in item:
                new_depth = depth - 1 if depth > 0 else -1
                item['children'] = self._get_folder_contents_recursive(drive_id, item['id'], new_depth)

        return result

    def get_folder_contents(self, site_name, path,recursive=False,metadata_only=True):
        """
        Lists all files in a given directory recursively with paths relative to the input directory.

        :param site_name: The name of the SharePoint site.
        :param path: The path of the folder within the SharePoint drive.
        :param relative_path: The relative path used to build paths relative to the input directory.
        :return: A list of all files with their paths relative to the input directory.

        # TODO: put in logging info and exceptions
        # TODO: make API calls more efficient either by batching or using expand=children parameter (although this has limitations on depth )
        ## see https://learn.microsoft.com/en-us/graph/query-parameters
        """

        response = self.get_folder(site_name,path)
        items = response.get('value', [])

        all_files = []

        for item in items:

            folder_has_children = item.get("folder",{}.get("childCount"))

            if folder_has_children and recursive:
                # Recursively list contents of the folder
                subpath = f"{path}/{item['name']}"
                content = self.get_folder_contents(site_name, subpath,recursive=recursive,metadata_only=metadata_only)

            elif 'file' in item:
                subpath = f"{path}/{item['name']}"
                content = [self.get_file(site_name,subpath,metadata_only=metadata_only)]
            else:
                content = [item]
            
            all_files.extend(content)
            
        return all_files

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
            headers['Content-Type'] = content_type
        else:
            headers['Content-Type'] = 'application/octet-stream'  # Fallback binary stream

        with open(local_file_path, 'rb') as file_stream:
            response = requests.put(upload_url, headers=headers, data=file_stream)

        if response.status_code in (200, 201):
            print(f"File '{file_name}' uploaded successfully to '{folder_path}' with Content-Type '{headers['Content-Type']}'.")
            return response.json()
        else:
            print(f"Failed to upload file: {response.status_code}")
            print(response.text)
            response.raise_for_status()

    def update_content(self, site_name, folder_path, local_file_path, create_if_missing=False):
        """
        [IN DEVELOPMENT] Updates an existing file in SharePoint, or creates it if not found (optional).
        """
        site_id = self.get_site_id(site_name)
        drive_id = self.get_drive_id(site_id)
        file_name = Path(local_file_path).name
        file_path = f"{folder_path}/{file_name}"

        content_type, _ = mimetypes.guess_type(local_file_path)
        headers = self.auth_header.copy()
        headers['Content-Type'] = content_type or 'application/octet-stream'

        # Attempt to get file metadata
        try:
            file_metadata = self.get_item_metadata(drive_id, file_path)
            file_id = file_metadata.get('id')
        except requests.HTTPError as e:
            if e.response.status_code == 404:
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
            raise FileNotFoundError(f"File '{file_name}' not found and `create_if_missing` is False.")

        with open(local_file_path, 'rb') as file_stream:
            response = requests.put(upload_url, headers=headers, data=file_stream)

        if response.status_code in (200, 201):
            print(f"File '{file_name}' {action} successfully in '{folder_path}'.")
            return response.json()
        else:
            print(f"Failed to {action} file: {response.status_code}")
            print(response.text)
            response.raise_for_status()


__all__ = ["SharepointClient"]