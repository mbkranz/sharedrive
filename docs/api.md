# Python API

Auto-generated from source signatures and docstrings.

## `sharedrive.helpers`

### Constants

- `DESCRIPTOR_DEFAULTS_FILE = Path('.sharedrive/sharedrive_set.json')`

### Functions

- `def descriptor_scope_key(descriptor: Path | str) -> str`
  - Return the stable key used for descriptor-scoped defaults.
- `def get_checked_out_entity() -> str | None`
  - Return the currently checked-out entity dot-path, or None if no entity is active.
- `def get_saved_params_for_descriptor(descriptor: Path | str | None = None) -> dict[str, Any]`
  - Return merged global and descriptor-scoped saved params.
- `def load_descriptor_defaults_store() -> dict[str, Any]`
  - Load persisted descriptor defaults for global and descriptor scopes.
- `def resolve_default_descriptor() -> Path`
  - Return the first existing default descriptor path.
- `def resolve_descriptor_path(descriptor: Path | str | None = None) -> Path`
  - Resolve descriptor path from explicit input, saved defaults, or standard locations.
- `def resolve_output_dir(output_dir: Path | str | None = None, *, descriptor: Path | str | None = None) -> Path`
  - Resolve output_dir from explicit input, saved defaults, or the standard path.
- `def save_descriptor_defaults_store(data: dict[str, Any]) -> None`
  - Persist descriptor defaults store to disk.


## `sharedrive.models`

### Constants

- `CATALOG_PROFILE = 'data-package-catalog'`
- `ENTITY_TYPE_ALIASES = {'file': 'File', 'directory': 'Directory', 'folder': 'Directory', 'container': 'Container'}`
- `SERVICE_TYPE_ALIASES = {'googledrive': 'GoogleDrive', 'google-drive': 'GoogleDrive', 'google drive': 'GoogleDrive', 'sharepoint': 'SharePoint', 'share-point': 'SharePoint', 's3': 'S3'}`

### Functions

- `def load_drive_descriptor(path: Path | str, *, create_if_missing: bool = False) -> DriveCatalog`
- `def normalize_entity_type(entity_type: str) -> str`
  - Normalize source entity type to OpenMetadata-style class naming.
- `def normalize_service_type(service_type: str) -> str`
- `def save_drive_descriptor(path: Path | str, descriptor: DriveCatalog) -> None`

### Classes

#### `DriveDescriptor`
- Fields:
  - `profile: str`
  - `resources: list[DriveResource]`
  - `packages: list[DrivePackage]`
  - `catalogs: list['DriveCatalog']`
- Methods:
  - `def to_dict(self)`
  - `def get_entity_reference(self, selector: str) -> tuple[str, DriveResource | DrivePackage | 'DriveCatalog'] | None`
  - `def get_resource_reference(self, selector: str) -> tuple[str, DriveResource | DrivePackage] | None`

#### `DriveCatalog`
- Fields:
  - `profile: str`
  - `resources: list[DriveResource]`
  - `packages: list[DrivePackage]`
  - `catalogs: list['DriveCatalog']`
- Methods:
  - `def to_dict(self)`
  - `def get_entity_reference(self, selector: str) -> tuple[str, DriveResource | DrivePackage | 'DriveCatalog'] | None`
  - `def get_resource_reference(self, selector: str) -> tuple[str, DriveResource | DrivePackage] | None`

#### `DrivePackage`
- Fields:
  - `path: Optional[str]`
  - `sources: list[DriveSource]`
  - `drive_id: Optional[str]`
  - `resources: list['DriveResource | DrivePackage']`
  - `profile: Optional[str]`
- Methods:
  - `def primary_source(self) -> Optional[DriveSource]`
  - `def source_path(self) -> Optional[str]`
  - `def source_service_type(self) -> Optional[str]`
  - `def source_entity_type(self) -> Optional[str]`
  - `def to_dict(self)`
  - `def is_package(self) -> bool`
  - `def get_resource_reference(self, resource_selector: str) -> tuple[str, DriveResource | DrivePackage] | None`

