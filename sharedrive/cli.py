
from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import typer
from dotenv import find_dotenv, load_dotenv

from sharedrive.aws import download_s3_url
from sharedrive.actions.fetch import check_auth_for_descriptor, fetch_from_descriptor

try:
    from cloudpathlib import S3Path
except ImportError:  # pragma: no cover
    S3Path = None

if TYPE_CHECKING:  # pragma: no cover
    from sharedrive.clients.google import GoogleDriveClient
    from sharedrive.clients.sharepoint import SharepointClient

load_dotenv(find_dotenv(usecwd=True))

app = typer.Typer(
    name="sharedrive",
    help="Shared drive utilities for SharePoint, Google Drive, and S3.",
    rich_markup_mode="markdown",
)
auth_app = typer.Typer(
    help="Authentication helpers.",
    rich_markup_mode="markdown",
)
auth_login_app = typer.Typer(
    help="Interactive login commands.",
    rich_markup_mode="markdown",
)
gdrive_app = typer.Typer(
    help="Google Drive commands.",
    rich_markup_mode="markdown",
)
sharepoint_app = typer.Typer(
    help="SharePoint commands.",
    rich_markup_mode="markdown",
)
s3_app = typer.Typer(
    help="S3 commands.",
    rich_markup_mode="markdown",
)
app.add_typer(auth_app, name="auth")
auth_app.add_typer(auth_login_app, name="login")
app.add_typer(gdrive_app, name="gdrive")
app.add_typer(sharepoint_app, name="sharepoint")
app.add_typer(sharepoint_app, name="spo")
app.add_typer(s3_app, name="s3")


class OutputFormat(str, Enum):
    TEXT = "text"
    JSON = "json"


def _examples_epilog(*lines: str) -> str:
    codeblocks = "\n\n".join(f"```bash\n\n\n{line.strip()}\n\n\n```" for line in lines)
    return f"\n\n**Examples**\n\n\n{codeblocks}"


def _echo_json(payload: Any) -> None:
    typer.echo(json.dumps(payload, indent=2, default=str))


def _load_env_file(env_file: Optional[Path]) -> None:
    if env_file is not None:
        load_dotenv(str(env_file), override=True)


def _make_sharepoint_client() -> SharepointClient:
    from sharedrive.auth.settings import make_sharepoint_client_from_microsoft_auth

    return make_sharepoint_client_from_microsoft_auth()


def _run_microsoft_login(
    auth_mode: Optional[str],
    host_url: Optional[str],
    scope: Optional[list[str]],
    env_file: Optional[Path],
) -> None:
    from sharedrive.auth.settings import MicrosoftAuthConfig, MicrosoftAuthMode

    _load_env_file(env_file)

    config_kwargs: dict[str, Any] = {}
    if auth_mode is not None:
        config_kwargs["auth_mode"] = MicrosoftAuthMode(auth_mode)
    if host_url is not None:
        config_kwargs["host_url"] = host_url
    if scope is not None:
        config_kwargs["scopes"] = scope

    config = MicrosoftAuthConfig(**config_kwargs)
    config.to_strategy().build()
    typer.echo(
        f"Microsoft login succeeded using {config.auth_mode.value} mode for {config.host_url}"
    )


def _make_gdrive_client(credentials_path: Optional[str], scope: Optional[list[str]] = None) -> GoogleDriveClient:
    from sharedrive.auth.google import default_drive_strategy
    from sharedrive.clients.google import GoogleDriveClient

    if not credentials_path and _has_google_settings_configured():
        return _make_gdrive_client_from_settings(scope)

    path = credentials_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    return GoogleDriveClient(
        credential_strategy=default_drive_strategy(credentials_path=path, scopes=scope)
    )


def _make_gdrive_client_from_settings(scope: Optional[list[str]] = None) -> GoogleDriveClient:
    from sharedrive.auth.settings import GoogleAuthConfig, make_google_drive_client_from_settings

    if scope is None:
        return make_google_drive_client_from_settings()

    return make_google_drive_client_from_settings(GoogleAuthConfig(scopes=scope))


