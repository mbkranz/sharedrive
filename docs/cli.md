# CLI Reference

Auto-generated from live `sharedrive --help` output.

## `sharedrive --help`

```text
Usage: sharedrive [OPTIONS] COMMAND [ARGS]...

  Shared drive utilities for SharePoint, Google Drive, and S3.

Options:
  --install-completion  Install completion for the current shell.
  --show-completion     Show completion for the current shell, to copy it or
                        customize the installation.
  --help                Show this message and exit.

Commands:
  update      Update descriptor-root or resource properties using...
  checkout    Activate a descriptor for later commands.
  set         Set reusable key/value parameters for sharedrive descriptor...
  add         Add a resource entry to a descriptor.
  fetch       Fetch remote metadata for one resource into the descriptor.
  download    Download descriptor resources by adapter type or resource...
  auth        Authentication helpers.
  clone       Clone descriptor state for new local variants.
  gdrive      Google Drive commands.
  sharepoint  SharePoint commands (`spo` is alias for `sharepoint`).
  spo         SharePoint commands (`spo` is alias for `sharepoint`).
  s3          S3 commands.
```

## `sharedrive auth --help`

```text
Usage: sharedrive auth [OPTIONS] COMMAND [ARGS]...

  Authentication helpers.

Options:
  --help  Show this message and exit.

Commands:
  check  Validate credentials for the adapters selected by a descriptor.
  login  Interactive login commands.
```

## `sharedrive auth check --help`

```text
Usage: sharedrive auth check [OPTIONS] [DESCRIPTOR]

  Validate credentials for the adapters selected by a descriptor.

Arguments:
  [DESCRIPTOR]  Descriptor file path. Defaults to the saved descriptor or the
                first standard descriptor path.

Options:
  -i, --include TEXT    Include adapter types and/or resource names. Repeat the
                        option or pass a comma-separated list.
  --format [text|json]  Output format.  [default: text]
  --env-file PATH       Path to .env file for credentials. Defaults to .env in
                        the current directory.
  --help                Show this message and exit.

  **Examples**

  ```bash

  sharedrive auth check resources/descriptor.yaml

  ```

  ```bash

  sharedrive auth check resources/descriptor.yaml --include sharepoint

  ```

  ```bash

  sharedrive auth check resources/descriptor.yaml --format json

  ```
```

## `sharedrive auth login --help`

```text
Usage: sharedrive auth login [OPTIONS] COMMAND [ARGS]...

  Interactive login commands.

Options:
  --help  Show this message and exit.

Commands:
  gdrive      Run the Google installed-app OAuth flow and optionally...
  microsoft   Validate Microsoft authentication used by SharePoint workflows.
  sharepoint  Validate SharePoint authentication using the configured auth...
```

## `sharedrive auth login gdrive --help`

```text
Usage: sharedrive auth login gdrive [OPTIONS]

  Run the Google installed-app OAuth flow and optionally persist a token.

  Sample .env for using Google user OAuth with descriptor-based commands such as
  ``sharedrive fetch`` and ``sharedrive download``:

  ```env GOOGLE_AUTH_MODE=user_oauth #
  GOOGLE_APPLICATION_CREDENTIALS=.google/service-account.json #
  GOOGLE_SERVICE_ACCOUNT_CREDENTIALS=.google/service-account.json
  GOOGLE_OAUTH_CREDENTIALS=.google/oauth-credentials.json
  GOOGLE_SCOPES=https://www.googleapis.com/auth/drive
  GOOGLE_OAUTH_USE_LOCAL_SERVER=true GOOGLE_OAUTH_TOKEN_PATH=.google/oauth-
  token.json ```

Options:
  --oauth-client-secrets PATH  Path to Google OAuth client secrets JSON.
  --oauth-token-path PATH      Path to persist the authorized-user token JSON.
  --scope TEXT                 OAuth scope. Repeat for multiple scopes.
  --no-local-server            Use the console flow instead of a local callback
                               server.
  --env-file PATH              Path to .env file for credentials. Defaults to
                               .env in the current directory.
  --help                       Show this message and exit.

  **Examples**

  ```bash

  sharedrive auth login gdrive --oauth-client-secrets .google/oauth-
  credentials.json --oauth-token-path .google/oauth-token.json

  ```

  ```bash

  sharedrive auth login gdrive --scope
  https://www.googleapis.com/auth/drive.readonly

  ```
```