#### `DriveResource`
- Fields:
  - `sources: list[DriveSource]`
  - `drive_id: Optional[str]`
  - `profile: Optional[str]`
- Methods:
  - `def primary_source(self) -> Optional[DriveSource]`
  - `def source_path(self) -> Optional[str]`
  - `def source_service_type(self) -> Optional[str]`
  - `def source_entity_type(self) -> Optional[str]`
  - `def sync_target(self) -> str`
    - Return the declared sync target for a resource.
  - `def syncs_to_resources(self) -> bool`
    - Return whether a resource syncs into nested resources.
  - `def is_package(self) -> bool`
  - `def to_dict(self)`
  - `def from_drive_metadata(cls, *, name: str, path: str, service_type: str, entity_type: str, source_url: str, format_str: Optional[str] = None, mediatype: Optional[str] = None, drive_id: Optional[str] = None, profile: Optional[str] = None) -> 'DriveResource'`

#### `DriveSource`
- Fields:
  - `serviceType: Optional[str]`
  - `entityType: Optional[str]`


## `sharedrive.item`

### Classes

#### `DriveFile`
- Methods:
  - `def is_directory(self) -> bool`
  - `def to_source(self) -> DriveSource`
  - `def to_resource(self) -> DriveResource`
  - `def to_dp(self) -> DriveResource` *(deprecated alias for `to_resource`)*
  - `def refresh(self, *, include_children: bool = True) -> 'DriveFile'`

#### `DriveFolder`
- Methods:
  - `def is_directory(self) -> bool`
  - `def children(self) -> list[DriveItem]`
  - `def iter_files(self) -> Iterable[DriveFile]`
  - `def refresh_tree(self) -> 'DriveFolder'`
  - `def download(self, target: Path | str) -> None`
  - `def to_source(self) -> DriveSource`
  - `def to_resource(self) -> DrivePackage`
  - `def to_dp(self) -> DrivePackage` *(deprecated alias for `to_resource`)*

#### `DriveItem`
- Methods:
  - `def id(self) -> str`
  - `def name(self) -> str`
  - `def path(self) -> str`
  - `def service_type(self) -> str`
  - `def source_url(self) -> str`
  - `def is_directory(self) -> bool`
  - `def download(self, target: Path | str) -> None`
  - `def refresh(self, *, include_children: bool = True) -> 'DriveItem'`
    - Refresh this runtime item from its backing service.
  - `def refresh_tree(self) -> 'DriveItem'`
    - Recursively refresh this runtime item and any descendant items.
  - `def to_source(self) -> DriveSource`
    - Convert to a `DriveSource` remote pointer (url, serviceType, entityType only).
  - `def to_resource(self) -> DriveResource | DrivePackage | DriveCatalog`
    - Convert to a descriptor resource, package, or catalog entry.
  - `def to_dp(self) -> DriveResource | DrivePackage` *(deprecated alias for `to_resource`)*


## `sharedrive.actions.add`

### Constants

- `SUPPORTED_SERVICE_TYPES = {'GoogleDrive', 'SharePoint', 'S3'}`

### Functions

- `def add_resource_to_descriptor(descriptor: Path | str, *, name: str, path: str, source: str, title: str | None = None, description: str | None = None, service_type: str | None = None, entity_type: str | None = None, sync_target: str | None = None, drive_service: str | None = None, package: bool = False, profile: str | None = None, create_if_missing: bool = False) -> dict[str, Any]`
  - Append a resource entry to a descriptor and return the created resource.
- `def infer_entity_type(source: str, *, service_type: str) -> str`
  - Infer OpenMetadata-style entityType from the source locator.
- `def infer_drive_service(source: str) -> str`
  - Backward-compatible alias for inferring canonical serviceType.
- `def infer_service_type(source: str) -> str`
  - Infer canonical serviceType from a source URL/URI.
- `def resolve_entity_type(source: str, *, service_type: str, entity_type: str | None = None) -> str`
  - Return the declared or inferred source entity type.
