# Python API

Auto-generated from source signatures and docstrings.

## `sharedrive.retrieve`

### Functions

- `def resolve_default_descriptor() -> Path`
  - Return the first existing default descriptor path.
- `def retrieve_from_descriptor(descriptor: Path | str, include: str | Iterable[str] = 'all', output_dir: Path | str = Path('resources'), dry_run: bool = False, *, log: LogFn | None = print, sharepoint_client_factory: Callable[[], Any] | None = None, googledrive_client_factory: Callable[[], Any] | None = None, use_cloudpathlib: bool = True) -> RetrieveSummary`
  - Retrieve resources from a descriptor using adapter-specific clients.
- `def retrieve_resources(descriptor: Path | str, include: str | Iterable[str] = 'all', output_dir: Path | str = Path('resources'), dry_run: bool = False, *, log: LogFn | None = print) -> RetrieveSummary`
  - Convenience alias for retrieve_from_descriptor.

### Classes

#### `RetrieveSummary`
- Fields:
  - `total_resources: int`
  - `downloaded: int`
  - `skipped: int`
  - `dry_run_actions: int`
  - `failures: int`
- Methods:
  - `def ok(self) -> bool`


## `sharedrive.azure`

### Classes

#### `SpoConfig`
- Fields:
  - `tenant_id: str`
  - `client_id: str`
  - `client_secret: SecretStr | None`
  - `scope: list[str]`
  - `user_delegated_access: bool`
  - `host_url: str`
- Methods:
  - `def to_client(self) -> SharepointClient`


## `sharedrive.aws`

### Functions

- `def parse_s3_source_url(source_url: str) -> tuple[str, str]`
- `def download_s3_url(source_url: str, output_path: Path, *, dry_run: bool = False, use_cloudpathlib: bool = True) -> Path | None`


## `sharedrive.googledrive`

### Classes

#### `GoogleDriveClient`
- Minimal Google Drive client (ID-first) with read/write and full export coverage for Google-native files.
- Methods:
  - `def list_files(self)`
    - List all files the authenticated user has access to.
  - `def get_file(self, file_id: str, **kwargs) -> Dict[str, Any]`
  - `def download_file(self, file_id: str, output_path: Optional[str] = None, mime_type: Optional[str] = None, acknowledge_abuse: bool = False, byte_range: Optional[str] = None, supports_all_drives: bool = True, **kwargs) -> Union[bytes, str]`
    - Download file content (handles both regular files and Google Workspace documents automatically).
  - `def download_from_weburl(self, web_url: str, **kwargs) -> Union[bytes, str]`
    - Extract ID from a Drive URL and download.
  - `def export_file(self, file_id: str, mime_type: Optional[str] = None, output_path: Optional[str] = None, supports_all_drives: bool = True, **kwargs) -> Union[bytes, str]`
    - Export Google Workspace document content to a specific format.
  - `def export_from_weburl(self, web_url: str, mime_type: Optional[str] = None, **kwargs) -> Union[bytes, str]`
    - Extract ID from a Drive URL and export to a specific MIME type.
  - `def update_file(self, file_id: str, file_in_bytes_or_path: Optional[Union[str, bytes]] = None, mime_type: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]`
    - Update file content and/or metadata.
  - `def update_from_weburl(self, web_url: str, **kwargs) -> Dict[str, Any]`
    - Extract ID from a Drive URL and update file content and/or metadata.
  - `def create_file(self, parent_folder_id: str, file_in_bytes: Optional[bytes] = None, mime_type: Optional[str] = None, name: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None, supports_all_drives: bool = True, **kwargs) -> Dict[str, Any]`
    - Create a new file via multipart upload (for files ≤5MB).
  - `def create_folder(self, parent_folder_id: str, name: str) -> Dict[str, Any]`
    - Create a folder under a parent folder ID.


## `sharedrive.auth.google`

### Functions

- `def normalize_google_scopes(scopes: Sequence[str] | str | None, *, default: Sequence[str] = DEFAULT_DRIVE_SCOPES) -> list[str]`
- `def default_drive_strategy(credentials_path: str | Path | None = None, scopes: Sequence[str] | str | None = None) -> CredentialStrategy`

### Classes

#### `AdcStrategy`
- Fields:
  - `scopes: Sequence[str] | str | None`
- Methods:
  - `def build(self) -> Credentials`

#### `ServiceAccountStrategy`
- Fields:
  - `credentials_path: str | Path`
  - `scopes: Sequence[str] | str | None`
- Methods:
  - `def build(self) -> Credentials`

#### `UserOAuthStrategy`
- Fields:
  - `client_secrets_path: str | Path`
  - `scopes: Sequence[str] | str | None`
  - `token_store: TokenStore | None`
  - `use_local_server: bool`
- Methods:
  - `def build(self) -> Credentials`

#### `ChainedStrategy`
- Fields:
  - `strategies: Sequence[CredentialStrategy]`
- Methods:
  - `def build(self) -> Credentials`


## `sharedrive.auth.token_store`

### Classes

#### `JsonTokenStore`
- Persist authorized-user OAuth credentials as JSON on disk.
- Methods:
  - `def load(self) -> Credentials | None`
  - `def save(self, creds: Credentials) -> None`


## `sharedrive.google_base`

### Classes

#### `GoogleBaseClient`
- Shared Google client base for auth lifecycle and HTTP transport helpers.
- Methods:
  - `def _ensure_valid_credentials(self) -> None`
  - `def _request(self, method: str, url: str, **kwargs) -> requests.Response`


## `sharedrive.sharepoint`

### Classes

#### `SharepointClient`
- TODO: look into for local dev: https://learn.microsoft.com/en-us/powershell/microsoftgraph/overview?view=graph-powershell-1.0
- Methods:
  - `def get_from_weburl(self, url)`
    - Generic method to get a file or folder from a SharePoint URL.
  - `def download_from_weburl(self, url, output_path, dry_run = True)`
  - `def get_file(self, site_name, file_path, metadata_only = False)`
    - gets file item metadata and file
  - `def get_folder(self, site_name: str, folder_path: str, depth: int = 0)`
    - Retrieve the contents of a folder, with optional recursion depth.
  - `def get_folder_contents(self, site_name, path, recursive = False, metadata_only = True)`
    - Lists all files in a given directory recursively with paths relative to the input directory.
  - `def upload_new_content(self, site_name, folder_path, local_file_path)`
    - [IN DEVELOPMENT] Uploads a file to a specified SharePoint folder with proper Content-Type.
  - `def update_content(self, site_name, folder_path, local_file_path, create_if_missing = False)`
    - [IN DEVELOPMENT] Updates an existing file in SharePoint, or creates it if not found (optional).
