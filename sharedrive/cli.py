from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import typer
from dplib.error import Error
from dotenv import find_dotenv, load_dotenv

from sharedrive.actions.add import add_resource_to_descriptor
from sharedrive.actions.download import (
    check_auth as check_auth_action,
    download as download_action,
)
from sharedrive.actions.fetch import fetch as fetch_action
from sharedrive.actions.list import list_descriptor_entities
from sharedrive.actions.migrate import migrate_descriptor
from sharedrive.exceptions import GoogleApiError, GraphApiError
from sharedrive.helpers import (
    DESCRIPTOR_DEFAULTS_FILE,
    get_checked_out_entity,
    has_saved_global_descriptor,
    resolve_descriptor_path,
    resolve_output_dir,
    save_params_for_scope,
    set_active_descriptor,
)
from sharedrive.models import (
    DriveCatalog,
    DrivePackage,
    DriveResource,
    normalize_entity_type,
    normalize_service_type,
)

load_dotenv(find_dotenv(usecwd=True))

app = typer.Typer(
    name="sharedrive",
    help="Shared drive utilities for SharePoint, Google Drive, and S3.",
    rich_markup_mode="markdown",
)
clone_app = typer.Typer(
    help="Clone descriptor state for new local variants.", rich_markup_mode="markdown"
)
auth_app = typer.Typer(help="Authentication helpers.", rich_markup_mode="markdown")
auth_login_app = typer.Typer(
    help="Interactive login commands.", rich_markup_mode="markdown"
)
app.add_typer(auth_app, name="auth")
app.add_typer(clone_app, name="clone")
auth_app.add_typer(auth_login_app, name="login")


class OutputFormat(str, Enum):
    TEXT = "text"
    JSON = "json"


DESCRIPTOR_DEFAULT_HELP = (
    "Descriptor file path. Defaults to the saved descriptor or the first "
    "standard descriptor path."
)


def _examples_epilog(*lines: str) -> str:
    codeblocks = "\n\n".join(f"```bash\n\n\n{line.strip()}\n\n\n```" for line in lines)
    return f"\n\n**Examples**\n\n\n{codeblocks}"


def _echo_json(payload: Any) -> None:
    typer.echo(json.dumps(payload, indent=2, default=str))