- `def resolve_service_type(source: str, service_type: str | None = None) -> str`
  - Return a supported canonical serviceType, inferring it when omitted.


## `sharedrive.actions.download`

### Functions

- `def check_auth_for_adapters(adapters: Iterable[str], *, sharepoint_client_factory: Callable[[], Any] | None = None, googledrive_client_factory: Callable[[], Any] | None = None, s3_auth_checker: Callable[[], None] | None = None) -> list[AuthCheckResult]`
- `def check_auth_for_descriptor(descriptor: Path | str, include: str | Iterable[str] = 'all', *, sharepoint_client_factory: Callable[[], Any] | None = None, googledrive_client_factory: Callable[[], Any] | None = None, s3_auth_checker: Callable[[], None] | None = None) -> list[AuthCheckResult]`
- `def download_from_descriptor(descriptor: Path | str, include: str | Iterable[str] = 'all', output_dir: Path | str = Path('resources'), dry_run: bool = False, *, check_auth: bool = False, log: LogFn | None = print, sharepoint_client_factory: Callable[[], Any] | None = None, googledrive_client_factory: Callable[[], Any] | None = None, use_cloudpathlib: bool = True) -> DownloadSummary`
  - Download resources from a descriptor using adapter-specific clients.
- `def download_resources(descriptor: Path | str, include: str | Iterable[str] = 'all', output_dir: Path | str = Path('resources'), dry_run: bool = False, *, check_auth: bool = False, log: LogFn | None = print) -> DownloadSummary`
  - Convenience alias for download_from_descriptor.
- `def load_descriptor(path: Path | str) -> DriveCatalog`
- `def resource_adapter_name(resource: Any, source_url: str | None) -> str`
  - Resolve runtime adapter name from source serviceType or fallback inference.
- `def resource_output_path(resource: Entry, output_dir: Path) -> Path`
  - Resolve resource.path against output_dir unless path is absolute.
- `def resource_output_paths(resource: Entry, output_dir: Path) -> list[Path]`
  - Resolve primary resource.path plus optional targets[] into local output paths.
- `def resource_source_url(resource: Any) -> str | None`
  - Resolve the primary source locator for a resource.

### Classes

#### `AuthCheckResult`
- Fields:
  - `adapter: str`
  - `ok: bool`
  - `message: str`
- Methods:
  - `def to_dict(self) -> dict[str, str | bool]`

#### `DownloadSummary`
- Fields:
  - `total_resources: int`
  - `downloaded: int`
  - `skipped: int`
  - `dry_run_actions: int`
  - `failures: int`
- Methods:
  - `def ok(self) -> bool`


## `sharedrive.actions.fetch`

### Functions

- `def fetch_entity_metadata_in_descriptor(descriptor: Path | str, entity_selector: str | None, *, dry_run: bool = False, depth: int = 0, log: LogFn | None = print, googledrive_client_factory: Callable[[], Any] | None = None, sharepoint_client_factory: Callable[[], Any] | None = None) -> list[FetchSummary]`
  - Fetch remote metadata for one entity (package or catalog) in a descriptor.
- `def fetch_resource_metadata_in_descriptor(descriptor: Path | str, resource_name: str, *, dry_run: bool = False, log: LogFn | None = print, googledrive_client_factory: Callable[[], Any] | None = None, sharepoint_client_factory: Callable[[], Any] | None = None) -> FetchSummary`
  - Fetch metadata for one package resource into nested descriptor resources.
- `def fetch_package_metadata_in_descriptor(descriptor: Path | str, package_name: str, *, dry_run: bool = False, log: LogFn | None = print, googledrive_client_factory: Callable[[], Any] | None = None, sharepoint_client_factory: Callable[[], Any] | None = None) -> FetchSummary`

### Classes

#### `FetchSummary`
- Fields:
  - `resource_name: str`
  - `generated_resources: int`
  - `dry_run: bool`
  - `changed: bool`


