# CLI Reference

Auto-generated from live `sharedrive --help` output.

## `sharedrive --help`

```text
Usage: sharedrive [OPTIONS] COMMAND [ARGS]...

 Shared drive utilities for SharePoint, Google Drive, and S3.

 Options
 --install-completion          Install completion for the current shell.
 --show-completion             Show completion for the current shell, to copy it or customize the installation.
 --help                        Show this message and exit.

 Commands
 gdrive                                       Google Drive commands.
 retrieve                                     Descriptor-driven retrieval commands.
 s3                                           S3 commands.
 sharepoint                                   SharePoint commands.
```

## `sharedrive retrieve --help`

```text
Usage: sharedrive retrieve [OPTIONS] COMMAND [ARGS]...

 Descriptor-driven retrieval commands.

 Options
 --help          Show this message and exit.

 Commands
 descriptor                   Copy resources from a descriptor; explicit alias for retrieve run.
 googledrive                  Copy only Google Drive-backed resources from a descriptor.
 run                          Copy resources from a descriptor and exit non-zero if any resource fails.
 s3                           Copy only S3-backed resources from a descriptor.
 sharepoint                   Copy only SharePoint-backed resources from a descriptor.
```

## `sharedrive retrieve run --help`

```text
Usage: sharedrive retrieve run [OPTIONS]

 Copy resources from a descriptor and exit non-zero if any resource fails.

 Options
 --descriptor                    PATH  Descriptor file path. [default: resources\descriptor.yaml]
 --include                       TEXT  One of: all, sharepoint, s3, googledrive [default: all]
 --output-dir                    PATH  Base output directory for relative resource paths. [default: resources]
 --dry-run       --no-dry-run          Print actions without downloading. [default: no-dry-run]
 --help                                Show this message and exit.


 **Examples**
 ```bash sharedrive retrieve run --dry-run ```
 ```bash sharedrive retrieve run --descriptor resources/descriptor.yaml --include all ```
 ```bash sharedrive retrieve run --include sharepoint --output-dir resources ```
```

## `sharedrive retrieve descriptor --help`

```text
Usage: sharedrive retrieve descriptor [OPTIONS]

 Copy resources from a descriptor; explicit alias for retrieve run.

 Options
 --descriptor                    PATH  Descriptor file path. [default: resources\descriptor.yaml]
 --include                       TEXT  One of: all, sharepoint, s3, googledrive [default: all]
 --output-dir                    PATH  Base output directory for relative resource paths. [default: resources]
 --dry-run       --no-dry-run          Print actions without downloading. [default: no-dry-run]
 --help                                Show this message and exit.


 **Examples**
 ```bash sharedrive retrieve descriptor --descriptor resources/descriptor.yaml ```
 ```bash sharedrive retrieve descriptor --include s3 --dry-run ```
```

## `sharedrive retrieve s3 --help`

```text
Usage: sharedrive retrieve s3 [OPTIONS]

 Copy only S3-backed resources from a descriptor.

 Options
 --descriptor                    PATH  Descriptor file path. [default: resources\descriptor.yaml]
 --output-dir                    PATH  Base output directory for relative resource paths. [default: resources]
 --dry-run       --no-dry-run          Print actions without downloading. [default: no-dry-run]
 --help                                Show this message and exit.


 **Examples**
 ```bash sharedrive retrieve s3 --descriptor resources/descriptor.yaml ```
 ```bash sharedrive retrieve s3 --output-dir resources/background --dry-run ```
```

## `sharedrive retrieve sharepoint --help`

```text
Usage: sharedrive retrieve sharepoint [OPTIONS]

 Copy only SharePoint-backed resources from a descriptor.

 Options
 --descriptor                    PATH  Descriptor file path. [default: resources\descriptor.yaml]
 --output-dir                    PATH  Base output directory for relative resource paths. [default: resources]
 --dry-run       --no-dry-run          Print actions without downloading. [default: no-dry-run]
 --help                                Show this message and exit.


 **Examples**
 ```bash sharedrive retrieve sharepoint --descriptor resources/descriptor.yaml ```
 ```bash sharedrive retrieve sharepoint --dry-run ```
```

