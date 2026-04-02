# sharedrive

!!!warning

  **IN DEVELOPMENT**

Experimental connectors and workflows for moving files across SharePoint, Google Drive, and S3.

## Current scope

- `sharedrive/clients/sharepoint.py`: Microsoft Graph SharePoint client (`SharepointClient`)
- `sharedrive/clients/googledrive.py`: Google Drive client (`GoogleDriveClient`)
- `sharedrive/item.py`: runtime item abstractions for live remote files and folders
- `sharedrive/models.py`: descriptor and metadata models for persisted catalog/package/resource state
- `sharedrive/auth/microsoft.py`: SharePoint access-token strategies
- `sharedrive/auth/settings.py`: Google and SharePoint auth settings/factories
- `sharedrive/clients/aws.py`: S3 URL parsing/download helpers (cloudpathlib + boto3 fallback)
- `sharedrive/actions/fetch.py`: reusable descriptor-based fetch Python API
- `sharedrive/actions/sync.py`: reusable descriptor sync Python API for package resources
- `sharedrive/cli.py`: Typer CLI (`sharedrive`)
- `scripts/dev_adapters.py`: manual adapter smoke checks

## Architecture

`sharedrive` uses a layered adapter-oriented architecture.

- Descriptor models in `sharedrive/models.py` represent persisted catalog metadata. They validate YAML/JSON descriptor files, normalize fields such as `serviceType` and `entityType`, and are the source of truth for what gets written back to disk.
- Runtime items in `sharedrive/item.py` represent live remote files and folders. They are adapter-backed objects returned by service clients and expose runtime behavior such as `download()`, `refresh()`, `children`, and `iter_files()`.
- Clients in `sharedrive/clients/*.py` translate provider APIs into runtime items. They own provider-specific HTTP calls, URL resolution, pagination, and item construction.
- Action modules in `sharedrive/actions/*.py` orchestrate workflows across descriptors, clients, and runtime items. They load descriptors, select adapters, resolve runtime roots, traverse items, and save descriptor updates or materialize downloads.
- The CLI in `sharedrive/cli.py` is the outer interface. It parses user input, resolves defaults, and delegates to action-layer workflows.

The important separation is between persisted descriptor state and live runtime state:

- Descriptor models describe what is stored.
- Runtime items describe what is currently available from a remote service.
- Actions translate between the two when workflows need both.

This is why `sharedrive fetch ...` remains an action-layer descriptor update, while runtime items use `refresh()` to reload in-memory remote state.

## Setup

### Prerequisites

- Python 3.12+ (see `requires-python` in `pyproject.toml`)
- `uv` installed (recommended)
  - Install instructions: https://docs.astral.sh/uv/getting-started/installation/

### Install (CLI tool)

If you primarily want the `sharedrive` CLI, install it as a `uv` tool (no repo checkout / venv activation needed):

```bash
# from a local clone (path to the git repo)
uv tool install "<path-to-sharedrive-repo>"

# if you're already in the repo directory
uv tool install .

# OR from a git repo URL
uv tool install "sharedrive @ git+https://github.com/<org>/<repo>.git"
```

After install, run:

```bash
sharedrive --help
```

### Install (Python API dependency)

If you want to call `sharedrive` from your own Python project:

```bash
# from a local clone (path to the git repo)
uv add "<path-to-sharedrive-repo>"

# OR from a git repo URL
uv add "sharedrive @ git+https://github.com/<org>/<repo>.git"
```

Alternative (without `uv`):

```bash
pip install "<path-to-sharedrive-repo>"

# or, if you're already in the repo directory
pip install .
```

### Install (repo development)

If you are developing in this repository:

```bash
uv sync
uv sync --extra dev --extra test
```

Configure `.env` from `.env-sample` and set:

- `AZURE_TENANT_ID`
- `AZURE_CLIENT_ID`
- `AZURE_CLIENT_SECRET`
- `SHAREPOINT_AUTH_MODE`
- `GOOGLE_APPLICATION_CREDENTIALS`
- AWS credentials for S3 access

## Microsoft Auth For SharePoint

`sharedrive` now separates Microsoft token acquisition from `SharepointClient` itself.

The primary Microsoft auth surface is now:

- `sharedrive.auth.microsoft` for delegated and app-only Microsoft Graph token strategies
- `sharedrive.auth.settings.MicrosoftAuthConfig` for env-validated configuration
- `sharedrive.auth.settings.make_sharepoint_client_from_microsoft_auth()` for SharePoint client construction

Backward-compatible aliases remain available under `sharedrive.auth.sharepoint`, `SharepointAuthConfig`, and `make_sharepoint_client_from_settings()`.

Supported first-class SharePoint auth patterns:

