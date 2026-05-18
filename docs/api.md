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
- `def has_saved_global_descriptor() -> bool`
  - Return whether the global defaults include a descriptor path.
- `def load_descriptor_defaults_store() -> dict[str, Any]`
  - Load persisted descriptor defaults for global and descriptor scopes.
- `def resolve_default_descriptor() -> Path`
  - Return the first existing default descriptor path.
- `def resolve_descriptor_path(descriptor: Path | str | None = None) -> Path`
  - Resolve descriptor path from explicit input, saved defaults, or standard locations.
- `def resolve_output_dir(output_dir: Path | str | None = None, *, descriptor: Path | str | None = None) -> Path`
  - Resolve output_dir from explicit input, saved defaults, or the standard path.
- `def save_params_for_scope(parsed: dict[str, Any], descriptor: Path | str | None, *, global_scope: bool) -> str`
  - Save reusable CLI params to the global or descriptor-specific scope.
- `def save_descriptor_defaults_store(data: dict[str, Any]) -> None`
  - Persist descriptor defaults store to disk.
- `def set_active_descriptor(descriptor_path: Path, *, entity: str | None = None) -> Path`
  - Persist the active descriptor and optional checked-out entity.


## `sharedrive.models`

### Constants

- `CATALOG_PROFILE = 'data-package-catalog'`
- `SUPPORTED_SERVICE_TYPES = {'GoogleDrive', 'SharePoint', 'S3'}`

### Functions

- `def adapter_from_locator(locator: str) -> str`
  - Infer a registry adapter name from a remote locator.
- `def adapter_from_service_type(service_type: str | None) -> str | None`
  - Map supported serviceType values to registry adapter names.
- `def infer_entity_type(locator: str, *, service_type: str) -> str`
  - Infer whether a locator points at a file, directory, or container.
- `def infer_service_type(locator: str) -> str`
  - Infer a supported serviceType from a remote locator.
- `def normalize_entity_type(value: str | None) -> str | None`
  - Normalize OpenMetadata-style drive/storage entity names.
- `def normalize_service_type(value: str | None) -> str | None`
  - Normalize OpenMetadata-style drive/storage service names.
- `def resolve_cache_path(resource: 'DriveResource', output_dir: Path) -> Path`
  - Resolve a resource's `_cache` path under the requested output directory.
- `def resolve_entity_type(locator: str, *, service_type: str, entity_type: str | None = None) -> str`
  - Return the declared or inferred entity type.
- `def resolve_service_type(locator: str, service_type: str | None = None) -> str`
  - Return a supported canonical serviceType, inferring it when omitted.

### Classes

#### `DriveCatalog`
- Fields:
  - `profile: str`
  - `accessURL: Optional[str]`
  - `serviceType: Optional[str]`
  - `entityType: Optional[str]`
  - `resources: list[DriveResource]`
  - `packages: list[DrivePackage]`
  - `catalogs: list['DriveCatalog']`
- Methods:
  - `def adapter_name(self) -> str`
  - `def to_dict(self)`
  - `def empty(cls) -> 'DriveCatalog'`

#### `DrivePackage`
- Logical Data Package; not used as a remote folder surrogate.
- Fields:
  - `resources: list['DriveResource | DrivePackage']`
  - `sources: list[DriveSource]`

#### `DriveResource`
- Data Package resource with shared-drive adapter metadata.
- Fields:
  - `cache: Annotated[Optional[str], Field(default=None, alias='_cache', validation_alias=AliasChoices('_cache', 'cache'))]`
  - `serviceType: Optional[str]`
  - `entityType: Optional[str]`
  - `sources: list[DriveSource]`
- Methods:
  - `def adapter_name(self) -> str`
  - `def from_drive_metadata(cls, *, name: str, path: str, service_type: str, entity_type: str, source_url: str, format_str: str | None = None, drive_id: str | None = None) -> 'DriveResource'`
    - Create a standards-aligned resource from runtime drive metadata.

#### `DriveSource`
- Provenance source.


## `sharedrive.item`

### Classes

#### `DriveFile`
- Backward-compatible file item base class.
- Methods:
  - `def is_directory(self) -> bool`

#### `DriveFolder`
- Backward-compatible folder item base class.
- Methods:
  - `def is_directory(self) -> bool`