def _has_google_settings_configured() -> bool:
    return any(
        os.getenv(name)
        for name in (
            "GOOGLE_AUTH_MODE",
            "GOOGLE_SERVICE_ACCOUNT_CREDENTIALS",
            "GOOGLE_OAUTH_CREDENTIALS",
            "GOOGLE_OAUTH_TOKEN_PATH",
            "GOOGLE_SCOPES",
            "GOOGLE_OAUTH_USE_LOCAL_SERVER",
        )
    )


def _parse_include_values(values: list[str] | None) -> str | list[str]:
    if not values:
        return "all"
    tokens: list[str] = []
    for value in values:
        tokens.extend(part.strip() for part in value.split(","))
    normalized = [token for token in tokens if token]
    if not normalized or "all" in {token.lower() for token in normalized}:
        return "all"
    return normalized


def _run_fetch_command(
    descriptor: Path,
    include: str | list[str],
    output_dir: Path,
    dry_run: bool,
    check_auth: bool,
) -> None:
    summary = fetch_from_descriptor(
        descriptor=descriptor,
        include=include,
        output_dir=output_dir,
        dry_run=dry_run,
        check_auth=check_auth,
        log=typer.echo,
        sharepoint_client_factory=_make_sharepoint_client,
        googledrive_client_factory=lambda: _make_gdrive_client(None),
    )
    if not summary.ok:
        raise typer.Exit(code=1)


def _render_auth_results(results: list[Any], output_format: OutputFormat) -> None:
    if output_format == OutputFormat.JSON:
        _echo_json([result.to_dict() for result in results])
        return

    if not results:
        typer.echo("No matching adapters were selected.")
        return

    for result in results:
        status = "ready" if result.ok else "failed"
        typer.echo(f"{result.adapter}: {status} - {result.message}")


@app.command(
    "fetch",
    epilog=_examples_epilog(
        "sharedrive fetch resources/descriptor.yaml --dry-run",
        "sharedrive fetch resources/descriptor.yaml --include s3 --include sharepoint",
        "sharedrive fetch resources/descriptor.yaml --include spec-workbook --output-dir resources",
    ),
)
def fetch(
    descriptor: Path = typer.Argument(
        ...,
        exists=False,
        help="Descriptor file path.",
    ),
    include: Optional[list[str]] = typer.Option(
        None,
        "--include",
        "-i",
        help=(
            "Include adapter types and/or resource names. "
            "Repeat the option or pass a comma-separated list."
        ),
    ),
    output_dir: Path = typer.Option(Path("resources"), help="Base output directory for relative resource paths."),
    dry_run: bool = typer.Option(False, help="Print actions without downloading."),
    check_auth: bool = typer.Option(False, "--check-auth", help="Validate service credentials before downloading."),
    env_file: Optional[Path] = typer.Option(None, "--env-file", help="Path to .env file for credentials. Defaults to .env in the current directory."),
) -> None:
    """Fetch descriptor resources by adapter type or resource name filters."""
    _load_env_file(env_file)
    include_values = _parse_include_values(include)
    _run_fetch_command(
        descriptor=descriptor,
        include=include_values,
        output_dir=output_dir,
        dry_run=dry_run,
        check_auth=check_auth,
    )


@app.command(
    "retrieve",
    hidden=True,
    epilog=_examples_epilog(
        "sharedrive retrieve resources/descriptor.yaml --dry-run",
        "sharedrive retrieve resources/descriptor.yaml --include s3 --include sharepoint",
    ),
)
def retrieve(
    descriptor: Path = typer.Argument(
        ...,
        exists=False,
        help="Descriptor file path.",
    ),
    include: Optional[list[str]] = typer.Option(
        None,
        "--include",
        "-i",
        help=(
            "Include adapter types and/or resource names. "
            "Repeat the option or pass a comma-separated list."
        ),
    ),
    output_dir: Path = typer.Option(Path("resources"), help="Base output directory for relative resource paths."),
    dry_run: bool = typer.Option(False, help="Print actions without downloading."),
    check_auth: bool = typer.Option(False, "--check-auth", help="Validate service credentials before downloading."),
    env_file: Optional[Path] = typer.Option(None, "--env-file", help="Path to .env file for credentials. Defaults to .env in the current directory."),
) -> None:
    """Backward-compatible alias for fetch."""
    fetch(
        descriptor=descriptor,
        include=include,
        output_dir=output_dir,
        dry_run=dry_run,
        check_auth=check_auth,
        env_file=env_file,
    )