- App-only Microsoft Graph auth via `AppOnlyStrategy`
- Delegated interactive auth via `DelegatedStrategy`

For CLI operators:

- `sharedrive auth login microsoft` validates Microsoft auth directly using the configured mode
- `sharedrive auth login sharepoint` validates SharePoint auth using the configured mode
- `sharedrive auth check <descriptor>` includes SharePoint in descriptor-aware preflight checks
- `sharedrive download ... --check-auth` validates SharePoint credentials before downloading selected resources

For Python API usage:

```python
from sharedrive.auth.settings import (
  MicrosoftAuthConfig,
  make_sharepoint_client_from_microsoft_auth,
)

config = MicrosoftAuthConfig()
client = make_sharepoint_client_from_microsoft_auth(config)
```

Compatibility note:

- `sharedrive.azure.SpoConfig` remains as a thin shim over the new settings layer.

## Google Auth

`sharedrive` now separates Google credential acquisition from `GoogleDriveClient` itself.

For existing CLI download flows, the compatibility behavior is unchanged:

- `sharedrive download ...` still uses `GOOGLE_APPLICATION_CREDENTIALS` when set.
- If `GOOGLE_APPLICATION_CREDENTIALS` is not set, the Google Drive client falls back to Application Default Credentials.

For CLI operators, there are now explicit auth-oriented commands in addition to the transfer commands:

- `sharedrive set --global --descriptor resources/descriptor.yaml` saves a reusable default descriptor path for descriptor-based commands.
- `sharedrive auth check [descriptor]` validates credentials for the adapters selected by a descriptor before any download starts.
- `sharedrive auth login gdrive` runs the installed-app Google OAuth flow and can persist an authorized-user token to `GOOGLE_OAUTH_TOKEN_PATH` or an explicit `--oauth-token-path`.
- `sharedrive auth login microsoft` validates Microsoft auth used by SharePoint workflows.
- `sharedrive auth login sharepoint` validates SharePoint auth using app-only or delegated mode.
- `sharedrive add ...` can omit `--descriptor` once a default descriptor has been saved.
- `sharedrive checkout <descriptor>` saves the active descriptor for later commands.
- `sharedrive add ... --package` creates a folder-backed package resource for descriptor metadata fetch and package-aware download.
- `sharedrive fetch <package-name>` refreshes nested resources for Google Drive or SharePoint package resources inside a descriptor.
- `sharedrive download ... --check-auth` runs the same descriptor-aware preflight before downloading.

For Python API usage, you can now choose an explicit auth strategy:

```python
from sharedrive.auth.google import AdcStrategy, UserOAuthStrategy
from sharedrive.auth.token_store import JsonTokenStore
from sharedrive.clients.googledrive import GoogleDriveClient

adc_client = GoogleDriveClient(
  credential_strategy=AdcStrategy(),
)

oauth_client = GoogleDriveClient(
  credential_strategy=UserOAuthStrategy(
    client_secrets_path=".google/oauth-credentials.json",
    token_store=JsonTokenStore(".google/oauth-token.json"),
    scopes=["https://www.googleapis.com/auth/drive.readonly"],
  )
)
```

Supported first-class Google auth patterns:

- Application Default Credentials via `AdcStrategy`
- Service account JSON via `ServiceAccountStrategy`
- Installed-app user OAuth via `UserOAuthStrategy`
- Ordered fallback via `ChainedStrategy`

Token persistence for user OAuth should use `JsonTokenStore`; pickle-based persistence is intentionally not the default.

If you prefer env-validated configuration instead of building strategies manually, use `GoogleAuthConfig`:

```python
from sharedrive.auth.settings import GoogleAuthConfig, make_google_drive_client_from_settings

config = GoogleAuthConfig()
client = make_google_drive_client_from_settings(config)
```

The settings layer is additive. Existing `GOOGLE_APPLICATION_CREDENTIALS` behavior in the CLI and retrieval flows still works.

## Fetch And Download

CLI:

```bash
sharedrive checkout resources/descriptor.yaml
sharedrive set --global --output-dir resources
sharedrive auth check
sharedrive auth check resources/descriptor.yaml
sharedrive auth login gdrive --oauth-client-secrets .google/oauth-credentials.json --oauth-token-path .google/oauth-token.json
sharedrive auth login microsoft --auth-mode delegated
sharedrive auth login sharepoint --auth-mode delegated
sharedrive add spec-workbook --path background/specs/spec-workbook.xlsx --source https://tenant.sharepoint.com/sites/Test/Shared%20Documents/spec.xlsx
sharedrive add census-package --path downloads/census --source https://drive.google.com/drive/folders/<id> --drive-service googledrive --package
sharedrive fetch census-package --dry-run
sharedrive download --dry-run
sharedrive download resources/descriptor.yaml --dry-run
sharedrive download resources/descriptor.yaml --check-auth
sharedrive download resources/descriptor.yaml --include sharepoint
sharedrive download resources/descriptor.yaml --include s3,googledrive
sharedrive download resources/descriptor.yaml --include spec-workbook
sharedrive update --title "Hello" --description "hello"
sharedrive update --resource spec-workbook --title "Hello"
```