#### `DriveItem`
- Abstract base for a single item (file or directory) on a remote drive.
- Methods:
  - `def id(self) -> str`
  - `def name(self) -> str`
  - `def path(self) -> str`
  - `def service_type(self) -> str`
  - `def source_url(self) -> str`
  - `def is_directory(self) -> bool`
  - `def refresh(self, *, include_children: bool = True) -> 'DriveItem'`
    - Refresh this runtime item from its backing service.
  - `def children(self) -> list['DriveItem']`
    - Direct child items for directories; always empty for files.
  - `def iter_files(self) -> Iterable['DriveItem']`
    - Recursively yield all leaf (non-directory) items.
  - `def refresh_tree(self) -> 'DriveItem'`
    - Recursively refresh this item and all of its descendants.
  - `def download(self, target: Path | str) -> None`
    - Download this item to *target*.
  - `def to_source(self) -> DriveSource`
    - Convert to a provenance source entry.
  - `def to_resource(self) -> DriveResource | DrivePackage | DriveCatalog`
    - Convert to a descriptor resource, package, or catalog entry.
  - `def to_dp(self) -> DriveResource | DrivePackage`
    - Deprecated alias for :meth:`to_resource`.


## `sharedrive.catalog`

### Classes

#### `AuthCheckResult`
- Fields:
  - `adapter: str`
  - `ok: bool`
  - `message: str`
- Methods:
  - `def to_dict(self) -> dict[str, str | bool]`

#### `CatalogSelector`
- Normalised selector for catalog entities.
- Methods:
  - `def tokens(self) -> frozenset[str] | None`
    - The normalised set of filter tokens, or ``None`` for "select all".
  - `def matches(self, ref: Any) -> bool`
    - Return True if *ref* matches any selector token.

#### `DownloadSummary`
- Fields:
  - `total_resources: int`
  - `downloaded: int`
  - `skipped: int`
  - `dry_run_actions: int`
  - `failures: int`
- Methods:
  - `def ok(self) -> bool`

#### `FetchSummary`
- Fields:
  - `resource_name: str`
  - `generated_resources: int`
  - `dry_run: bool`
  - `changed: bool`
  - `failures: int`
  - `errors: list[str]`
- Methods:
  - `def ok(self) -> bool`

#### `SharedriveCatalog`
- Python workflow API for one shared-drive descriptor catalog.
- Methods:
  - `def from_path(cls, path: Path | str) -> 'SharedriveCatalog'`
  - `def save(self, path: Path | str | None = None) -> Path`
    - Write the loaded descriptor model to disk.
  - `def client(self, adapter: str) -> Any`
  - `def references(self, selector: str | Iterable[str] | None = None) -> list[Any]`
  - `def resources(self, selector: str | Iterable[str] | None = None) -> list[DriveResource]`
  - `def adapter_names(self, selector: str | Iterable[str] | None = None) -> list[str]`
  - `def check_auth(self, selector: str | Iterable[str] | None = None, *, adapters: Iterable[str] | None = None) -> list[AuthCheckResult]`
  - `def fetch(self, selector: str | None = None, *, dry_run: bool = False, depth: int = -1, log: LogFn | None = print, persist: bool | Path | str = False) -> list[FetchSummary]`
  - `def download(self, selector: str | Iterable[str] | None = None, *, output_dir: Path | str = Path('resources'), dry_run: bool = False, check_auth: bool = False, log: LogFn | None = print, use_cloudpathlib: bool = True) -> DownloadSummary`


## `sharedrive.clients.aws`

### Functions

- `def check_s3_credentials() -> None`
  - Validate that AWS credentials are available for S3 operations.
- `def download_s3_url(source_url: str, output_path: Path, *, dry_run: bool = False, use_cloudpathlib: bool = True) -> Path | None`
  - Backward-compatible helper for downloading an S3 object URL to a local path.
- `def parse_s3_source_url(source_url: str, *, allow_empty_key: bool = False) -> tuple[str, str]`
  - Parse an S3 URL into bucket/key.

### Classes

#### `S3Client`
- Methods:
  - `def build_default(cls) -> 'S3Client'`
  - `def check_auth(cls) -> None`
  - `def get_from_weburl(self, url: str) -> 'S3Item'`
  - `def download_from_weburl(self, source_url: str, output_path: Path, *, dry_run: bool = False, use_cloudpathlib: bool = True) -> Path | None`

#### `S3Item`
- Methods:
  - `def id(self) -> str`
  - `def name(self) -> str`
  - `def path(self) -> str`
  - `def service_type(self) -> str`
  - `def source_url(self) -> str`
  - `def is_directory(self) -> bool`
  - `def children(self) -> list['S3Item']`
  - `def refresh(self, *, include_children: bool = True) -> 'S3Item'`
  - `def download(self, target_dir: str | Path) -> None`


## `sharedrive.clients.googledrive`

### Classes

#### `GoogleBaseClient`
- Shared Google client base: auth lifecycle and HTTP transport helpers.
- Fields:
  - `auth_methods: ClassVar[list[str]]`
  - `capabilities: ClassVar[AdapterCapabilities]`
- Methods:
  - `def refresh(self) -> None`
  - `def get_from_weburl(self, url: str)`
  - `def build_default(cls) -> 'GoogleBaseClient'`
    - Construct from environment variables / settings.
  - `def check_auth(cls) -> None`
    - Validate that Google credentials are available.

