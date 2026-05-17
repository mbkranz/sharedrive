from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import typer
from dotenv import load_dotenv

from sharedrive.helpers import get_checked_out_entity
from sharedrive.helpers import resolve_descriptor_path as resolve_descriptor_path_helper
from sharedrive.models import (
    DriveCatalog,
    DrivePackage,
    DriveResource,
    normalize_entity_type,
    normalize_service_type,
)


class OutputFormat(str, Enum):
    TEXT = "text"
    JSON = "json"


DESCRIPTOR_DEFAULT_HELP = (
    "Descriptor file path. Defaults to the saved descriptor or the first "
    "standard descriptor path."
)


def examples_epilog(*lines: str) -> str:
    codeblocks = "\n\n".join(f"```bash\n\n\n{line.strip()}\n\n\n```" for line in lines)
    return f"\n\n**Examples**\n\n\n{codeblocks}"


def echo_json(payload: Any) -> None:
    typer.echo(json.dumps(payload, indent=2, default=str))


def load_env_file(env_file: Optional[Path]) -> None:
    if env_file is not None:
        load_dotenv(str(env_file), override=True)


def prepare_descriptor_path(
    descriptor: Path | str | None = None,
    *,
    env_file: Optional[Path] = None,
    require_exists: bool = True,
) -> Path:
    load_env_file(env_file)
    descriptor_path = resolve_descriptor_path_helper(descriptor)
    if require_exists:
        exit_if_descriptor_missing(descriptor_path)
    return descriptor_path


def run_microsoft_login(
    auth_mode: Optional[str],
    host_url: Optional[str],
    scope: Optional[list[str]],
    env_file: Optional[Path],
) -> None:
    from sharedrive.auth.settings import MicrosoftAuthConfig, MicrosoftAuthMode

    load_env_file(env_file)

    config_kwargs: dict[str, Any] = {}
    if auth_mode is not None:
        config_kwargs["auth_mode"] = MicrosoftAuthMode(auth_mode)
    if host_url is not None:
        config_kwargs["host_url"] = host_url
    if scope is not None:
        config_kwargs["scopes"] = scope

    config = MicrosoftAuthConfig(**config_kwargs)
    config.to_auth()
    typer.echo(
        f"Microsoft login succeeded using {config.auth_mode.value} mode for {config.host_url}"
    )


def parse_include_values(values: list[str] | None) -> str | list[str]:
    normalized = parse_selector_tokens(values)
    if normalized is None:
        return "all"
    return normalized


def coerce_set_value(raw: str) -> Any:
    value = raw.strip()
    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower in {"null", "none"}:
        return None
    if (value.startswith("{") and value.endswith("}")) or (
        value.startswith("[") and value.endswith("]")
    ):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return raw
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return raw


def parse_set_args(args: list[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    if not args:
        return parsed
    idx = 0
    while idx < len(args):
        token = args[idx]
        if not token.startswith("--"):
            raise typer.BadParameter(
                f"Invalid token '{token}'. Use --key value or --key=value."
            )

        key_token = token[2:]
        if not key_token:
            raise typer.BadParameter("Invalid empty parameter name.")

        if "=" in key_token:
            key, raw_value = key_token.split("=", 1)
            if not key:
                raise typer.BadParameter("Invalid empty parameter name.")
            parsed[key] = coerce_set_value(raw_value)
            idx += 1
            continue

        key = key_token
        idx += 1
        if idx >= len(args):
            raise typer.BadParameter(f"Missing value for --{key}.")

        raw_value = args[idx]
        if raw_value.startswith("--"):
            raise typer.BadParameter(f"Missing value for --{key}.")
        parsed[key] = coerce_set_value(raw_value)
        idx += 1

    return parsed


def parse_selector_tokens(values: str | list[str] | tuple[str, ...] | None) -> list[str] | None:
    """Parse selector values into tokens or ``None`` when selector means "all".

    Empty parts are ignored, and any ``all`` token takes precedence over all
    other tokens.
    """
    if values is None:
        return None
    raw_values = [values] if isinstance(values, str) else list(values)
    tokens = [
        part.strip()
        for raw_value in raw_values
        for part in raw_value.split(",")
        if part.strip()
    ]
    if not tokens or "all" in {token.lower() for token in tokens}:
        return None
    return tokens


def scoped_selector(selector: str | None) -> str | None:
    """Return selector scoped to checked-out entity, preserving string API shape.

    Returns a single selector token as ``str`` and multiple tokens as a
    comma-separated ``str`` so existing action call sites can keep passing
    selector values as strings.
    """
    checked_out_entity = get_checked_out_entity()
    if selector is None:
        return checked_out_entity
    selector_tokens = parse_selector_tokens(selector)
    if selector_tokens is None:
        return None

    scoped_tokens = (
        [f"{checked_out_entity}.{token}" for token in selector_tokens]
        if checked_out_entity
        else selector_tokens
    )
    return scoped_tokens[0] if len(scoped_tokens) == 1 else ",".join(scoped_tokens)


def resolve_resource_reference(resource_selector: str, descriptor: DriveCatalog):
    for reference in descriptor.iter_entity_paths(include_self=False):
        if reference.name_path == resource_selector or (
            "." not in resource_selector
            and reference.name_path.split(".")[-1] == resource_selector
        ):
            if isinstance(reference.model, (DriveResource, DrivePackage, DriveCatalog)):
                return reference
    raise typer.BadParameter(f'Entity selector "{resource_selector}" was not found.')


def normalize_update_property(property_name: str, *, resource_target: bool) -> str:
    normalized = property_name.strip()
    if not normalized:
        raise typer.BadParameter("Property name must be a non-empty string.")

    normalized = {
        "service-type": "serviceType",
        "entity-type": "entityType",
        "drive-service": "driveService",
        "cache": "_cache",
        "access-url": "accessURL",
    }.get(normalized, normalized)

    if not resource_target:
        return normalized

    aliases = {
        "source": "path",
        "driveService": "serviceType",
    }
    return aliases.get(normalized, normalized)


def normalize_update_value(property_path: str, value: Any) -> Any:
    if property_path == "serviceType" and isinstance(value, str):
        return normalize_service_type(value)
    if property_path == "entityType" and isinstance(value, str):
        return normalize_entity_type(value)
    return value


def exit_if_descriptor_missing(descriptor_path: Path) -> None:
    if descriptor_path.exists():
        return

    typer.echo(f"Descriptor '{descriptor_path}' does not exist.", err=True)
    raise typer.Exit(code=1)


__all__ = [
    "DESCRIPTOR_DEFAULT_HELP",
    "OutputFormat",
    "coerce_set_value",
    "echo_json",
    "examples_epilog",
    "exit_if_descriptor_missing",
    "load_env_file",
    "normalize_update_property",
    "normalize_update_value",
    "parse_include_values",
    "parse_selector_tokens",
    "parse_set_args",
    "prepare_descriptor_path",
    "resolve_resource_reference",
    "run_microsoft_login",
    "scoped_selector",
]
