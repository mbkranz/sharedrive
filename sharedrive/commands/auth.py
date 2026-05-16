from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import typer

from sharedrive.actions.download import check_auth as check_auth_action
from sharedrive.commands.toolkit import (
    DESCRIPTOR_DEFAULT_HELP,
    OutputFormat,
    echo_json,
    examples_epilog,
    exit_if_descriptor_missing,
    load_env_file,
    parse_include_values,
    run_microsoft_login,
)
from sharedrive.helpers import resolve_descriptor_path


def _render_auth_results(results: list[Any], output_format: OutputFormat) -> None:
    if output_format == OutputFormat.JSON:
        echo_json([result.to_dict() for result in results])
        return

    if not results:
        typer.echo("No matching adapters were selected.")
        return

    for result in results:
        status = "ready" if result.ok else "failed"
        typer.echo(f"{result.adapter}: {status} - {result.message}")


def register_auth_commands(auth_app: typer.Typer, auth_login_app: typer.Typer) -> None:
    @auth_app.command(
        "check",
        epilog=examples_epilog(
            "sharedrive auth check resources/descriptor.yaml",
            "sharedrive auth check resources/descriptor.yaml --include sharepoint",
            "sharedrive auth check resources/descriptor.yaml --format json",
        ),
    )
    def auth_check(
        descriptor: Optional[Path] = typer.Argument(
            None, exists=False, help=DESCRIPTOR_DEFAULT_HELP
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
        output_format: OutputFormat = typer.Option(
            OutputFormat.TEXT, "--format", help="Output format."
        ),
        env_file: Optional[Path] = typer.Option(
            None,
            "--env-file",
            help="Path to .env file for credentials. Defaults to .env in the current directory.",
        ),
    ) -> None:
        """Validate credentials for the adapters selected by a descriptor."""
        load_env_file(env_file)
        descriptor_path = resolve_descriptor_path(descriptor)
        exit_if_descriptor_missing(descriptor_path)
        include_values = parse_include_values(include)
        results = check_auth_action(descriptor=descriptor_path, selector=include_values)
        _render_auth_results(results, output_format)
        if any(not result.ok for result in results):
            raise typer.Exit(code=1)

    @auth_login_app.command(
        "gdrive",
        epilog=examples_epilog(
            "sharedrive auth login gdrive --oauth-client-secrets .google/oauth-credentials.json --oauth-token-path .google/oauth-token.json",
            "sharedrive auth login gdrive --scope https://www.googleapis.com/auth/drive.readonly",
        ),
    )
    def auth_login_gdrive(
        oauth_client_secrets: Optional[Path] = typer.Option(
            None,
            "--oauth-client-secrets",
            help="Path to Google OAuth client secrets JSON.",
        ),
        oauth_token_path: Optional[Path] = typer.Option(
            None,
            "--oauth-token-path",
            help="Path to persist the authorized-user token JSON.",
        ),
        scope: Optional[list[str]] = typer.Option(
            None, "--scope", help="OAuth scope. Repeat for multiple scopes."
        ),
        no_local_server: bool = typer.Option(
            False,
            "--no-local-server",
            help="Use the console flow instead of a local callback server.",
        ),
        env_file: Optional[Path] = typer.Option(
            None,
            "--env-file",
            help="Path to .env file for credentials. Defaults to .env in the current directory.",
        ),
    ) -> None:
        """Run the Google installed-app OAuth flow and optionally persist a token."""
        from sharedrive.auth.settings import GoogleAuthConfig, GoogleAuthMode

        load_env_file(env_file)

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
        config.to_auth()

        if config.oauth_token_path is not None:
            typer.echo(
                f"Google Drive login succeeded. Token saved to {config.oauth_token_path}"
            )
        else:
            typer.echo(
                "Google Drive login succeeded. No token path was configured, so credentials are only available for this process."
            )

    @auth_login_app.command(
        "microsoft",
        epilog=examples_epilog(
            "sharedrive auth login microsoft",
            "sharedrive auth login microsoft --auth-mode delegated",
            "sharedrive auth login microsoft --host-url norc.sharepoint.com",
        ),
    )
    def auth_login_microsoft(
        auth_mode: Optional[str] = typer.Option(
            None, "--auth-mode", help="Microsoft auth mode: app_only or delegated."
        ),
        host_url: Optional[str] = typer.Option(
            None,
            "--host-url",
            help="SharePoint host for validating Graph-backed access, for example norc.sharepoint.com.",
        ),
        scope: Optional[list[str]] = typer.Option(
            None, "--scope", help="Microsoft Graph scope. Repeat for multiple scopes."
        ),
        env_file: Optional[Path] = typer.Option(
            None,
            "--env-file",
            help="Path to .env file for credentials. Defaults to .env in the current directory.",
        ),
    ) -> None:
        """Validate Microsoft authentication used by SharePoint workflows."""
        run_microsoft_login(auth_mode, host_url, scope, env_file)

    @auth_login_app.command(
        "sharepoint",
        epilog=examples_epilog(
            "sharedrive auth login sharepoint",
            "sharedrive auth login sharepoint --auth-mode delegated",
            "sharedrive auth login sharepoint --host-url norc.sharepoint.com",
        ),
    )
    def auth_login_sharepoint(
        auth_mode: Optional[str] = typer.Option(
            None,
            "--auth-mode",
            help="Microsoft auth mode for SharePoint: app_only or delegated.",
        ),
        host_url: Optional[str] = typer.Option(
            None, "--host-url", help="SharePoint host, for example norc.sharepoint.com."
        ),
        scope: Optional[list[str]] = typer.Option(
            None, "--scope", help="Microsoft Graph scope. Repeat for multiple scopes."
        ),
        env_file: Optional[Path] = typer.Option(
            None,
            "--env-file",
            help="Path to .env file for credentials. Defaults to .env in the current directory.",
        ),
    ) -> None:
        """Validate SharePoint authentication using the configured auth mode."""
        run_microsoft_login(auth_mode, host_url, scope, env_file)


__all__ = ["register_auth_commands"]
