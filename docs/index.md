# sharedrive

Shared-drive adapters and retrieval workflows for SharePoint, Google Drive, and S3.

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

## Retrieval

CLI:

```bash
sharedrive retrieve resources/descriptor.yaml --dry-run
```

Python:

```python
from pathlib import Path
from sharedrive.retrieve import retrieve_from_descriptor

summary = retrieve_from_descriptor(
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
