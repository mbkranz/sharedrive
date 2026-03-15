# Python API

Auto-generated from source signatures and docstrings.

## `sharedrive.descriptor`

### Functions

- `def get_descriptor_resources(document: dict[str, Any], *, create: bool = False) -> list[dict[str, Any]]`
  - Return the top-level resources list, optionally initializing it.
- `def load_descriptor(path: Path | str) -> list[dict[str, Any]]`
  - Load a JSON/YAML descriptor and return the top-level resources list.
- `def load_descriptor_document(path: Path | str) -> dict[str, Any]`
  - Load a JSON/YAML descriptor and return the full top-level document.
- `def resolve_default_descriptor() -> Path`
  - Return the first existing default descriptor path.
- `def save_descriptor_document(path: Path | str, document: dict[str, Any]) -> None`
  - Persist a descriptor document as JSON or YAML based on file suffix.


## `sharedrive.actions.add`

### Constants

- `SUPPORTED_DRIVE_SERVICES = {'sharepoint', 'googledrive', 's3'}`

### Functions

- `def add_resource_to_descriptor(descriptor: Path | str, *, name: str, path: str, source: str, title: str | None = None, description: str | None = None, drive_service: str | None = None) -> dict[str, Any]`
  - Append a resource entry to a descriptor and return the created resource.
- `def infer_drive_service(source: str) -> str`
  - Infer the implemented drive service from a source URL/URI.
- `def normalize_drive_service(source: str, drive_service: str | None = None) -> str`
  - Return a supported drive service, inferring it from source if omitted.


## `sharedrive.actions.fetch`

### Functions

- `def check_auth_for_adapters(adapters: Iterable[str], *, sharepoint_client_factory: Callable[[], Any] | None = None, googledrive_client_factory: Callable[[], Any] | None = None, s3_auth_checker: Callable[[], None] | None = None) -> list[AuthCheckResult]`
- `def check_auth_for_descriptor(descriptor: Path | str, include: str | Iterable[str] = 'all', *, sharepoint_client_factory: Callable[[], Any] | None = None, googledrive_client_factory: Callable[[], Any] | None = None, s3_auth_checker: Callable[[], None] | None = None) -> list[AuthCheckResult]`
- `def fetch_from_descriptor(descriptor: Path | str, include: str | Iterable[str] = 'all', output_dir: Path | str = Path('resources'), dry_run: bool = False, *, check_auth: bool = False, log: LogFn | None = print, sharepoint_client_factory: Callable[[], Any] | None = None, googledrive_client_factory: Callable[[], Any] | None = None, use_cloudpathlib: bool = True) -> FetchSummary`
  - Fetch resources from a descriptor using adapter-specific clients.
- `def fetch_resources(descriptor: Path | str, include: str | Iterable[str] = 'all', output_dir: Path | str = Path('resources'), dry_run: bool = False, *, check_auth: bool = False, log: LogFn | None = print) -> FetchSummary`
  - Convenience alias for fetch_from_descriptor.
- `def resource_adapter_name(resource: dict[str, Any], source_url: str | None) -> str`
  - Resolve adapter from driveService/x-adapter override or infer from URL.
- `def resource_output_path(resource: dict[str, Any], output_dir: Path) -> Path`
  - Resolve resource.path against output_dir unless path is absolute.
- `def resource_output_paths(resource: dict[str, Any], output_dir: Path) -> list[Path]`
  - Resolve primary resource.path plus optional targets[] into local output paths.
- `def resource_source_url(resource: dict[str, Any]) -> str | None`
  - Resolve source URL using sources[].path first, then legacy source.
- `def retrieve_from_descriptor(descriptor: Path | str, include: str | Iterable[str] = 'all', output_dir: Path | str = Path('resources'), dry_run: bool = False, *, check_auth: bool = False, log: LogFn | None = print, sharepoint_client_factory: Callable[[], Any] | None = None, googledrive_client_factory: Callable[[], Any] | None = None, use_cloudpathlib: bool = True) -> RetrieveSummary`
  - Backward-compatible alias for fetch_from_descriptor.