## `sharedrive.clients.aws`

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
  - `def list_files(self, *, query: str | None = None, fields: str = 'id, name, mimeType, parents', page_size: int = 100)`
    - List all files the authenticated user has access to.
  - `def list_folder_contents(self, folder_id: str, *, recursive: bool = False) -> list[Dict[str, Any]]`
    - List folder descendants and annotate each entry with a relative_path.
  - `def list_folder_files(self, folder_id: str, *, recursive: bool = True) -> list[Dict[str, Any]]`
    - List files contained in a folder, optionally descending into child folders.
  - `def list_folder_files_from_weburl(self, web_url: str, *, recursive: bool = True) -> list[Dict[str, Any]]`
    - Resolve a folder URL and list files contained within it.
  - `def get_file(self, file_id: str, **kwargs) -> Dict[str, Any]`
  - `def infer_export_mime_type(self, file_id: str) -> Optional[str]`
  - `def download_file(self, file_id: str, output_path: Optional[str] = None, mime_type: Optional[str] = None, acknowledge_abuse: bool = False, byte_range: Optional[str] = None, supports_all_drives: bool = True, **kwargs) -> Union[bytes, str]`
  - `def export_file(self, file_id: str, mime_type: Optional[str] = None, output_path: Optional[str] = None, supports_all_drives: bool = True, **kwargs) -> Union[bytes, str]`
  - `def create_file(self, parent_folder_id: str, file_in_bytes: Optional[bytes] = None, mime_type: Optional[str] = None, name: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None, supports_all_drives: bool = True, **kwargs) -> Dict[str, Any]`
  - `def update_file(self, file_id: str, file_in_bytes_or_path: Optional[Union[str, bytes]] = None, mime_type: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]`
  - `def create_folder(self, parent_folder_id: str, name: str) -> Dict[str, Any]`
  - `def get_from_weburl(self, web_url: str, fields: str = '*') -> 'GDriveItem'`
    - Return metadata for a Google Drive file or folder given a web URL,
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
  - `scopes: Annotated[list[str], NoDecode]`
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
  - `scopes: Annotated[list[str], NoDecode]`
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
  - `scopes: Annotated[list[str], NoDecode]`
- Methods:
  - `def empty_string_to_none(cls, value: str | None) -> str | None`
  - `def normalize_host_url(cls, value: str | None) -> str`
  - `def to_scope_list(cls, value: str | list[str] | tuple[str, ...] | None) -> list[str]`
  - `def validate_for_mode(self) -> MicrosoftAuthConfig`
  - `def to_strategy(self) -> AppOnlyStrategy | DelegatedStrategy`

#### `SharepointAuthMode`


## `sharedrive.clients.sharepoint`

### Classes

#### `SharepointClient`
- TODO: look into for local dev: https://learn.microsoft.com/en-us/powershell/microsoftgraph/overview?view=graph-powershell-1.0
- Methods:
  - `def get_site_id(self, site_name)`
  - `def list_site_drives(self, site_id: str) -> list[dict[str, Any]]`
  - `def get_drive_id(self, site_id, drive_name: str | None = None)`
    - Retrieves the default document drive associated with a SharePoint site.
  - `def get_item_metadata(self, drive: str, *, item_path: str | None = None, item_id: str | None = None, fields: list[str] | None = None)`
    - get item metadata based on relative file path or item id within the drive
  - `def resolve_weburl(self, url: str) -> dict[str, str]`
  - `def download_content(self, drive_id = None, item_id = None, download_url = None)`
    - takes in the components needed to download content --
  - `def get_from_weburl(self, url: str) -> 'SharepointItem'`
  - `def download(self, metadata, path)`
  - `def get_file(self, site_name, file_path, metadata_only = False)`
    - gets file item metadata and file
  - `def get_folder(self, site_name: str, path: str)`
    - Retrieve the contents of a folder, with optional recursion depth.
  - `def upload_new_content(self, site_name, folder_path, local_file_path)`
    - [IN DEVELOPMENT] Uploads a file to a specified SharePoint folder with proper Content-Type.
  - `def update_content(self, site_name, folder_path, local_file_path, create_if_missing = False)`
    - [IN DEVELOPMENT] Updates an existing file in SharePoint, or creates it if not found (optional).