def _load_env_file(env_file: Optional[Path]) -> None:
    if env_file is not None:
        load_dotenv(str(env_file), override=True)


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
    config.to_auth()
    typer.echo(
        f"Microsoft login succeeded using {config.auth_mode.value} mode for {config.host_url}"
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


def _coerce_set_value(raw: str) -> Any:
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


def _parse_set_args(args: list[str]) -> dict[str, Any]:
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
            parsed[key] = _coerce_set_value(raw_value)
            idx += 1
            continue

        key = key_token
        idx += 1
        if idx >= len(args):
            raise typer.BadParameter(f"Missing value for --{key}.")

        raw_value = args[idx]
        if raw_value.startswith("--"):
            raise typer.BadParameter(f"Missing value for --{key}.")
        parsed[key] = _coerce_set_value(raw_value)
        idx += 1

    return parsed


def _scoped_selector(selector: str | None) -> str | None:
    checked_out_entity = get_checked_out_entity()
    if selector is None:
        return checked_out_entity
    return f"{checked_out_entity}.{selector}" if checked_out_entity else selector


def _resolve_resource_reference(resource_selector: str, descriptor: DriveCatalog):
    for reference in descriptor.iter_entity_paths(include_self=False):
        if reference.name_path == resource_selector or (
            "." not in resource_selector
            and reference.name_path.split(".")[-1] == resource_selector
        ):
            if isinstance(reference.model, (DriveResource, DrivePackage, DriveCatalog)):
                return reference
    raise typer.BadParameter(f'Entity selector "{resource_selector}" was not found.')


def _normalize_update_property(property_name: str, *, resource_target: bool) -> str:
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


def _normalize_update_value(property_path: str, value: Any) -> Any:
    if property_path == "serviceType" and isinstance(value, str):
        return normalize_service_type(value)
    if property_path == "entityType" and isinstance(value, str):
        return normalize_entity_type(value)
    return value


def _exit_if_descriptor_missing(descriptor_path: Path) -> None:
    if descriptor_path.exists():
        return

    typer.echo(f"Descriptor '{descriptor_path}' does not exist.", err=True)
    raise typer.Exit(code=1)


@clone_app.command(
    "descriptor",
    epilog=_examples_epilog(
        "sharedrive clone descriptor resources/descriptor-copy.yaml --descriptor resources/descriptor.yaml",
        "sharedrive clone descriptor resources/descriptor-copy.json --descriptor resources/descriptor.yaml --dry-run",
    ),
)
def clone_descriptor(
    target_path: Path = typer.Argument(
        ..., help="Target descriptor path for the clone."
    ),
    descriptor: Optional[Path] = typer.Option(
        None, "--descriptor", help=DESCRIPTOR_DEFAULT_HELP
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be cloned without writing files."
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite an existing target descriptor."
    ),
) -> None:
    """Clone one descriptor file to a new local path."""
    source_descriptor = resolve_descriptor_path(descriptor)
    _exit_if_descriptor_missing(source_descriptor)
    if source_descriptor == target_path:
        raise typer.BadParameter("Source and target descriptor paths must differ.")
    if target_path.exists() and not force:
        raise typer.BadParameter(
            f"Refusing to overwrite existing descriptor without --force: {target_path}"
        )

    if dry_run:
        typer.echo(f"Would clone descriptor: {source_descriptor} -> {target_path}")
        return

    DriveCatalog.from_path(str(source_descriptor)).to_path(str(target_path))
    typer.echo(f"Cloned descriptor: {source_descriptor} -> {target_path}")


@app.command(
    "update",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    epilog=_examples_epilog(
        'sharedrive update --title "Hello" --description "hello"',
        'sharedrive update --resource file1 --title "Hello" --description "hello"',
        'sharedrive update --descriptor resources/descriptor.yaml --resource file1 --title "Hello"',
    ),
)
def update_command(
    ctx: typer.Context,
    descriptor: Optional[Path] = typer.Option(
        None, "--descriptor", help=DESCRIPTOR_DEFAULT_HELP
    ),
    resource: Optional[str] = typer.Option(
        None, "--resource", help="Exact resource name or dot-path to update."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be updated without writing files."
    ),
) -> None:
    """Update descriptor-root or resource properties using flag-style field edits."""
    parsed = _parse_set_args(list(ctx.args))
    if not parsed:
        raise typer.BadParameter("Provide one or more field values to update.")

    descriptor_path = resolve_descriptor_path(descriptor)
    _exit_if_descriptor_missing(descriptor_path)

    descriptor_model = DriveCatalog.from_path(str(descriptor_path))
    document = descriptor_model.to_dict()
    target_label = str(descriptor_path)
    target: dict[str, Any] = document
    if resource is not None:
        try:
            descriptor_model.assert_valid_entity_paths()
        except Error as exc:
            raise typer.BadParameter(str(exc)) from exc
        resolved = _resolve_resource_reference(resource, descriptor_model)
        target = DriveCatalog.get_json_pointer_value(document, resolved.json_pointer)
        if not isinstance(target, dict):
            raise typer.BadParameter(
                f"Resolved resource '{resolved.name_path}' is not an object."
            )
        target_label = f"{resolved.name_path} in {descriptor_path}"

    changed_properties: list[str] = []
    for property_name, raw_value in parsed.items():
        property_path = _normalize_update_property(
            property_name, resource_target=resource is not None
        )
        value = _normalize_update_value(property_path, raw_value)
        try:
            changed = DriveCatalog.set_property_value(target, property_path, value)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        if changed:
            changed_properties.append(
                f"{property_path} -> {json.dumps(value, default=str)}"
            )

    if not changed_properties:
        typer.echo("No changes needed.")
        return

    if dry_run:
        for change in changed_properties:
            typer.echo(f"Would update {target_label}: {change}")
        return

    DriveCatalog.from_dict(document).to_path(str(descriptor_path))
    for change in changed_properties:
        typer.echo(f"Updated {target_label}: {change}")


@app.command(
    "checkout",
    epilog=_examples_epilog(
        "sharedrive checkout resources/descriptor.yaml",
        "sharedrive checkout resources/descriptor.yaml research",
        "sharedrive checkout resources/descriptor.yaml research.archive",
    ),
)
def checkout_command(
    descriptor: Path = typer.Argument(
        ..., help="Descriptor path to activate for later commands."
    ),
    entity: Optional[str] = typer.Argument(
        None,
        help="Entity dot-path within the descriptor to set as the active scope for fetch/download commands.",
    ),
) -> None:
    """Activate a descriptor and optionally an entity within it for later commands.

    When an entity is checked out, ``fetch`` and ``download`` without a selector
    argument operate on the whole entity.  A selector argument is then treated as
    a path relative to the checked-out entity (e.g. ``fetch archive`` becomes
    ``research.archive`` when ``research`` is checked out).
    """
    try:
        descriptor_path = set_active_descriptor(descriptor, entity=entity)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if entity and entity.strip():
        typer.echo(f"Checked out entity '{entity.strip()}' in {descriptor_path}")
    else:
        typer.echo(f"Checked out descriptor: {descriptor_path}")


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
    "list",
    epilog=_examples_epilog(
        "sharedrive list",
        "sharedrive list resources/descriptor.yaml",
        "sharedrive list resources/descriptor.yaml --format json",
    ),
)
def list_command(
    descriptor: Optional[Path] = typer.Argument(
        None, exists=False, help=DESCRIPTOR_DEFAULT_HELP
    ),
    output_format: OutputFormat = typer.Option(
        OutputFormat.TEXT, "--format", help="Output format."
    ),
) -> None:
    """List local descriptor entities, paths, and source metadata."""
    descriptor_path = resolve_descriptor_path(descriptor)
    _exit_if_descriptor_missing(descriptor_path)

    try:
        entities = list_descriptor_entities(descriptor_path)
    except (FileNotFoundError, ValueError, Error) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if output_format == OutputFormat.JSON:
        _echo_json(
            {
                "descriptor": descriptor_path.as_posix(),
                "entities": [entity.to_dict() for entity in entities],
            }
        )
        return

    from rich.console import Console
    from rich.tree import Tree

    root = Tree(descriptor_path.name)
    nodes: dict[str, Any] = {}
    for entity in entities:
        parent_path = entity.name_path.rpartition(".")[0]
        parent_node = nodes.get(parent_path, root) if parent_path else root
        label = (
            f"{entity.name} ({entity.entity_type}) "
            f"[dim]{entity.name_path} {entity.json_pointer}[/dim]"
        )
        node = parent_node.add(label)
        nodes[entity.name_path] = node
        details = []
        if entity.path:
            details.append(f"path={entity.path}")
        if entity.cache:
            details.append(f"_cache={entity.cache}")
        if entity.access_url:
            details.append(f"accessURL={entity.access_url}")
        if entity.service_type:
            details.append(f"serviceType={entity.service_type}")
        if entity.drive_entity_type:
            details.append(f"entityType={entity.drive_entity_type}")
        if details:
            node.add("[dim]" + ", ".join(details) + "[/dim]")

    Console().print(root)