#### `GoogleDriveClient`
- Google Drive client (ID-first) with read/write and full export coverage.
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
  - `def get_from_weburl(self, web_url: str, fields: str = '*') -> DriveItem`
    - Return metadata for a Google Drive file or folder given a web URL,
  - `def download_from_weburl(self, web_url: str, **kwargs) -> Union[bytes, str]`
  - `def export_from_weburl(self, web_url: str, mime_type: Optional[str] = None, **kwargs) -> Union[bytes, str]`
  - `def update_from_weburl(self, web_url: str, **kwargs) -> Dict[str, Any]`

#### `GDriveItem`
- A Google Drive file or folder item backed by the Drive REST API.
- Methods:
  - `def id(self) -> str`
  - `def name(self) -> str`
  - `def path(self) -> str`
  - `def service_type(self) -> str`
  - `def source_url(self) -> str`
  - `def is_directory(self) -> bool`
  - `def children(self) -> list['GDriveItem']`
    - Direct children of this directory; empty list for files.
  - `def refresh(self, *, include_children: bool = True) -> 'GDriveItem'`
    - Re-fetch raw metadata (and optionally children) from the API.
  - `def download(self, target_dir: str | Path) -> None`
    - Download this item.

#### `GDriveFile`
- A Google Drive file or folder item backed by the Drive REST API.
- Methods:
  - `def id(self) -> str`
  - `def name(self) -> str`
  - `def path(self) -> str`
  - `def service_type(self) -> str`
  - `def source_url(self) -> str`
  - `def is_directory(self) -> bool`
  - `def children(self) -> list['GDriveItem']`
    - Direct children of this directory; empty list for files.
  - `def refresh(self, *, include_children: bool = True) -> 'GDriveItem'`
    - Re-fetch raw metadata (and optionally children) from the API.
  - `def download(self, target_dir: str | Path) -> None`
    - Download this item.

#### `GDriveFolder`
- A Google Drive file or folder item backed by the Drive REST API.
- Methods:
  - `def id(self) -> str`
  - `def name(self) -> str`
  - `def path(self) -> str`
  - `def service_type(self) -> str`
  - `def source_url(self) -> str`
  - `def is_directory(self) -> bool`
  - `def children(self) -> list['GDriveItem']`
    - Direct children of this directory; empty list for files.
  - `def refresh(self, *, include_children: bool = True) -> 'GDriveItem'`
    - Re-fetch raw metadata (and optionally children) from the API.
  - `def download(self, target_dir: str | Path) -> None`
    - Download this item.


## `sharedrive.auth.google`

### Classes

#### `GoogleAuth`
- Google credential holder with named constructors for each auth mode.
- Methods:
  - `def refresh(self) -> None`
    - Refresh the access token
  - `def from_adc(cls, scopes: Sequence[str] | str | None = None) -> 'GoogleAuth'`
    - Build from Application Default Credentials (``gcloud auth application-default login``).
  - `def from_service_account(cls, credentials_path: str | Path, scopes: Sequence[str] | str | None = None) -> 'GoogleAuth'`
    - Build from a service account JSON key file.
  - `def from_user_oauth(cls, scopes: Sequence[str] | str, client_secrets_path: str | Path = None, token_path: str | Path = None, token_store: Any = None) -> 'GoogleAuth'`
    - Build via the OAuth installed-app flow, with token persistence.
  - `def from_settings(cls, config: object | None = None) -> 'GoogleAuth'`
    - Build from environment variables or a :class:`~sharedrive.auth.settings.GoogleAuthConfig`.
  - `def credentials(self) -> Credentials`
    - The underlying :class:`~google.auth.credentials.Credentials` object.
  - `def ensure_valid(self) -> None`
    - Refresh credentials when the current token is not valid.


## `sharedrive.auth.microsoft`

### Classes

#### `MicrosoftAuth`
- Microsoft access-token holder with named constructors for each auth mode.
- Methods:
  - `def from_app_only(cls, tenant_id: str, client_id: str, client_secret: str, scopes: Sequence[str] | str | None = None) -> 'MicrosoftAuth'`
    - Build using client-credential (app-only) flow via MSAL.
  - `def from_delegated(cls, tenant_id: str, client_id: str, scopes: Sequence[str] | str | None = None) -> 'MicrosoftAuth'`
    - Build using interactive delegated (user) flow via MSAL.
  - `def from_settings(cls, config: object | None = None) -> 'MicrosoftAuth'`
    - Build from environment variables or a :class:`~sharedrive.auth.settings.MicrosoftAuthConfig`.
  - `def access_token(self) -> str`
    - The raw Bearer access token string.


## `sharedrive.auth.token_store`

### Classes