## `sharedrive auth login microsoft --help`

```text
Usage: sharedrive auth login microsoft [OPTIONS]

  Validate Microsoft authentication used by SharePoint workflows.

Options:
  --auth-mode TEXT  Microsoft auth mode: app_only or delegated.
  --host-url TEXT   SharePoint host for validating Graph-backed access, for
                    example norc.sharepoint.com.
  --scope TEXT      Microsoft Graph scope. Repeat for multiple scopes.
  --env-file PATH   Path to .env file for credentials. Defaults to .env in the
                    current directory.
  --help            Show this message and exit.

  **Examples**

  ```bash

  sharedrive auth login microsoft

  ```

  ```bash

  sharedrive auth login microsoft --auth-mode delegated

  ```

  ```bash

  sharedrive auth login microsoft --host-url norc.sharepoint.com

  ```
```

## `sharedrive auth login sharepoint --help`

```text
Usage: sharedrive auth login sharepoint [OPTIONS]

  Validate SharePoint authentication using the configured auth mode.

Options:
  --auth-mode TEXT  Microsoft auth mode for SharePoint: app_only or delegated.
  --host-url TEXT   SharePoint host, for example norc.sharepoint.com.
  --scope TEXT      Microsoft Graph scope. Repeat for multiple scopes.
  --env-file PATH   Path to .env file for credentials. Defaults to .env in the
                    current directory.
  --help            Show this message and exit.

  **Examples**

  ```bash

  sharedrive auth login sharepoint

  ```

  ```bash

  sharedrive auth login sharepoint --auth-mode delegated

  ```

  ```bash

  sharedrive auth login sharepoint --host-url norc.sharepoint.com

  ```
```

## `sharedrive checkout --help`

```text
Usage: sharedrive checkout [OPTIONS] DESCRIPTOR

  Activate a descriptor for later commands.

Arguments:
  DESCRIPTOR  Descriptor path to activate for later commands.  [required]

Options:
  --help  Show this message and exit.

  **Examples**

  ```bash

  sharedrive checkout resources/descriptor.yaml

  ```
```

## `sharedrive set --help`

```text
Usage: sharedrive set [OPTIONS] [DESCRIPTOR_SCOPE]

  Set reusable key/value parameters for sharedrive descriptor workflows.

Arguments:
  [DESCRIPTOR_SCOPE]  Descriptor path to save defaults for.

Options:
  --global           Save params as global defaults for all descriptors.
  --descriptor TEXT  Default descriptor path to save.
  --output-dir TEXT  Default output directory to save.
  --help             Show this message and exit.

  **Examples**

  ```bash

  sharedrive set --global --descriptor resources/descriptor.yaml

  ```

  ```bash

  sharedrive set --global --output-dir resources

  ```

  ```bash

  sharedrive set resources/descriptor.yaml --output-dir exports

  ```
```

## `sharedrive add --help`

```text
Usage: sharedrive add [OPTIONS] NAME

  Add a resource entry to a descriptor.

Arguments:
  NAME  Resource name to store in the descriptor.  [required]

Options:
  --path TEXT          Resource path stored in the descriptor.  [required]
  --source TEXT        Source URL/URI/path for the resource.  [required]
  --title TEXT         Optional resource title.
  --description TEXT   Optional resource description.
  --service-type TEXT  Source serviceType. If omitted, infer from source.
  --entity-type TEXT   Source entityType such as File, Directory, or Container.
  --sync-target TEXT   Descriptor syncTarget: 'path' or 'resources'.
  --profile TEXT       Optional metadata profile for the resource.
  --descriptor PATH    Descriptor file path. Defaults to the saved descriptor or
                       the first standard descriptor path.
  --help               Show this message and exit.

  **Examples**

  ```bash

  sharedrive add spec-workbook --path background/specs/spec-workbook.xlsx
  --source https://tenant.sharepoint.com/sites/Test/Shared%20Documents/spec.xlsx

  ```

  ```bash

  sharedrive add source-export --path background/exports/source-export.csv
  --source s3://my-bucket/source-export.csv --service-type S3

  ```

  ```bash

  sharedrive add census-docs --path downloads/census --source
  https://drive.google.com/drive/folders/<id> --service-type GoogleDrive
  --entity-type Directory --sync-target resources

  ```
```

