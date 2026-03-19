# sharedrive

Shared-drive adapters and retrieval workflows for SharePoint, Google Drive, and S3.


## TODO

- finish google drive authentication doc page with info from ppsc-pmd-utils/docs 
- create the Sharepoint auth documentation page
- build out the "list" action



## Quick start

```bash
uv sync
```

Configure `.env` with:

- `AZURE_TENANT_ID`
- `AZURE_CLIENT_ID`
- `AZURE_CLIENT_SECRET`
- `GOOGLE_APPLICATION_CREDENTIALS`

Google Drive auth supports two layers:

- Compatibility mode for CLI and descriptor retrieval using `GOOGLE_APPLICATION_CREDENTIALS` or ADC.
- Explicit Python auth strategies via `sharedrive.auth.google` for ADC, service account, user OAuth, and chained fallback.

See also: [Google Auth Credentials](google-auth.md) for manual OAuth setup and non-interactive automation options.

## Retrieval

CLI:

```bash
sharedrive add census-package --path downloads/census --source https://drive.google.com/drive/folders/<id> --drive-service googledrive --package
sharedrive sync census-package --descriptor resources/descriptor.yaml --dry-run
sharedrive fetch resources/descriptor.yaml --dry-run
```

## Package resources

`sharedrive` now supports folder-backed package resources in descriptors. A package resource is a top-level descriptor resource with a package profile, a local root `path`, and a remote folder source. `sharedrive sync <package-name>` can populate that package with nested file resources from Google Drive, and `sharedrive fetch` can then retrieve those nested resources normally.

Python:

```python
from pathlib import Path
from sharedrive.actions.fetch import fetch_from_descriptor

summary = fetch_from_descriptor(
    descriptor=Path("resources/descriptor.yaml"),
    include="all",
    output_dir=Path("resources"),
    dry_run=True,
)
print(summary)
```

## Docs site

```bash
uv run mkdocs serve
```

## GitHub-rendered markdown docs

To regenerate static Markdown pages that render directly on GitHub:

```bash
python scripts/update_docs_markdown.py
```