#### `JsonTokenStore`
- Persist Google authorized-user credentials as JSON.
- Methods:
  - `def load(self) -> UserCredentials | None`
  - `def save(self, creds: UserCredentials) -> None`


## `sharedrive.auth.settings`

### Classes

#### `GoogleAuthConfig`
- Fields:
  - `auth_mode: GoogleAuthMode`
  - `service_account_credentials: Path | None`
  - `oauth_client_secrets: Path | None`
  - `oauth_token_path: Path`
  - `scopes: Annotated[list[str], NoDecode]`
  - `use_local_server: bool`
- Methods:
  - `def to_scope_list(cls, value: str | list[str] | tuple[str, ...] | None) -> list[str]`
  - `def validate_for_mode(self) -> GoogleAuthConfig`
  - `def to_auth(self) -> GoogleAuth`
    - Return a :class:`~sharedrive.auth.google.GoogleAuth` for this configuration.

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
  - `def to_auth(self) -> MicrosoftAuth`
    - Return a :class:`~sharedrive.auth.microsoft.MicrosoftAuth` for this configuration.

#### `MicrosoftAuthMode`


## `sharedrive.clients.sharepoint`

### Classes

#### `SharepointClient`
- SharePoint / OneDrive client backed by the Microsoft Graph API.
- Fields:
  - `auth_methods: ClassVar[list[str]]`
  - `capabilities: ClassVar[AdapterCapabilities]`
- Methods:
  - `def build_default(cls) -> 'SharepointClient'`
    - Construct from environment variables / settings.
  - `def check_auth(cls) -> None`
    - Validate that Microsoft Graph credentials are available.
  - `def get_site_id(self, site_name)`
  - `def list_site_drives(self, site_id: str) -> list[dict[str, Any]]`
  - `def get_drive_id(self, site_id, drive_name: str | None = None)`
    - Retrieves the default document drive associated with a SharePoint site.
  - `def get_item_metadata(self, drive: str, *, item_path: str | None = None, item_id: str | None = None, fields: list[str] | None = None)`
    - get item metadata based on relative file path or item id within the drive
  - `def resolve_weburl(self, url: str) -> dict[str, str]`
  - `def download_content(self, drive_id = None, item_id = None, download_url = None)`
    - takes in the components needed to download content --
  - `def get_from_weburl(self, url: str) -> DriveItem`
  - `def download(self, metadata, path)`
  - `def get_file(self, site_name, file_path, metadata_only = False)`
    - gets file item metadata and file
  - `def get_folder(self, site_name: str, path: str)`
    - Retrieve the contents of a folder, with optional recursion depth.
  - `def upload_new_content(self, site_name, folder_path, local_file_path)`
    - [IN DEVELOPMENT] Uploads a file to a specified SharePoint folder with proper Content-Type.
  - `def update_content(self, site_name, folder_path, local_file_path, create_if_missing = False)`
    - [IN DEVELOPMENT] Updates an existing file in SharePoint, or creates it if not found (optional).

#### `SharepointItem`
- A SharePoint file or folder item backed by the Graph API.
- Methods:
  - `def id(self) -> str`
  - `def name(self) -> str`
  - `def path(self) -> str`
  - `def service_type(self) -> str`
  - `def source_url(self) -> str`
  - `def is_directory(self) -> bool`
  - `def children(self) -> list['SharepointItem']`
    - Direct children of this directory; empty list for files.
  - `def refresh(self, *, include_children: bool = True) -> 'SharepointItem'`
    - Re-fetch raw metadata (and optionally children) from the Graph API.
  - `def download(self, target_dir: str | Path) -> None`
    - Download this item.

#### `SharepointFile`
- A SharePoint file or folder item backed by the Graph API.
- Methods:
  - `def id(self) -> str`
  - `def name(self) -> str`
  - `def path(self) -> str`
  - `def service_type(self) -> str`
  - `def source_url(self) -> str`
  - `def is_directory(self) -> bool`
  - `def children(self) -> list['SharepointItem']`
    - Direct children of this directory; empty list for files.
  - `def refresh(self, *, include_children: bool = True) -> 'SharepointItem'`
    - Re-fetch raw metadata (and optionally children) from the Graph API.
  - `def download(self, target_dir: str | Path) -> None`
    - Download this item.

#### `SharepointFolder`
- A SharePoint file or folder item backed by the Graph API.
- Methods:
  - `def id(self) -> str`
  - `def name(self) -> str`
  - `def path(self) -> str`
  - `def service_type(self) -> str`
  - `def source_url(self) -> str`
  - `def is_directory(self) -> bool`
  - `def children(self) -> list['SharepointItem']`
    - Direct children of this directory; empty list for files.
  - `def refresh(self, *, include_children: bool = True) -> 'SharepointItem'`
    - Re-fetch raw metadata (and optionally children) from the Graph API.
  - `def download(self, target_dir: str | Path) -> None`
    - Download this item.