If you are running from a repo checkout without activating an environment, prefix commands with `uv run`:

```bash
uv run sharedrive checkout resources/descriptor.yaml
uv run sharedrive download --dry-run
uv run sharedrive download resources/descriptor.yaml --dry-run
```

Saved defaults are persisted in `.sharedrive/sharedrive_set.json`.
Use `sharedrive checkout ...` to avoid repeating the descriptor path for `sharedrive auth check`, `sharedrive add`, `sharedrive fetch`, `sharedrive download`, and `sharedrive update`.
Use `sharedrive set --global --output-dir ...` to save a reusable output directory for `sharedrive download`.
Use `sharedrive set <descriptor> --output-dir ...` to save descriptor-scoped defaults that apply when you explicitly download that descriptor.

Python API:

```python
from pathlib import Path
from sharedrive.actions.download import download_from_descriptor

summary = download_from_descriptor(
    descriptor=Path("resources/descriptor.yaml"),
    include="all",  # or: "sharepoint", "s3", "googledrive", ["s3", "sharepoint"]
    output_dir=Path("resources"),
    dry_run=True,
)

if not summary.ok:
  raise RuntimeError(f"Download failed for {summary.failures} resources")
```

Runtime item API:

```python
from sharedrive.auth.google import default_drive_strategy
from sharedrive.clients.googledrive import GoogleDriveClient

client = GoogleDriveClient(credential_strategy=default_drive_strategy())
item = client.get_from_weburl("https://drive.google.com/drive/folders/<id>")

item.refresh()
for child in item.children:
  print(child.path)

item.refresh_tree()
```

Runtime items returned by service clients are live adapter-backed objects.
Use `refresh()` to reload a file or folder from the backing service.
Use `refresh_tree()` when you want a folder and its descendants refreshed recursively before traversal.
For folders, `children` exposes the current immediate child items and `iter_files()` flattens nested files.
Descriptor fetch remains an action-layer workflow: `sharedrive fetch ...` updates descriptor metadata, while runtime item refresh updates in-memory remote objects.

## Descriptor format

`resources/descriptor.yaml` (or json/yml) must contain top-level `resources`:

```yaml
resources:
  - name: spec-workbook
    path: background/specs/spec-workbook.xlsx
    driveService: sharepoint
    sources:
      - path: https://norc.sharepoint.com/sites/...

  - name: source-export
    path: background/exports/source-export.csv
    driveService: s3
    sources:
      - path: s3://my-bucket/path/to/source-export.csv

  - name: census-package
    profile: data-package
    path: downloads/census
    driveService: googledrive
    sources:
      - path: https://drive.google.com/drive/folders/<id>
    resources: []
```

Folder-backed package resources can be authored explicitly with `sharedrive add --package` and then populated with nested resources using `sharedrive fetch <package-name>`. Fetch now supports Google Drive and SharePoint package resources and writes deterministic nested file resources into the descriptor.

Compatibility behavior preserved:

- `resources` top-level array
- `sources[].path` and legacy `source`
- `driveService` canonical service field
- legacy `x-adapter` override support for existing descriptors
- `targets` output paths beside `sources` (string, object, or list entries with `path`)

Add a descriptor resource from the CLI:

```bash
sharedrive add spec-workbook \
  --path background/specs/spec-workbook.xlsx \
  --descriptor resources/descriptor.yaml \
  --source https://tenant.sharepoint.com/sites/Test/Shared%20Documents/spec.xlsx \
  --title "Spec workbook" \
  --description "Source workbook for specs"
```

## Documentation site (MkDocs)

This repository now uses MkDocs for docs-site navigation and static markdown docs.

Install docs dependencies:

```bash
uv sync --group docs
```

Run docs locally:

```bash
uv run mkdocs serve
```

Build static docs:

```bash
uv run mkdocs build
```

Regenerate GitHub-viewable CLI/API markdown docs:

```bash
uv run python scripts/update_docs_markdown.py
```

Docs sources:

- `mkdocs.yml`
- `docs/index.md`
- `docs/cli.md`
- `docs/api.md`
- `scripts/update_docs_markdown.py`

## Repository layout

```text
sharedrive/
  docs/
    index.md
    cli.md
    api.md
  scripts/
    dev_adapters.py
  sharedrive/
    aws.py
    azure.py
    actions/
      fetch.py
      add.py
    cli.py
    app.py
  resources/
    descriptor.yaml
```