@auth_app.command(
    "check",
    epilog=_examples_epilog(
        "sharedrive auth check resources/descriptor.yaml",
        "sharedrive auth check resources/descriptor.yaml --include sharepoint",
        "sharedrive auth check resources/descriptor.yaml --format json",
    ),
)
def auth_check(
    descriptor: Path = typer.Argument(..., exists=False, help="Descriptor file path."),
    include: Optional[list[str]] = typer.Option(
        None,
        "--include",
        "-i",
        help=(
            "Include adapter types and/or resource names. "
            "Repeat the option or pass a comma-separated list."
        ),
    ),
    output_format: OutputFormat = typer.Option(OutputFormat.TEXT, "--format", help="Output format."),
    env_file: Optional[Path] = typer.Option(None, "--env-file", help="Path to .env file for credentials. Defaults to .env in the current directory."),
) -> None:
    """Validate credentials for the adapters selected by a descriptor."""
    _load_env_file(env_file)
    include_values = _parse_include_values(include)
    results = check_auth_for_descriptor(
        descriptor=descriptor,
        include=include_values,
        sharepoint_client_factory=_make_sharepoint_client,
        googledrive_client_factory=lambda: _make_gdrive_client(None),
    )
    _render_auth_results(results, output_format)
    if any(not result.ok for result in results):
        raise typer.Exit(code=1)


@auth_login_app.command(
    "gdrive",
    epilog=_examples_epilog(
        "sharedrive auth login gdrive --oauth-client-secrets .google/oauth-credentials.json --oauth-token-path .google/oauth-token.json",
        "sharedrive auth login gdrive --scope https://www.googleapis.com/auth/drive.readonly",
    ),
)
def auth_login_gdrive(
    oauth_client_secrets: Optional[Path] = typer.Option(None, "--oauth-client-secrets", help="Path to Google OAuth client secrets JSON."),
    oauth_token_path: Optional[Path] = typer.Option(None, "--oauth-token-path", help="Path to persist the authorized-user token JSON."),
    scope: Optional[list[str]] = typer.Option(None, "--scope", help="OAuth scope. Repeat for multiple scopes."),
    no_local_server: bool = typer.Option(False, "--no-local-server", help="Use the console flow instead of a local callback server."),
    env_file: Optional[Path] = typer.Option(None, "--env-file", help="Path to .env file for credentials. Defaults to .env in the current directory."),
) -> None:
    """Run the Google installed-app OAuth flow and optionally persist a token."""
    from sharedrive.auth.settings import GoogleAuthConfig, GoogleAuthMode

    _load_env_file(env_file)

    config_kwargs: dict[str, Any] = {
        "auth_mode": GoogleAuthMode.USER_OAUTH,
        "use_local_server": not no_local_server,
    }
    if oauth_client_secrets is not None:
        config_kwargs["oauth_client_secrets"] = oauth_client_secrets
    if oauth_token_path is not None:
        config_kwargs["oauth_token_path"] = oauth_token_path
    if scope is not None:
        config_kwargs["scopes"] = scope

    config = GoogleAuthConfig(**config_kwargs)
    config.to_strategy().build()

    if config.oauth_token_path is not None:
        typer.echo(f"Google Drive login succeeded. Token saved to {config.oauth_token_path}")
    else:
        typer.echo("Google Drive login succeeded. No token path was configured, so credentials are only available for this process.")


@auth_login_app.command(
    "microsoft",
    epilog=_examples_epilog(
        "sharedrive auth login microsoft",
        "sharedrive auth login microsoft --auth-mode delegated",
        "sharedrive auth login microsoft --host-url norc.sharepoint.com",
    ),
)
def auth_login_microsoft(
    auth_mode: Optional[str] = typer.Option(None, "--auth-mode", help="Microsoft auth mode: app_only or delegated."),
    host_url: Optional[str] = typer.Option(None, "--host-url", help="SharePoint host for validating Graph-backed access, for example norc.sharepoint.com."),
    scope: Optional[list[str]] = typer.Option(None, "--scope", help="Microsoft Graph scope. Repeat for multiple scopes."),
    env_file: Optional[Path] = typer.Option(None, "--env-file", help="Path to .env file for credentials. Defaults to .env in the current directory."),
) -> None:
    """Validate Microsoft authentication used by SharePoint workflows."""
    _run_microsoft_login(auth_mode, host_url, scope, env_file)


