from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from sharedrive.commands.toolkit import examples_epilog, parse_set_args
from sharedrive.helpers import DESCRIPTOR_DEFAULTS_FILE, save_params_for_scope


def register_config_commands(app: typer.Typer) -> None:
    @app.command(
        "set",
        context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
        epilog=examples_epilog(
            "sharedrive set --global --descriptor resources/descriptor.yaml",
            "sharedrive set --global --output-dir resources",
            "sharedrive set resources/descriptor.yaml --output-dir exports",
        ),
    )
    def set_command(
        ctx: typer.Context,
        descriptor_scope: Optional[Path] = typer.Argument(
            None, help="Descriptor path to save defaults for."
        ),
        global_scope: bool = typer.Option(
            False, "--global", help="Save params as global defaults for all descriptors."
        ),
        descriptor: Optional[str] = typer.Option(
            None, "--descriptor", help="Default descriptor path to save."
        ),
        output_dir: Optional[str] = typer.Option(
            None, "--output-dir", help="Default output directory to save."
        ),
    ) -> None:
        """Set reusable key/value parameters for sharedrive descriptor workflows."""
        parsed = parse_set_args(list(ctx.args))

        if descriptor_scope is not None and not Path(descriptor_scope).exists():
            raise typer.BadParameter(
                f"Descriptor '{descriptor_scope}' does not exist.",
                param_hint="<descriptor>",
            )

        if descriptor is not None:
            descriptor_path = Path(descriptor)
            if not descriptor_path.exists():
                raise typer.BadParameter(
                    f"Descriptor '{descriptor_path}' does not exist.",
                    param_hint="--descriptor",
                )
            parsed["descriptor"] = descriptor_path.as_posix()
        if output_dir is not None:
            parsed["output_dir"] = output_dir
        if not parsed:
            raise typer.BadParameter("Provide one or more values to save.")

        try:
            target = save_params_for_scope(
                parsed, descriptor_scope, global_scope=global_scope
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        typer.echo(
            f"Saved {len(parsed)} parameter(s) for '{target}' in {DESCRIPTOR_DEFAULTS_FILE}."
        )


__all__ = ["register_config_commands"]