## `sharedrive retrieve googledrive --help`

```text
Usage: sharedrive retrieve googledrive [OPTIONS]

 Copy only Google Drive-backed resources from a descriptor.

 Options
 --descriptor                    PATH  Descriptor file path. [default: resources\descriptor.yaml]
 --output-dir                    PATH  Base output directory for relative resource paths. [default: resources]
 --dry-run       --no-dry-run          Print actions without downloading. [default: no-dry-run]
 --help                                Show this message and exit.


 **Examples**
 ```bash sharedrive retrieve googledrive --descriptor resources/descriptor.yaml ```
 ```bash sharedrive retrieve googledrive --output-dir resources/background ```
```

## `sharedrive gdrive --help`

```text
Usage: sharedrive gdrive [OPTIONS] COMMAND [ARGS]...

 Google Drive commands.

 Options
 --help          Show this message and exit.

 Commands
 download            Download one Google Drive file and print the written local output path.
 export              Export a Google Workspace file and print output path or exported byte count.
 get                 Print JSON metadata for one Google Drive file resolved from an ID or web URL.
 list                Print JSON metadata for all files visible to the authenticated Google Drive client.
```

## `sharedrive gdrive list --help`

```text
Usage: sharedrive gdrive list [OPTIONS]

 Print JSON metadata for all files visible to the authenticated Google Drive client.

 Options
 --credentials-path        TEXT  Path to service account JSON; defaults to GOOGLE_APPLICATION_CREDENTIALS. [default: None]
 --help                          Show this message and exit.


 **Examples**
 ```bash sharedrive gdrive list ```
 ```bash sharedrive gdrive list --credentials-path ./secrets/google-service-account.json ```
```

## `sharedrive gdrive get --help`

```text
Usage: sharedrive gdrive get [OPTIONS] FILE_ID_OR_URL

 Print JSON metadata for one Google Drive file resolved from an ID or web URL.

 Arguments
 *    file_id_or_url      TEXT  Google file ID or web URL. [default: None] [required]

 Options
 --credentials-path        TEXT  Path to credentials JSON. [default: None]
 --help                          Show this message and exit.


 **Examples**
 ```bash sharedrive gdrive get 1lvWns43FFPerUjFpHPFfFnPLr-B-ERAqG83AVC4bpME ```
 ```bash sharedrive gdrive get https://docs.google.com/document/d/<id>/edit ```
```

## `sharedrive gdrive download --help`

```text
Usage: sharedrive gdrive download [OPTIONS] FILE_ID_OR_URL OUTPUT_PATH

 Download one Google Drive file and print the written local output path.

 Arguments
 *    file_id_or_url      TEXT  Google file ID or web URL. [default: None] [required]
 *    output_path         PATH  Local output path. [default: None] [required]

 Options
 --credentials-path        TEXT  Path to credentials JSON. [default: None]
 --help                          Show this message and exit.


 **Examples**
 ```bash sharedrive gdrive download 1lvWns43FFPerUjFpHPFfFnPLr-B-ERAqG83AVC4bpME resources/test.docx ```
 ```bash sharedrive gdrive download https://docs.google.com/document/d/<id>/edit resources/test.docx ```
```

## `sharedrive gdrive export --help`

```text
Usage: sharedrive gdrive export [OPTIONS] FILE_ID_OR_URL

 Export a Google Workspace file and print output path or exported byte count.

 Arguments
 *    file_id_or_url      TEXT  Google file ID or web URL. [default: None] [required]

 Options
 --mime-type               TEXT  Target export MIME type. [default: None]
 --output-path             PATH  Optional output path. [default: None]
 --credentials-path        TEXT  Path to credentials JSON. [default: None]
 --help                          Show this message and exit.


 **Examples**
 ```bash sharedrive gdrive export 1lvWns43FFPerUjFpHPFfFnPLr-B-ERAqG83AVC4bpME --mime-type application/pdf --output-path resources/test.pdf ```
 ```bash sharedrive gdrive export https://docs.google.com/spreadsheets/d/<id>/edit --mime-type text/csv ```
