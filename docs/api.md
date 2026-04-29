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
- `ENTITY_TYPE_ALIASES = {'file': 'File', 'directory': 'Directory', 'folder': 'Directory', 'container': 'Container'}`
- `SERVICE_TYPE_ALIASES = {'googledrive': 'GoogleDrive', 'google-drive': 'GoogleDrive', 'google drive': 'GoogleDrive', 'sharepoint': 'SharePoint', 'share-point': 'SharePoint', 's3': 'S3'}`

### Functions

- `def contained_entries(container: Entry) -> list[Entry]`
- `def entry_to_dict(entry: Entry) -> dict[str, Any]`
- `def inherited_entry(resource: Entry, *, parent: Entry | None = None) -> dict[str, Any]`
- `def iter_source_refs(resource: Entry, parent: Entry | None = None) -> list[DriveSourceReference]`
- `def load_drive_descriptor(path: Path | str, *, create_if_missing: bool = False) -> DriveCatalog`
- `def normalize_selector(selector: str | Iterable[str] | None) -> set[str]`
- `def normalize_entity_type(entity_type: str) -> str`
  - Normalize source entity type to OpenMetadata-style class naming.
- `def normalize_service_type(service_type: str) -> str`
- `def remote_basename(source_path: str) -> str`
- `def resolve_entity_reference(model: Model, selector: str, entity_types: tuple[type[T], ...]) -> EntityReference | None`
  - Resolve a dot-path selector to an entity reference.
- `def resource_matches_selector(resource: Entry, selector_set: set[str], *, selector_path: str | None = None) -> bool`
- `def resource_or_descendant_matches_selector(resource: Entry, selector_set: set[str], *, parent_selector_path: str | None = None) -> bool`
- `def resource_selector_path(resource: Entry, parent_selector_path: str | None = None) -> str`
- `def save_drive_descriptor(path: Path | str, descriptor: DriveCatalog) -> None`
- `def selected_adapter_names(resources: Iterable[Entry], selector: str | Iterable[str] | None = None) -> list[str]`
- `def sync_target(resource: Entry) -> str`

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
  - `def load_document(cls, path: Path | str) -> dict[str, Any]`
    - Load a sharedrive descriptor as a mutable document.
  - `def save_document(cls, path: Path | str, document: dict[str, Any]) -> None`
    - Validate and save a mutable sharedrive descriptor document.

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
  - `def load_document(cls, path: Path | str) -> dict[str, Any]`
    - Load a sharedrive descriptor as a mutable document.
  - `def save_document(cls, path: Path | str, document: dict[str, Any]) -> None`
    - Validate and save a mutable sharedrive descriptor document.

#### `DrivePackage`
- Fields:
  - `path: Optional[str]`
  - `sources: list[DriveSource]`
  - `drive_id: Optional[str]`
  - `resources: list['DriveResource | DrivePackage']`
  - `profile: Optional[str]`
- Methods:
  - `def to_dict(self)`
  - `def sync_target(self) -> str`
    - Return the declared sync target for a package-like resource.
  - `def is_package(self) -> bool`
  - `def get_resource_reference(self, resource_selector: str) -> tuple[str, DriveResource | DrivePackage] | None`

#### `DriveResource`
- Fields:
  - `sources: list[DriveSource]`
  - `drive_id: Optional[str]`
  - `profile: Optional[str]`
- Methods:
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
- Methods:
  - `def adapter_name(self, service_type: str | None = None) -> str`
    - Return the runtime adapter for this source.
  - `def key(self, *, index: int, adapter: str | None = None) -> str`
    - Return a deterministic path segment for namespacing this source.
  - `def target_path(self) -> str | None`
    - Return a source-level output override path, when declared.

#### `DriveSourceReference`
- A source selected in the context of an entity and source index.
- Fields:
  - `index: int`
  - `source: DriveSource`
  - `service_type: str | None`
  - `entity_type: str | None`
- Methods:
  - `def path(self) -> str`
  - `def adapter(self) -> str`
  - `def key(self) -> str`
  - `def target(self) -> str | None`


## `sharedrive.item`

### Classes

#### `DriveFile`
- Backward-compatible shell for a leaf (non-directory) drive item.
- Methods:
  - `def is_directory(self) -> bool`