## `sharedrive fetch --help`

```text
Usage: sharedrive fetch [OPTIONS] RESOURCE_NAME

  Fetch remote metadata for one resource into the descriptor.

Arguments:
  RESOURCE_NAME  Top-level resource name whose metadata should be refreshed.
                 [required]

Options:
  --descriptor PATH         Descriptor file path. Defaults to the saved
                            descriptor or the first standard descriptor path.
  --dry-run / --no-dry-run  Preview descriptor changes without writing them.
                            [default: no-dry-run]
  --env-file PATH           Path to .env file for credentials. Defaults to .env
                            in the current directory.
  --help                    Show this message and exit.

  **Examples**

  ```bash

  sharedrive fetch census-package --descriptor resources/descriptor.yaml --dry-
  run

  ```

  ```bash

  sharedrive fetch census-package --descriptor resources/descriptor.yaml

  ```
```

## `sharedrive download --help`

```text
Usage: sharedrive download [OPTIONS] [DESCRIPTOR]

  Download descriptor resources by adapter type or resource name filters.

Arguments:
  [DESCRIPTOR]  Descriptor file path. Defaults to the saved descriptor or the
                first standard descriptor path.

Options:
  -i, --include TEXT        Include adapter types and/or resource names. Repeat
                            the option or pass a comma-separated list.
  --output-dir PATH         Base output directory for relative resource paths.
  --dry-run / --no-dry-run  Print actions without downloading.  [default: no-
                            dry-run]
  --check-auth              Validate service credentials before downloading.
  --env-file PATH           Path to .env file for credentials. Defaults to .env
                            in the current directory.
  --help                    Show this message and exit.

  **Examples**

  ```bash

  sharedrive download resources/descriptor.yaml --dry-run

  ```

  ```bash

  sharedrive download resources/descriptor.yaml --include s3 --include
  sharepoint

  ```

  ```bash

  sharedrive download resources/descriptor.yaml --include spec-workbook
  --output-dir resources

  ```
```

## `sharedrive update --help`

```text
Usage: sharedrive update [OPTIONS]

  Update descriptor-root or resource properties using flag-style field edits.

Options:
  --descriptor PATH  Descriptor file path. Defaults to the saved descriptor or
                     the first standard descriptor path.
  --resource TEXT    Exact resource name or dot-path to update.
  --dry-run          Show what would be updated without writing files.
  --help             Show this message and exit.

  **Examples**

  ```bash

  sharedrive update --title "Hello" --description "hello"

  ```

  ```bash

  sharedrive update --resource file1 --title "Hello" --description "hello"

  ```

  ```bash

  sharedrive update --descriptor resources/descriptor.yaml --resource file1
  --title "Hello"

  ```
```

## `sharedrive gdrive --help`

```text
Usage: sharedrive gdrive [OPTIONS] COMMAND [ARGS]...

  Google Drive commands.

Options:
  --help  Show this message and exit.

Commands:
  list      Print JSON metadata for all files visible to the authenticated...
  get       Print JSON metadata for one Google Drive file resolved from an...
  download  Download one Google Drive file and print the written local...
  export    Export a Google Workspace file and print output path or...
```

## `sharedrive gdrive list --help`

```text
Usage: sharedrive gdrive list [OPTIONS]

  Print JSON metadata for all files visible to the authenticated Google Drive
  client.

Options:
  --credentials-path TEXT  Path to service account JSON; defaults to
                           GOOGLE_APPLICATION_CREDENTIALS.
  --help                   Show this message and exit.

  **Examples**

  ```bash

  sharedrive gdrive list

  ```

  ```bash

  sharedrive gdrive list --credentials-path ./secrets/google-service-
  account.json

  ```
```

## `sharedrive gdrive get --help`

```text
Usage: sharedrive gdrive get [OPTIONS] FILE_ID_OR_URL

  Print JSON metadata for one Google Drive file resolved from an ID or web URL.

Arguments:
  FILE_ID_OR_URL  Google file ID or web URL.  [required]

Options:
  --credentials-path TEXT  Path to credentials JSON.
  --help                   Show this message and exit.

  **Examples**

  ```bash

  sharedrive gdrive get 1lvWns43FFPerUjFpHPFfFnPLr-B-ERAqG83AVC4bpME

  ```

  ```bash

  sharedrive gdrive get https://docs.google.com/document/d/<id>/edit

  ```
```