- `def retrieve_resources(descriptor: Path | str, include: str | Iterable[str] = 'all', output_dir: Path | str = Path('resources'), dry_run: bool = False, *, check_auth: bool = False, log: LogFn | None = print) -> RetrieveSummary`
  - Backward-compatible alias for fetch_resources.

### Classes

#### `AuthCheckResult`
- Fields:
  - `adapter: str`
  - `ok: bool`
  - `message: str`
- Methods:
  - `def to_dict(self) -> dict[str, str | bool]`

#### `FetchSummary`
- Fields:
  - `total_resources: int`
  - `downloaded: int`
  - `skipped: int`
  - `dry_run_actions: int`
  - `failures: int`
- Methods:
  - `def ok(self) -> bool`

#### `RetrieveSummary`
- Fields:
  - `total_resources: int`
  - `downloaded: int`
  - `skipped: int`
  - `dry_run_actions: int`
  - `failures: int`
- Methods:
  - `def ok(self) -> bool`


## `sharedrive.aws`

### Functions

- `def download_s3_url(source_url: str, output_path: Path, *, dry_run: bool = False, use_cloudpathlib: bool = True) -> Path | None`
- `def parse_s3_source_url(source_url: str) -> tuple[str, str]`


## `sharedrive.clients.googledrive`

### Classes

#### `GoogleBaseClient`
- Shared Google client base for auth lifecycle and HTTP transport helpers.

#### `GoogleDriveClient`
- Minimal Google Drive client (ID-first) with read/write and full export coverage for Google-native files.
- Methods:
  - `def list_files(self)`
    - List all files the authenticated user has access to.
  - `def get_file(self, file_id: str, **kwargs) -> Dict[str, Any]`
  - `def infer_export_mime_type(self, file_id: str) -> Optional[str]`
  - `def download_file(self, file_id: str, output_path: Optional[str] = None, mime_type: Optional[str] = None, acknowledge_abuse: bool = False, byte_range: Optional[str] = None, supports_all_drives: bool = True, **kwargs) -> Union[bytes, str]`
  - `def export_file(self, file_id: str, mime_type: Optional[str] = None, output_path: Optional[str] = None, supports_all_drives: bool = True, **kwargs) -> Union[bytes, str]`
  - `def create_file(self, parent_folder_id: str, file_in_bytes: Optional[bytes] = None, mime_type: Optional[str] = None, name: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None, supports_all_drives: bool = True, **kwargs) -> Dict[str, Any]`
  - `def update_file(self, file_id: str, file_in_bytes_or_path: Optional[Union[str, bytes]] = None, mime_type: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]`
  - `def create_folder(self, parent_folder_id: str, name: str) -> Dict[str, Any]`
  - `def get_from_weburl(self, web_url: str, fields: str = '*') -> Dict[str, Any]`
  - `def download_from_weburl(self, web_url: str, **kwargs) -> Union[bytes, str]`
  - `def export_from_weburl(self, web_url: str, mime_type: Optional[str] = None, **kwargs) -> Union[bytes, str]`
  - `def update_from_weburl(self, web_url: str, **kwargs) -> Dict[str, Any]`


## `sharedrive.auth.google`

### Constants

- `DEFAULT_DRIVE_READONLY_SCOPES = ('https://www.googleapis.com/auth/drive.readonly',)`
- `DEFAULT_DRIVE_SCOPES = ('https://www.googleapis.com/auth/drive',)`

### Functions

- `def default_drive_strategy(credentials_path: str | Path | None = None, scopes: Sequence[str] | str | None = None) -> CredentialStrategy`
- `def normalize_google_scopes(scopes: Sequence[str] | str | None, *, default: Sequence[str] = DEFAULT_DRIVE_SCOPES) -> list[str]`

### Classes

#### `AdcStrategy`
- Fields:
  - `scopes: Sequence[str] | str | None`
- Methods:
  - `def build(self) -> Credentials`

#### `ChainedStrategy`
- Fields:
  - `strategies: Sequence[CredentialStrategy]`
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


## `sharedrive.auth.microsoft`

### Constants

- `DEFAULT_MICROSOFT_GRAPH_SCOPES = ('https://graph.microsoft.com/.default',)`

### Functions