@app.command(
    "set",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    epilog=_examples_epilog(
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
    parsed = _parse_set_args(list(ctx.args))

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


@app.command(
    "add",
    epilog=_examples_epilog(
        "sharedrive add my-resource --path https://drive.google.com/file/d/123... --cache downloads/file.csv",
        "sharedrive add my-folder --catalog --access-url https://drive.google.com/drive/folders/abc...",
    ),
)
def add(
    name: str = typer.Argument(..., help="Resource name to store in the descriptor."),
    path: Optional[str] = typer.Option(
        None, "--path", help="Canonical resource path, usually a remote file URL."
    ),
    cache: Optional[str] = typer.Option(
        None, "--cache", help="Local materialized path stored as _cache."
    ),
    access_url: Optional[str] = typer.Option(
        None, "--access-url", help="Remote folder/container accessURL for catalogs."
    ),
    source: Optional[str] = typer.Option(
        None,
        "--source",
        help="Deprecated alias for --path on file resources or --access-url on catalogs.",
    ),
    title: Optional[str] = typer.Option(
        None, "--title", help="Optional resource title."
    ),
    description: Optional[str] = typer.Option(
        None, "--description", help="Optional resource description."
    ),
    service_type: Optional[str] = typer.Option(
        None,
        "--service-type",
        help="Source serviceType. If omitted, infer from source.",
    ),
    entity_type: Optional[str] = typer.Option(
        None,
        "--entity-type",
        help="Source entityType such as File, Directory, or Container.",
    ),
    package: bool = typer.Option(
        False,
        "--package",
        help="Deprecated; remote folders are catalogs. Use --catalog.",
    ),
    catalog: bool = typer.Option(
        False,
        "--catalog",
        help="Treat as a catalog with accessURL.",
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="Optional metadata profile for the resource."
    ),
    descriptor: Optional[Path] = typer.Option(
        None, "--descriptor", help=DESCRIPTOR_DEFAULT_HELP
    ),
) -> None:
    """Add a standards-aligned resource or catalog entry to a descriptor."""
    descriptor_path = resolve_descriptor_path(descriptor)
    explicit_descriptor = descriptor is not None or has_saved_global_descriptor()
    if explicit_descriptor:
        _exit_if_descriptor_missing(descriptor_path)

    try:
        resource = add_resource_to_descriptor(
            descriptor=descriptor_path,
            name=name,
            path=path,
            cache=cache,
            source=source,
            access_url=access_url or (source if catalog else None),
            title=title,
            description=description,
            service_type=service_type,
            entity_type=entity_type,
            package=package,
            catalog=catalog,
            profile=profile,
            create_if_missing=not explicit_descriptor,
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

    location = resource.get("accessURL") or resource.get("path")
    typer.echo(
        f"Added {'catalog' if catalog else 'resource'} '{resource['name']}' to {descriptor_path} "
        f"at {location} with serviceType '{resource.get('serviceType')}', "
        f"entityType '{resource.get('entityType')}'."
    )


@app.command(
    "fetch",
    epilog=_examples_epilog(
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
    env_file: Optional[Path] = typer.Option(
        None,
        "--env-file",
        help="Path to .env file for credentials. Defaults to .env in the current directory.",
    ),
) -> None:
    """Fetch remote metadata for one selector into the descriptor.

    TODO(manage_todo_list): reconsider direct source-path fetch flow.
    """
    _load_env_file(env_file)
    descriptor_path = resolve_descriptor_path(descriptor)
    _exit_if_descriptor_missing(descriptor_path)
    entity_name = _scoped_selector(entity)

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

    if not summaries:
        typer.echo("No fetchable entities found.")
        return
    for summary in summaries:
        action = "Would fetch" if summary.dry_run else "Fetched"
        typer.echo(
            f"{action} metadata for {summary.generated_resources} resource(s) into '{summary.resource_name}' in {descriptor_path}."
        )


@app.command(
    "migrate",
    epilog=_examples_epilog(
        "sharedrive migrate resources/descriptor.yaml --dry-run",
        "sharedrive migrate resources/descriptor.yaml --output resources/descriptor.v2.yaml",
    ),
)
def migrate(
    descriptor: Path = typer.Argument(..., help="Legacy descriptor to migrate."),
    output: Optional[Path] = typer.Option(
        None, "--output", help="Write migrated descriptor to this path."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print migrated descriptor JSON without writing."
    ),
) -> None:
    """Migrate legacy sources/path descriptors to path/_cache/accessURL."""
    try:
        catalog = migrate_descriptor(descriptor, output=output, dry_run=dry_run)
    except (FileNotFoundError, ValueError, Error) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if dry_run:
        _echo_json(catalog.to_dict())
        return
    typer.echo(f"Migrated descriptor: {output or descriptor}")


@app.command(
    "download",
    epilog=_examples_epilog(
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
    env_file: Optional[Path] = typer.Option(
        None,
        "--env-file",
        help="Path to .env file for credentials. Defaults to .env in the current directory.",
    ),
) -> None:
    """Download resources from a selector in the descriptor."""
    _load_env_file(env_file)
    descriptor_path = resolve_descriptor_path(descriptor)
    entity_name = _scoped_selector(selector)

    output_dir_path = resolve_output_dir(output_dir, descriptor=descriptor_path)

    _exit_if_descriptor_missing(descriptor_path)

    summary = download_action(
        descriptor=descriptor_path,
        selector=entity_name,
        output_dir=output_dir_path,
        dry_run=dry_run,
        check_auth=check_auth,
        log=typer.echo,
    )
    if not summary.ok:
        raise typer.Exit(code=1)


@auth_app.command(
    "check",
    epilog=_examples_epilog(
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
    _load_env_file(env_file)
    descriptor_path = resolve_descriptor_path(descriptor)
    _exit_if_descriptor_missing(descriptor_path)
    include_values = _parse_include_values(include)
    results = check_auth_action(descriptor=descriptor_path, selector=include_values)
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
    oauth_client_secrets: Optional[Path] = typer.Option(
        None, "--oauth-client-secrets", help="Path to Google OAuth client secrets JSON."
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
    """Run the Google installed-app OAuth flow and optionally persist a token.

    Sample .env for using Google user OAuth with descriptor-based commands such
    as ``sharedrive fetch`` and ``sharedrive download``:

    ```env
    GOOGLE_AUTH_MODE=user_oauth
    # GOOGLE_APPLICATION_CREDENTIALS=.google/service-account.json
    # GOOGLE_SERVICE_ACCOUNT_CREDENTIALS=.google/service-account.json
    GOOGLE_OAUTH_CREDENTIALS=.google/oauth-credentials.json
    GOOGLE_SCOPES=https://www.googleapis.com/auth/drive
    GOOGLE_OAUTH_USE_LOCAL_SERVER=true
    GOOGLE_OAUTH_TOKEN_PATH=.google/oauth-token.json
    ```
    """
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
    epilog=_examples_epilog(
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
    _run_microsoft_login(auth_mode, host_url, scope, env_file)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