## `sharedrive gdrive download --help`

```text
Usage: sharedrive gdrive download [OPTIONS] FILE_ID_OR_URL OUTPUT_PATH

  Download one Google Drive file and print the written local output path.

Arguments:
  FILE_ID_OR_URL  Google file ID or web URL.  [required]
  OUTPUT_PATH     Local output path.  [required]

Options:
  --credentials-path TEXT  Path to credentials JSON.
  --help                   Show this message and exit.

  **Examples**

  ```bash

  sharedrive gdrive download 1lvWns43FFPerUjFpHPFfFnPLr-B-ERAqG83AVC4bpME
  resources/test.docx

  ```

  ```bash

  sharedrive gdrive download https://docs.google.com/document/d/<id>/edit
  resources/test.docx

  ```
```

## `sharedrive gdrive export --help`

```text
Usage: sharedrive gdrive export [OPTIONS] FILE_ID_OR_URL

  Export a Google Workspace file and print output path or exported byte count.

Arguments:
  FILE_ID_OR_URL  Google file ID or web URL.  [required]

Options:
  --mime-type TEXT         Target export MIME type.
  --output-path PATH       Optional output path.
  --credentials-path TEXT  Path to credentials JSON.
  --help                   Show this message and exit.

  **Examples**

  ```bash

  sharedrive gdrive export 1lvWns43FFPerUjFpHPFfFnPLr-B-ERAqG83AVC4bpME --mime-
  type application/pdf --output-path resources/test.pdf

  ```

  ```bash

  sharedrive gdrive export https://docs.google.com/spreadsheets/d/<id>/edit
  --mime-type text/csv

  ```
```

## `sharedrive sharepoint --help`

```text
Usage: sharedrive sharepoint [OPTIONS] COMMAND [ARGS]...

  SharePoint commands (`spo` is alias for `sharepoint`).

Options:
  --help  Show this message and exit.

Commands:
  get       Print JSON metadata for a SharePoint file or folder URL.
  download  Download one SharePoint file to disk and print the local path...
```

## `sharedrive sharepoint get --help`

```text
Usage: sharedrive sharepoint get [OPTIONS] URL

  Print JSON metadata for a SharePoint file or folder URL.

Arguments:
  URL  SharePoint URL.  [required]

Options:
  --help  Show this message and exit.

  **Examples**

  ```bash

  sharedrive sharepoint get
  https://norc.sharepoint.com/sites/MySite/Shared%20Documents/path/file.xlsx

  ```

  ```bash

  sharedrive spo get
  https://norc.sharepoint.com/sites/MySite/Shared%20Documents/path/file.xlsx

  ```
```

## `sharedrive sharepoint download --help`

```text
Usage: sharedrive sharepoint download [OPTIONS] URL OUTPUT_PATH

  Download one SharePoint file to disk and print the local path when not dry-
  run.

Arguments:
  URL          SharePoint URL.  [required]
  OUTPUT_PATH  Local output path.  [required]

Options:
  --dry-run / --no-dry-run  Print action only.  [default: no-dry-run]
  --help                    Show this message and exit.

  **Examples**

  ```bash

  sharedrive sharepoint download
  https://norc.sharepoint.com/sites/MySite/Shared%20Documents/path/file.xlsx
  resources/file.xlsx

  ```

  ```bash

  sharedrive sharepoint download
  https://norc.sharepoint.com/sites/MySite/Shared%20Documents/path/file.xlsx
  resources/file.xlsx --dry-run

  ```

  ```bash

  sharedrive spo download
  https://norc.sharepoint.com/sites/MySite/Shared%20Documents/path/file.xlsx
  resources/file.xlsx

  ```

  ```bash

  sharedrive spo download
  https://norc.sharepoint.com/sites/MySite/Shared%20Documents/path/file.xlsx
  resources/file.xlsx --dry-run

  ```
```

## `sharedrive spo --help`

```text
Usage: sharedrive spo [OPTIONS] COMMAND [ARGS]...

  SharePoint commands (`spo` is alias for `sharepoint`).

Options:
  --help  Show this message and exit.

Commands:
  get       Print JSON metadata for a SharePoint file or folder URL.
  download  Download one SharePoint file to disk and print the local path...
```