#### `DriveFolder`
- Backward-compatible shell for a directory drive item.
- Methods:
  - `def is_directory(self) -> bool`
  - `def children(self) -> list[DriveItem]`

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
    - Convert to a :class:`~sharedrive.models.DriveSource` remote pointer.
  - `def to_resource(self) -> DriveResource | DrivePackage | DriveCatalog`
    - Convert to a descriptor resource, package, or catalog entry.
  - `def to_dp(self) -> DriveResource | DrivePackage`
    - Deprecated alias for :meth:`to_resource`.


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

- `def check_auth(descriptor: Path | str | None = None, selector: str | Iterable[str] | None = None, *, adapters: Iterable[str] | None = None) -> list[AuthCheckResult]`
  - Validate credentials for selected descriptor sources or explicit adapters.
- `def download(descriptor: Path | str, selector: str | Iterable[str] | None = None, *, output_dir: Path | str = Path('resources'), dry_run: bool = False, check_auth: bool = False, log: LogFn | None = print, use_cloudpathlib: bool = True) -> DownloadSummary`
  - Download all sources selected from a descriptor.

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

- `def fetch(descriptor: Path | str, selector: str | None = None, *, dry_run: bool = False, depth: int = 0, log: LogFn | None = print) -> list[FetchSummary]`
  - Fetch remote metadata for one selector in a descriptor.

### Classes

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


## `sharedrive.clients.aws`

### Functions

- `def download_s3_url(source_url: str, output_path: Path, *, dry_run: bool = False, use_cloudpathlib: bool = True) -> Path | None`
- `def parse_s3_source_url(source_url: str) -> tuple[str, str]`


## `sharedrive.clients.googledrive`

### Classes

#### `GoogleBaseClient`
- Shared Google client base: auth lifecycle and HTTP transport helpers.
- Fields:
  - `auth_methods: ClassVar[list[str]]`
- Methods:
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
  - `def get_from_weburl(self, web_url: str, fields: str = '*') -> 'GDriveItem'`
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

### Constants

- `DEFAULT_DRIVE_READONLY_SCOPES = ('https://www.googleapis.com/auth/drive.readonly',)`
- `DEFAULT_DRIVE_SCOPES = ('https://www.googleapis.com/auth/drive',)`

### Functions

- `def normalize_google_scopes(scopes: Sequence[str] | str | None, *, default: Sequence[str] = DEFAULT_DRIVE_SCOPES) -> list[str]`

### Classes

#### `GoogleAuth`
- Google credential holder with named constructors for each auth mode.
- Methods:
  - `def from_adc(cls, scopes: Sequence[str] | str | None = None) -> 'GoogleAuth'`
    - Build from Application Default Credentials (``gcloud auth application-default login``).
  - `def from_service_account(cls, credentials_path: str | Path, scopes: Sequence[str] | str | None = None) -> 'GoogleAuth'`
    - Build from a service account JSON key file.
  - `def from_user_oauth(cls, client_secrets_path: str | Path, scopes: Sequence[str] | str | None = None, token_store: TokenStore | None = None, use_local_server: bool = True) -> 'GoogleAuth'`
    - Build via the OAuth installed-app flow.
  - `def from_settings(cls, config: object | None = None) -> 'GoogleAuth'`
    - Build from environment variables or a :class:`~sharedrive.auth.settings.GoogleAuthConfig`.
  - `def credentials(self) -> Credentials`
    - The underlying :class:`~google.auth.credentials.Credentials` object.
  - `def ensure_valid(self) -> None`
    - Refresh the credential token if it has expired.


## `sharedrive.auth.microsoft`

### Constants

- `DEFAULT_MICROSOFT_GRAPH_SCOPES = ('https://graph.microsoft.com/.default',)`

### Functions

- `def normalize_microsoft_scopes(scopes: Sequence[str] | str | None, *, default: Sequence[str] = DEFAULT_MICROSOFT_GRAPH_SCOPES) -> list[str]`

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
- Persist authorized-user OAuth credentials as JSON on disk.
- Methods:
  - `def load(self) -> Credentials | None`
  - `def save(self, creds: Credentials) -> None`

#### `TokenStore`
- Methods:
  - `def load(self) -> Credentials | None`
  - `def save(self, creds: Credentials) -> None`


## `sharedrive.auth.settings`

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
