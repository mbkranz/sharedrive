# sharedrive

!!!warning

  **IN DEVELOPMENT**

Experimental connectors and workflows for moving files across SharePoint, Google Drive, and S3.

## Current scope

- `sharedrive/sharepoint.py`: Microsoft Graph SharePoint client (`SharepointClient`)
- `sharedrive/googledrive.py`: Google Drive client (`GoogleDriveClient`)
- `sharedrive/azure.py`: SharePoint credential/config model (`SpoConfig`)
- `sharedrive/aws.py`: S3 URL parsing/download helpers (cloudpathlib + boto3 fallback)
- `sharedrive/retrieve.py`: reusable descriptor-based retrieval Python API
- `sharedrive/cli.py`: Typer CLI (`sharedrive`)
- `scripts/retrieve_resources.py`: compatibility wrapper for descriptor retrieval
- `scripts/dev_adapters.py`: manual adapter smoke checks

## Setup

```bash
uv sync
```

Configure `.env` from `.env-sample` and set:

- `AZURE_TENANT_ID`
- `AZURE_CLIENT_ID`
- `AZURE_CLIENT_SECRET`
- `GOOGLE_APPLICATION_CREDENTIALS`
- AWS credentials for S3 access

## Retrieval

CLI:

```bash
sharedrive retrieve resources/descriptor.yaml --dry-run
sharedrive retrieve resources/descriptor.yaml --include sharepoint
sharedrive retrieve resources/descriptor.yaml --include s3,googledrive
sharedrive retrieve resources/descriptor.yaml --include spec-workbook
```

Python API:

```python
from pathlib import Path
from sharedrive.retrieve import retrieve_from_descriptor

summary = retrieve_from_descriptor(
    descriptor=Path("resources/descriptor.yaml"),
    include="all",  # or: "sharepoint", "s3", "googledrive", ["s3", "sharepoint"]
    output_dir=Path("resources"),
    dry_run=True,
)

if not summary.ok:
    raise RuntimeError(f"Retrieval failed for {summary.failures} resources")
```

Compatibility script:

```bash
python scripts/retrieve_resources.py --dry-run
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
python scripts/update_docs_markdown.py
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
    retrieve.py
    sharepoint.py
    googledrive.py
    cli.py
    app.py
  resources/
    descriptor.yaml
```
