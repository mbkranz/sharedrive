# sharedrive

Experimental connectors and scripts for moving files across SharePoint, Google Drive, and S3 using a descriptor-driven workflow.

## Current scope

- `sharedrive/sharepoint.py`: Microsoft Graph SharePoint client (`SharepointClient`)
- `sharedrive/googledrive.py`: Google Drive client (`GoogleDriveClient`)
- `scripts/retrieve_resources.py`: pulls resources from descriptor entries (SharePoint + S3 today)
- `scripts/dev_adapters.py`: manual smoke-test script for adapter development

## Lineage and compatibility

This repo is currently aligned with prior `pmd-utils` usage patterns in the All of Us repos:

- `scripts/retrieve_resources.py` matches `allofus/ppsc-participant-tracks/scripts/retrieve_resources.py`
- `scripts/dev_adapters.py` matches `allofus/ppsc-pmd-utils/scripts/dev/dev_adapters.py`
- downstream repos that still import `pmd_utils.io.adapters.*` include:
  - `allofus/ppsc-participant-tracks`
  - `allofus/ppsc-salesforce`
  - `allofus/aou-qualtrics-specs-poc`

Important: the development scripts still import adapters from the `pmd_utils` namespace. Keep this in mind when wiring environments.

## Setup

### 1. Create environment

Using `uv`:

```bash
uv sync
```

Using `pip`:

```bash
pip install -e ".[dev,test]"
```

### 2. Configure secrets

```bash
cp .env-sample .env
```

Set values for:

- `AZURE_TENANT_ID`
- `AZURE_CLIENT_ID`
- `AZURE_CLIENT_SECRET`
- `GOOGLE_APPLICATION_CREDENTIALS`
- AWS credentials (if running S3 retrieval through `boto3`)

## Descriptor-driven retrieval

Run a dry-run first:

```bash
python scripts/retrieve_resources.py --dry-run
```

Typical runs:

```bash
python scripts/retrieve_resources.py --include all
python scripts/retrieve_resources.py --include sharepoint
python scripts/retrieve_resources.py --include s3 --descriptor resources/descriptor.yaml
```

### Descriptor format

`scripts/retrieve_resources.py` expects a top-level object with `resources`:

```yaml
resources:
  - name: spec-workbook
    path: background/specs/spec-workbook.xlsx
    x-adapter: sharepoint
    sources:
      - path: https://norc.sharepoint.com/sites/....

  - name: source-export
    path: background/exports/source-export.csv
    x-adapter: s3
    sources:
      - path: s3://my-bucket/path/to/source-export.csv
```

Behavior notes:

- `path` is required and is resolved under `--output-dir` unless absolute.
- source URL can be from `sources[0].path` (preferred) or legacy `source`.
- adapter resolution uses `x-adapter` first, then URL inference:
  - SharePoint host -> `sharepoint`
  - `s3://` or S3 HTTP URL -> `s3`

## Adapter smoke testing

`scripts/dev_adapters.py` is a manual integration/dev script. It contains real-style example operations (get/download/update) and is not a unit test.

Use carefully:

- it can perform writes (`update_file`)
- it uses hard-coded file IDs as examples

## Known gaps

- `sharedrive/cli.py` and `sharedrive/app.py` are currently placeholders.
- test suite scaffolding exists, but there are no committed tests yet.
- retrieve script include choices contain legacy values (`background`, `output`) while adapter filtering currently behaves by adapter type (`sharepoint`, `s3`, `all`).

## Repository layout

```text
sharedrive/
  resources/
    descriptor.yaml
  scripts/
    dev_adapters.py
    retrieve_resources.py
  sharedrive/
    sharepoint.py
    googledrive.py
    cli.py
    app.py
  tests/
```
