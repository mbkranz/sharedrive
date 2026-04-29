# sharedrive

Shared-drive adapters and retrieval workflows for SharePoint, Google Drive, and S3.

## Architecture

`sharedrive` is organized as a layered adapter-oriented application.

- Descriptor models in `sharedrive/models.py` are the persisted metadata layer. They validate and normalize descriptor documents stored on disk.
- Runtime items in `sharedrive/item.py` are live remote objects for files and folders. They expose runtime behavior such as `refresh()`, `download()`, `children`, and `iter_files()`.
- Clients in `sharedrive/clients/*.py` talk to provider APIs and build runtime items from Google Drive or SharePoint metadata.
- Actions in `sharedrive/actions/*.py` orchestrate workflows over descriptors and runtime items. This is where descriptor fetch, sync, and download flows live.
- The CLI in `sharedrive/cli.py` is the outer layer that resolves defaults and invokes the action layer.

The key boundary is that descriptor models are persisted metadata, while runtime items are live adapter-backed state. Action modules bridge those two worlds.


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
sharedrive fetch census-package --descriptor resources/descriptor.yaml --dry-run
```

## Package resources

`sharedrive` now supports folder-backed package resources in descriptors. A package resource is a top-level descriptor resource with a package profile, a local root `path`, and a remote folder source. `sharedrive sync <package-name>` can populate that package with nested file resources from Google Drive, and `sharedrive fetch <package-name>` can refresh the nested descriptor resources from the remote folder.

Python:

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

Runtime items use `refresh()` to reload remote state in memory and `refresh_tree()` to hydrate an entire folder subtree before traversal. Descriptor metadata updates remain action-level operations such as `fetch()`.

## Docs site

```bash
uv run mkdocs serve
```

## GitHub-rendered markdown docs

To regenerate static Markdown pages that render directly on GitHub:

```bash
uv run python scripts/update_docs_markdown.py
```