```

## `sharedrive sharepoint --help`

```text
Usage: sharedrive sharepoint [OPTIONS] COMMAND [ARGS]...

 SharePoint commands.

 Options
 --help          Show this message and exit.

 Commands
 download             Download one SharePoint file to disk and print the local path when not dry-run.
 get                  Print JSON metadata for a SharePoint file or folder URL.
```

## `sharedrive sharepoint get --help`

```text
Usage: sharedrive sharepoint get [OPTIONS] URL

 Print JSON metadata for a SharePoint file or folder URL.

 Arguments
 *    url      TEXT  SharePoint URL. [default: None] [required]

 Options
 --help          Show this message and exit.


 **Examples**
 ```bash sharedrive sharepoint get https://norc.sharepoint.com/sites/MySite/Shared%20Documents/path/file.xlsx ```
```

## `sharedrive sharepoint download --help`

```text
Usage: sharedrive sharepoint download [OPTIONS] URL OUTPUT_PATH

 Download one SharePoint file to disk and print the local path when not dry-run.

 Arguments
 *    url              TEXT  SharePoint URL. [default: None] [required]
 *    output_path      PATH  Local output path. [default: None] [required]

 Options
 --dry-run    --no-dry-run      Print action only. [default: no-dry-run]
 --help                         Show this message and exit.


 **Examples**
 ```bash sharedrive sharepoint download https://norc.sharepoint.com/sites/MySite/Shared%20Documents/path/file.xlsx resources/file.xlsx ```
 ```bash sharedrive sharepoint download https://norc.sharepoint.com/sites/MySite/Shared%20Documents/path/file.xlsx resources/file.xlsx --dry-run ```
```

## `sharedrive s3 --help`

```text
Usage: sharedrive s3 [OPTIONS] COMMAND [ARGS]...

 S3 commands.

 Options
 --help          Show this message and exit.

 Commands
 cat        Print text contents of an S3 object decoded with the selected encoding.
 cp         Copy one S3 object to a local path and print the local file path when written.
 ls         List entries under an S3 prefix and print one path per line.
```

## `sharedrive s3 cp --help`

```text
Usage: sharedrive s3 cp [OPTIONS] SOURCE_URL OUTPUT_PATH

 Copy one S3 object to a local path and print the local file path when written.

 Arguments
 *    source_url       TEXT  S3 URL (s3://bucket/key or compatible HTTPS). [default: None] [required]
 *    output_path      PATH  Local output path. [default: None] [required]

 Options
 --dry-run            --no-dry-run              Print action only. [default: no-dry-run]
 --no-cloudpathlib    --no-no-cloudpathlib      Disable cloudpathlib and use boto3 download fallback. [default: no-no-cloudpathlib]
 --help                                         Show this message and exit.


 **Examples**
 ```bash sharedrive s3 cp s3://my-bucket/path/file.csv resources/file.csv ```
 ```bash sharedrive s3 cp https://s3.amazonaws.com/my-bucket/path/file.csv resources/file.csv --no-cloudpathlib ```
```

## `sharedrive s3 ls --help`

```text
Usage: sharedrive s3 ls [OPTIONS] SOURCE_URL

 List entries under an S3 prefix and print one path per line.

 Arguments
 *    source_url      TEXT  S3 URL prefix. [default: None] [required]

 Options
 --help          Show this message and exit.


 **Examples**
 ```bash sharedrive s3 ls s3://my-bucket/path/ ```
```

## `sharedrive s3 cat --help`

```text
Usage: sharedrive s3 cat [OPTIONS] SOURCE_URL

 Print text contents of an S3 object decoded with the selected encoding.

 Arguments
 *    source_url      TEXT  S3 object URL. [default: None] [required]

 Options
 --encoding        TEXT  Text encoding for output. [default: utf-8]
 --help                  Show this message and exit.


 **Examples**
 ```bash sharedrive s3 cat s3://my-bucket/path/file.txt ```
 ```bash sharedrive s3 cat s3://my-bucket/path/file.json --encoding utf-8 ```
```