@auth_login_app.command(
    "sharepoint",
    epilog=_examples_epilog(
        "sharedrive auth login sharepoint",
        "sharedrive auth login sharepoint --auth-mode delegated",
        "sharedrive auth login sharepoint --host-url norc.sharepoint.com",
    ),
)
def auth_login_sharepoint(
    auth_mode: Optional[str] = typer.Option(None, "--auth-mode", help="Microsoft auth mode for SharePoint: app_only or delegated."),
    host_url: Optional[str] = typer.Option(None, "--host-url", help="SharePoint host, for example norc.sharepoint.com."),
    scope: Optional[list[str]] = typer.Option(None, "--scope", help="Microsoft Graph scope. Repeat for multiple scopes."),
    env_file: Optional[Path] = typer.Option(None, "--env-file", help="Path to .env file for credentials. Defaults to .env in the current directory."),
) -> None:
    """Validate SharePoint authentication using the configured auth mode."""
    _run_microsoft_login(auth_mode, host_url, scope, env_file)


@gdrive_app.command(
    "list",
    epilog=_examples_epilog(
        "sharedrive gdrive list",
        "sharedrive gdrive list --credentials-path ./secrets/google-service-account.json",
    ),
)
def gdrive_list(
    credentials_path: Optional[str] = typer.Option(None, help="Path to service account JSON; defaults to GOOGLE_APPLICATION_CREDENTIALS."),
) -> None:
    """Print JSON metadata for all files visible to the authenticated Google Drive client."""
    client = _make_gdrive_client(credentials_path)
    _echo_json(client.list_files())


@gdrive_app.command(
    "get",
    epilog=_examples_epilog(
        "sharedrive gdrive get 1lvWns43FFPerUjFpHPFfFnPLr-B-ERAqG83AVC4bpME",
        "sharedrive gdrive get https://docs.google.com/document/d/<id>/edit",
    ),
)
def gdrive_get(
    file_id_or_url: str = typer.Argument(..., help="Google file ID or web URL."),
    credentials_path: Optional[str] = typer.Option(None, help="Path to credentials JSON."),
) -> None:
    """Print JSON metadata for one Google Drive file resolved from an ID or web URL."""
    client = _make_gdrive_client(credentials_path)
    if file_id_or_url.startswith("http"):
        _echo_json(client.get_from_weburl(file_id_or_url))
    else:
        _echo_json(client.get_file(file_id_or_url))