- `def normalize_microsoft_scopes(scopes: Sequence[str] | str | None, *, default: Sequence[str] = DEFAULT_MICROSOFT_GRAPH_SCOPES) -> list[str]`

### Classes

#### `AppOnlyStrategy`
- Fields:
  - `client_secret: str | None`
- Methods:
  - `def build(self) -> str`

#### `DelegatedStrategy`
- Methods:
  - `def build(self) -> str`

#### `MicrosoftTokenStrategy`
- Fields:
  - `tenant_id: str`
  - `client_id: str`
  - `scopes: Sequence[str] | str | None`
- Methods:
  - `def normalized_scopes(self) -> list[str]`


## `sharedrive.auth.token_store`

### Classes

#### `JsonTokenStore`
- Persist authorized-user OAuth credentials as JSON on disk.
- Methods:
  - `def load(self) -> Credentials | None`
  - `def save(self, creds: Credentials) -> None`


## `sharedrive.auth.settings`

### Functions

- `def make_google_drive_client_from_settings(config: GoogleAuthConfig | None = None)`
- `def make_sharepoint_client_from_microsoft_auth(config: MicrosoftAuthConfig | None = None)`
- `def make_sharepoint_client_from_settings(config: MicrosoftAuthConfig | None = None)`

### Classes

#### `GoogleAuthConfig`
- Fields:
  - `auth_mode: GoogleAuthMode`
  - `service_account_credentials: Path | None`
  - `oauth_client_secrets: Path | None`
  - `oauth_token_path: Path | None`
  - `scopes: list[str]`
  - `use_local_server: bool`
- Methods:
  - `def to_scope_list(cls, value: str | list[str] | tuple[str, ...] | None) -> list[str]`
  - `def validate_for_mode(self) -> GoogleAuthConfig`
  - `def to_strategy(self) -> CredentialStrategy`

#### `GoogleAuthMode`

#### `MicrosoftAuthConfig`
- Fields:
  - `auth_mode: MicrosoftAuthMode`
  - `tenant_id: str | None`
  - `client_id: str | None`
  - `client_secret: SecretStr | None`
  - `host_url: str`
  - `scopes: list[str]`
- Methods:
  - `def empty_string_to_none(cls, value: str | None) -> str | None`
  - `def normalize_host_url(cls, value: str | None) -> str`
  - `def to_scope_list(cls, value: str | list[str] | tuple[str, ...] | None) -> list[str]`
  - `def validate_for_mode(self) -> MicrosoftAuthConfig`
  - `def to_strategy(self) -> AppOnlyStrategy | DelegatedStrategy`

#### `MicrosoftAuthMode`

#### `SharepointAuthConfig`
- Fields:
  - `auth_mode: MicrosoftAuthMode`
  - `tenant_id: str | None`
  - `client_id: str | None`
  - `client_secret: SecretStr | None`
  - `host_url: str`
  - `scopes: list[str]`
- Methods:
  - `def empty_string_to_none(cls, value: str | None) -> str | None`
  - `def normalize_host_url(cls, value: str | None) -> str`
  - `def to_scope_list(cls, value: str | list[str] | tuple[str, ...] | None) -> list[str]`
  - `def validate_for_mode(self) -> MicrosoftAuthConfig`
  - `def to_strategy(self) -> AppOnlyStrategy | DelegatedStrategy`

#### `SharepointAuthMode`


## `sharedrive.azure`

### Classes

#### `SpoConfig`
- Methods:
  - `def scope(self) -> list[str]`
  - `def user_delegated_access(self) -> bool`
  - `def to_client(self)`


## `sharedrive.clients.sharepoint`

### Classes

#### `SharepointClient`
- TODO: look into for local dev: https://learn.microsoft.com/en-us/powershell/microsoftgraph/overview?view=graph-powershell-1.0
- Methods:
  - `def get_site_id(self, site_name)`
  - `def get_drive_id(self, site_id)`
    - Retrieves the default document drive associated with a SharePoint site.
  - `def get_item_metadata(self, drive_id, itempath)`
    - get item metadata based on relative file path within the drive
  - `def download_content(self, drive_id = None, item_id = None, download_url = None)`
    - takes in the components needed to download content --
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
