# sharedrive

!!!warning

  **IN DEVELOPMENT**

Experimental connectors and workflows for moving files across SharePoint, Google Drive, and S3.

## Current scope

- `sharedrive/sharepoint.py`: Microsoft Graph SharePoint client (`SharepointClient`)
- `sharedrive/googledrive.py`: Google Drive client (`GoogleDriveClient`)
- `sharedrive/azure.py`: SharePoint credential/config model (`SpoConfig`)
- `sharedrive/aws.py`: S3 URL parsing/download helpers (cloudpathlib + boto3 fallback)
- `sharedrive/actions/fetch.py`: reusable descriptor-based fetch Python API
- `sharedrive/retrieve.py`: compatibility shim for the older retrieval module path
- `sharedrive/cli.py`: Typer CLI (`sharedrive`)
- `scripts/retrieve_resources.py`: compatibility wrapper for descriptor retrieval
- `scripts/dev_adapters.py`: manual adapter smoke checks

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
- `GOOGLE_APPLICATION_CREDENTIALS`
- AWS credentials for S3 access

## Google Auth

`sharedrive` now separates Google credential acquisition from `GoogleDriveClient` itself.

For existing CLI and fetch flows, the compatibility behavior is unchanged:

- `sharedrive gdrive ...` and `sharedrive fetch ...` still use `GOOGLE_APPLICATION_CREDENTIALS` when set.
- If `GOOGLE_APPLICATION_CREDENTIALS` is not set, the Google Drive client falls back to Application Default Credentials.

For Python API usage, you can now choose an explicit auth strategy:

```python
from sharedrive.auth.google import AdcStrategy, UserOAuthStrategy
from sharedrive.auth.token_store import JsonTokenStore
from sharedrive.clients.google import GoogleDriveClient

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

## Fetch

CLI aliases:

- `sharepoint` and `spo` are equivalent subcommands for SharePoint operations.

CLI:

```bash
sharedrive fetch resources/descriptor.yaml --dry-run
sharedrive fetch resources/descriptor.yaml --include sharepoint
sharedrive fetch resources/descriptor.yaml --include s3,googledrive
sharedrive fetch resources/descriptor.yaml --include spec-workbook
```

If you are running from a repo checkout without activating an environment, prefix commands with `uv run`:

```bash
uv run sharedrive fetch resources/descriptor.yaml --dry-run
```

Python API:

```python
from pathlib import Path
from sharedrive.actions.fetch import fetch_from_descriptor

summary = fetch_from_descriptor(
    descriptor=Path("resources/descriptor.yaml"),
    include="all",  # or: "sharepoint", "s3", "googledrive", ["s3", "sharepoint"]
    output_dir=Path("resources"),
    dry_run=True,
)

if not summary.ok:
  raise RuntimeError(f"Fetch failed for {summary.failures} resources")
```

Compatibility script:

```bash
uv run python scripts/retrieve_resources.py --dry-run
```

## Descriptor format

`resources/descriptor.yaml` (or json/yml) must contain top-level `resources`:

```yaml
resources:
  - name: spec-workbook
    path: background/specs/spec-workbook.xlsx
    x-adapter: sharepoint
    sources:
      - path: https://norc.sharepoint.com/sites/...

  - name: source-export
    path: background/exports/source-export.csv
    x-adapter: s3
    sources:
      - path: s3://my-bucket/path/to/source-export.csv
```

Compatibility behavior preserved:

- `resources` top-level array
- `sources[].path` and legacy `source`
- `x-adapter` override support
- `targets` output paths beside `sources` (string, object, or list entries with `path`)

## Documentation site (MkDocs)

This repository now uses MkDocs for docs-site navigation and static markdown docs.

Install docs dependencies:

```bash
uv sync --extra docs
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
    retrieve_resources.py
  sharedrive/
    aws.py
    azure.py
    actions/
      fetch.py
    retrieve.py
    sharepoint.py
    googledrive.py
    cli.py
    app.py
  resources/
    descriptor.yaml
```
