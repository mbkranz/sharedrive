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
  fetch       Fetch descriptor resources by adapter type or resource name...
  gdrive      Google Drive commands.
  sharepoint  SharePoint commands.
  spo         SharePoint commands.
  s3          S3 commands.
```

## `sharedrive fetch --help`

```text
Usage: sharedrive fetch [OPTIONS] DESCRIPTOR

  Fetch descriptor resources by adapter type or resource name filters.

Arguments:
  DESCRIPTOR  Descriptor file path.  [required]

Options:
  -i, --include TEXT        Include adapter types and/or resource names. Repeat
                            the option or pass a comma-separated list.
  --output-dir PATH         Base output directory for relative resource paths.
                            [default: resources]
  --dry-run / --no-dry-run  Print actions without downloading.  [default: no-
                            dry-run]
  --env-file PATH           Path to .env file for credentials. Defaults to .env
                            in the current directory.
  --help                    Show this message and exit.

  **Examples**

  ```bash

  sharedrive fetch resources/descriptor.yaml --dry-run

  ```

  ```bash

  sharedrive fetch resources/descriptor.yaml --include s3 --include sharepoint

  ```

  ```bash

  sharedrive fetch resources/descriptor.yaml --include spec-workbook --output-
  dir resources

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

  SharePoint commands.

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

  SharePoint commands.

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
