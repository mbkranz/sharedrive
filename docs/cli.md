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
  update    Update descriptor-root or resource properties using flag-style...
  checkout  Activate a descriptor for later commands.
  set       Set reusable key/value parameters for sharedrive descriptor...
  add       Add a resource entry to a descriptor.
  fetch     Fetch remote metadata for one resource into the descriptor.
  download  Download descriptor resources by adapter type or resource name...
  auth      Authentication helpers.
  clone     Clone descriptor state for new local variants.
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
  --package           Treat as a package (creates a resource with nested resources).
  --catalog           Treat as a catalog (alias for package, future extension).
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

  sharedrive add census-docs --package --path downloads/census --source \
  https://drive.google.com/drive/folders/<id> --service-type GoogleDrive \
  --entity-type Directory

  ```
```

## `sharedrive fetch --help`

```text
Usage: sharedrive fetch [OPTIONS] [RESOURCE_NAME]

  Fetch remote metadata for one resource into the descriptor.

Arguments:
  [RESOURCE_NAME]  Top-level resource name whose metadata should be refreshed.

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
Usage: sharedrive download [OPTIONS] [DESCRIPTOR_ARG]

  Download descriptor resources by adapter type or resource name filters.

Arguments:
  [DESCRIPTOR_ARG]  Descriptor file path. Defaults to the saved descriptor or
                    the first standard descriptor path.

Options:
  --descriptor PATH         Descriptor file path. Defaults to the saved
                            descriptor or the first standard descriptor path.
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