## `sharedrive spo get --help`

```text
Usage: sharedrive spo get [OPTIONS] URL

  Print JSON metadata for a SharePoint file or folder URL.

Arguments:
  URL  SharePoint URL.  [required]

Options:
  --help  Show this message and exit.

  **Examples**

  ```bash

  sharedrive sharepoint get
  https://norc.sharepoint.com/sites/MySite/Shared%20Documents/path/file.xlsx

  ```

  ```bash

  sharedrive spo get
  https://norc.sharepoint.com/sites/MySite/Shared%20Documents/path/file.xlsx

  ```
```

## `sharedrive spo download --help`

```text
Usage: sharedrive spo download [OPTIONS] URL OUTPUT_PATH

  Download one SharePoint file to disk and print the local path when not dry-
  run.

Arguments:
  URL          SharePoint URL.  [required]
  OUTPUT_PATH  Local output path.  [required]

Options:
  --dry-run / --no-dry-run  Print action only.  [default: no-dry-run]
  --help                    Show this message and exit.

  **Examples**

  ```bash

  sharedrive sharepoint download
  https://norc.sharepoint.com/sites/MySite/Shared%20Documents/path/file.xlsx
  resources/file.xlsx

  ```

  ```bash

  sharedrive sharepoint download
  https://norc.sharepoint.com/sites/MySite/Shared%20Documents/path/file.xlsx
  resources/file.xlsx --dry-run

  ```

  ```bash

  sharedrive spo download
  https://norc.sharepoint.com/sites/MySite/Shared%20Documents/path/file.xlsx
  resources/file.xlsx

  ```

  ```bash

  sharedrive spo download
  https://norc.sharepoint.com/sites/MySite/Shared%20Documents/path/file.xlsx
  resources/file.xlsx --dry-run

  ```
```

## `sharedrive s3 --help`

```text
Usage: sharedrive s3 [OPTIONS] COMMAND [ARGS]...

  S3 commands.

Options:
  --help  Show this message and exit.

Commands:
  cp   Copy one S3 object to a local path and print the local file path...
  ls   List entries under an S3 prefix and print one path per line.
  cat  Print text contents of an S3 object decoded with the selected encoding.
```

## `sharedrive s3 cp --help`

```text
Usage: sharedrive s3 cp [OPTIONS] SOURCE_URL OUTPUT_PATH

  Copy one S3 object to a local path and print the local file path when written.

Arguments:
  SOURCE_URL   S3 URL (s3://bucket/key or compatible HTTPS).  [required]
  OUTPUT_PATH  Local output path.  [required]

Options:
  --dry-run / --no-dry-run        Print action only.  [default: no-dry-run]
  --no-cloudpathlib / --no-no-cloudpathlib
                                  Disable cloudpathlib and use boto3 download
                                  fallback.  [default: no-no-cloudpathlib]
  --help                          Show this message and exit.

  **Examples**

  ```bash

  sharedrive s3 cp s3://my-bucket/path/file.csv resources/file.csv

  ```

  ```bash

  sharedrive s3 cp https://s3.amazonaws.com/my-bucket/path/file.csv
  resources/file.csv --no-cloudpathlib

  ```
```

## `sharedrive s3 ls --help`

```text
Usage: sharedrive s3 ls [OPTIONS] SOURCE_URL

  List entries under an S3 prefix and print one path per line.

Arguments:
  SOURCE_URL  S3 URL prefix.  [required]

Options:
  --help  Show this message and exit.

  **Examples**

  ```bash

  sharedrive s3 ls s3://my-bucket/path/

  ```
```

## `sharedrive s3 cat --help`

```text
Usage: sharedrive s3 cat [OPTIONS] SOURCE_URL

  Print text contents of an S3 object decoded with the selected encoding.

Arguments:
  SOURCE_URL  S3 object URL.  [required]

Options:
  --encoding TEXT  Text encoding for output.  [default: utf-8]
  --help           Show this message and exit.

  **Examples**

  ```bash

  sharedrive s3 cat s3://my-bucket/path/file.txt

  ```

  ```bash

  sharedrive s3 cat s3://my-bucket/path/file.json --encoding utf-8

  ```
```