@gdrive_app.command(
    "download",
    epilog=_examples_epilog(
        "sharedrive gdrive download 1lvWns43FFPerUjFpHPFfFnPLr-B-ERAqG83AVC4bpME resources/test.docx",
        "sharedrive gdrive download https://docs.google.com/document/d/<id>/edit resources/test.docx",
    ),
)
def gdrive_download(
    file_id_or_url: str = typer.Argument(..., help="Google file ID or web URL."),
    output_path: Path = typer.Argument(..., help="Local output path."),
    credentials_path: Optional[str] = typer.Option(None, help="Path to credentials JSON."),
) -> None:
    """Download one Google Drive file and print the written local output path."""
    client = _make_gdrive_client(credentials_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if file_id_or_url.startswith("http"):
        client.download_from_weburl(file_id_or_url, output_path=str(output_path))
    else:
        client.download_file(file_id_or_url, output_path=str(output_path))
    typer.echo(str(output_path))


@gdrive_app.command(
    "export",
    epilog=_examples_epilog(
        "sharedrive gdrive export 1lvWns43FFPerUjFpHPFfFnPLr-B-ERAqG83AVC4bpME --mime-type application/pdf --output-path resources/test.pdf",
        "sharedrive gdrive export https://docs.google.com/spreadsheets/d/<id>/edit --mime-type text/csv",
    ),
)
def gdrive_export(
    file_id_or_url: str = typer.Argument(..., help="Google file ID or web URL."),
    mime_type: Optional[str] = typer.Option(None, help="Target export MIME type."),
    output_path: Optional[Path] = typer.Option(None, help="Optional output path."),
    credentials_path: Optional[str] = typer.Option(None, help="Path to credentials JSON."),
) -> None:
    """Export a Google Workspace file and print output path or exported byte count."""
    client = _make_gdrive_client(credentials_path)
    kwargs: dict[str, Any] = {"mime_type": mime_type}
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_path"] = str(output_path)
    if file_id_or_url.startswith("http"):
        result = client.export_from_weburl(file_id_or_url, **kwargs)
    else:
        result = client.export_file(file_id_or_url, **kwargs)
    if isinstance(result, bytes):
        typer.echo(f"Exported {len(result)} bytes")
    else:
        typer.echo(str(result))


@sharepoint_app.command(
    "get",
    epilog=_examples_epilog(
        "sharedrive sharepoint get https://norc.sharepoint.com/sites/MySite/Shared%20Documents/path/file.xlsx",
        "sharedrive spo get https://norc.sharepoint.com/sites/MySite/Shared%20Documents/path/file.xlsx",
    ),
)
def sharepoint_get(url: str = typer.Argument(..., help="SharePoint URL.")) -> None:
    """Print JSON metadata for a SharePoint file or folder URL."""
    client = _make_sharepoint_client()
    _echo_json(client.get_from_weburl(url))


@sharepoint_app.command(
    "download",
    epilog=_examples_epilog(
        "sharedrive sharepoint download https://norc.sharepoint.com/sites/MySite/Shared%20Documents/path/file.xlsx resources/file.xlsx",
        "sharedrive sharepoint download https://norc.sharepoint.com/sites/MySite/Shared%20Documents/path/file.xlsx resources/file.xlsx --dry-run",
        "sharedrive spo download https://norc.sharepoint.com/sites/MySite/Shared%20Documents/path/file.xlsx resources/file.xlsx",
        "sharedrive spo download https://norc.sharepoint.com/sites/MySite/Shared%20Documents/path/file.xlsx resources/file.xlsx --dry-run",
    ),
)
def sharepoint_download(
    url: str = typer.Argument(..., help="SharePoint URL."),
    output_path: Path = typer.Argument(..., help="Local output path."),
    dry_run: bool = typer.Option(False, help="Print action only."),
) -> None:
    """Download one SharePoint file to disk and print the local path when not dry-run."""
    client = _make_sharepoint_client()
    client.download_from_weburl(url=url, output_path=output_path, dry_run=dry_run)
    if not dry_run:
        typer.echo(str(output_path))


@s3_app.command(
    "cp",
    epilog=_examples_epilog(
        "sharedrive s3 cp s3://my-bucket/path/file.csv resources/file.csv",
        "sharedrive s3 cp https://s3.amazonaws.com/my-bucket/path/file.csv resources/file.csv --no-cloudpathlib",
    ),
)
def s3_cp(
    source_url: str = typer.Argument(..., help="S3 URL (s3://bucket/key or compatible HTTPS)."),
    output_path: Path = typer.Argument(..., help="Local output path."),
    dry_run: bool = typer.Option(False, help="Print action only."),
    no_cloudpathlib: bool = typer.Option(False, help="Disable cloudpathlib and use boto3 download fallback."),
) -> None:
    """Copy one S3 object to a local path and print the local file path when written."""
    result = download_s3_url(source_url, output_path, dry_run=dry_run, use_cloudpathlib=not no_cloudpathlib)
    if result:
        typer.echo(str(result))


@s3_app.command(
    "ls",
    epilog=_examples_epilog(
        "sharedrive s3 ls s3://my-bucket/path/",
    ),
)
def s3_ls(source_url: str = typer.Argument(..., help="S3 URL prefix.")) -> None:
    """List entries under an S3 prefix and print one path per line."""
    if S3Path is None:
        raise typer.BadParameter("cloudpathlib is required for ls command")
    for item in S3Path(source_url).iterdir():
        typer.echo(str(item))


@s3_app.command(
    "cat",
    epilog=_examples_epilog(
        "sharedrive s3 cat s3://my-bucket/path/file.txt",
        "sharedrive s3 cat s3://my-bucket/path/file.json --encoding utf-8",
    ),
)
def s3_cat(
    source_url: str = typer.Argument(..., help="S3 object URL."),
    encoding: str = typer.Option("utf-8", help="Text encoding for output."),
) -> None:
    """Print text contents of an S3 object decoded with the selected encoding."""
    if S3Path is None:
        raise typer.BadParameter("cloudpathlib is required for cat command")
    typer.echo(S3Path(source_url).read_text(encoding=encoding))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
