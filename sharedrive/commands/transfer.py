from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from sharedrive.actions.download import download as download_action
from sharedrive.actions.fetch import fetch as fetch_action
from sharedrive.commands.toolkit import (
    DESCRIPTOR_DEFAULT_HELP,
    OutputFormat,
    echo_json,
    examples_epilog,
    exit_if_descriptor_missing,
    load_env_file,
    scoped_selector,
)
from sharedrive.exceptions import GoogleApiError, GraphApiError
from sharedrive.helpers import resolve_descriptor_path, resolve_output_dir


def _summary_to_dict(summary) -> dict:
    return {
        "total_resources": summary.total_resources,
        "downloaded": summary.downloaded,
        "skipped": summary.skipped,
        "dry_run_actions": summary.dry_run_actions,
        "failures": summary.failures,
        "ok": summary.ok,
    }


def register_transfer_commands(app: typer.Typer) -> None:
    @app.command(
        "fetch",
        epilog=examples_epilog(
            "sharedrive fetch # get metadata for the default selector in the checked-out descriptor",
            "sharedrive fetch census-package --descriptor resources/descriptor.yaml --dry-run",
            "sharedrive fetch census-package --descriptor resources/descriptor.yaml",
        ),
    )
    def fetch(
        entity: Optional[str] = typer.Argument(
            None,
            help="Entity or package dot-path to fetch. If omitted, uses the checked-out entity.",
        ),
        descriptor: Optional[Path] = typer.Option(
            None, "--descriptor", help=DESCRIPTOR_DEFAULT_HELP
        ),
        dry_run: bool = typer.Option(
            False, help="Preview descriptor changes without writing them."
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
        """Fetch remote metadata for one selector into the descriptor."""
        load_env_file(env_file)
        descriptor_path = resolve_descriptor_path(descriptor)
        exit_if_descriptor_missing(descriptor_path)
        entity_name = scoped_selector(entity)

        if output_format == OutputFormat.TEXT:
            if entity_name is not None:
                typer.echo(
                    f"Fetching metadata in {descriptor_path} for selector '{entity_name}'..."
                )
            else:
                typer.echo(f"Fetching all metadata in {descriptor_path}")

        try:
            summaries = fetch_action(
                descriptor=descriptor_path, selector=entity_name, dry_run=dry_run, log=None
            )
        except (
            FileNotFoundError,
            NotImplementedError,
            ValueError,
            GoogleApiError,
            GraphApiError,
        ) as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc

        if output_format == OutputFormat.JSON:
            echo_json(
                {
                    "descriptor": descriptor_path.as_posix(),
                    "selector": entity_name,
                    "summaries": [
                        {
                            "resource_name": summary.resource_name,
                            "generated_resources": summary.generated_resources,
                            "dry_run": summary.dry_run,
                            "changed": summary.changed,
                            "failures": summary.failures,
                            "errors": summary.errors,
                            "ok": summary.ok,
                        }
                        for summary in summaries
                    ],
                }
            )
            return

        if not summaries:
            typer.echo("No fetchable entities found.")
            return
        for summary in summaries:
            action = "Would fetch" if summary.dry_run else "Fetched"
            typer.echo(
                f"{action} metadata for {summary.generated_resources} resource(s) into '{summary.resource_name}' in {descriptor_path}."
            )

    @app.command(
        "download",
        epilog=examples_epilog(
            "sharedrive download --dry-run",
            "sharedrive download my-package --descriptor resources/descriptor.yaml",
            "sharedrive download my-package --output-dir resources",
        ),
    )
    def download(
        selector: Optional[str] = typer.Argument(
            None,
            help="Selector to download. If omitted, uses the checked-out entity or whole descriptor.",
        ),
        descriptor: Optional[Path] = typer.Option(
            None, "--descriptor", help=DESCRIPTOR_DEFAULT_HELP
        ),
        output_dir: Optional[Path] = typer.Option(
            None, help="Base output directory for relative resource paths."
        ),
        dry_run: bool = typer.Option(False, help="Print actions without downloading."),
        check_auth: bool = typer.Option(
            False, "--check-auth", help="Validate service credentials before downloading."
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
        """Download resources from a selector in the descriptor."""
        load_env_file(env_file)
        descriptor_path = resolve_descriptor_path(descriptor)
        entity_name = scoped_selector(selector)

        output_dir_path = resolve_output_dir(output_dir, descriptor=descriptor_path)

        exit_if_descriptor_missing(descriptor_path)

        summary = download_action(
            descriptor=descriptor_path,
            selector=entity_name,
            output_dir=output_dir_path,
            dry_run=dry_run,
            check_auth=check_auth,
            log=(typer.echo if output_format == OutputFormat.TEXT else None),
        )
        if output_format == OutputFormat.JSON:
            echo_json(
                {
                    "descriptor": descriptor_path.as_posix(),
                    "selector": entity_name,
                    "output_dir": output_dir_path.as_posix(),
                    "dry_run": dry_run,
                    "check_auth": check_auth,
                    "summary": _summary_to_dict(summary),
                }
            )
        if not summary.ok:
            raise typer.Exit(code=1)


__all__ = ["register_transfer_commands"]
