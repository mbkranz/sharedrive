
from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import typer
from dotenv import find_dotenv, load_dotenv

from sharedrive.clients.aws import download_s3_url
from sharedrive.actions.add import add_resource_to_descriptor
from sharedrive.actions.download import check_auth_for_descriptor, download_from_descriptor
from sharedrive.actions.fetch import fetch_resource_metadata_in_descriptor
from sharedrive.descriptor import (
    DESCRIPTOR_DEFAULTS_FILE,
    check_descriptor_exists,
    get_descriptor_resources,
    get_package_resources,
    load_descriptor_defaults_store,
    load_descriptor_document,
    normalize_service_type,
    resolve_descriptor_path,
    resolve_output_dir,
    save_descriptor_defaults_store,
)

try:
    from cloudpathlib import S3Path
except ImportError:  # pragma: no cover
    S3Path = None

if TYPE_CHECKING:  # pragma: no cover
    from sharedrive.clients.googledrive import GoogleDriveClient
    from sharedrive.clients.sharepoint import SharepointClient

load_dotenv(find_dotenv(usecwd=True))

app = typer.Typer(
    name="sharedrive",
    help="Shared drive utilities for SharePoint, Google Drive, and S3.",
    rich_markup_mode="markdown",
)
clone_app = typer.Typer(
    help="Clone descriptor state for new local variants.",
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
    help="SharePoint commands (`spo` is alias for `sharepoint`).",
    rich_markup_mode="markdown",
)
s3_app = typer.Typer(
    help="S3 commands.",
    rich_markup_mode="markdown",
)
app.add_typer(auth_app, name="auth")
app.add_typer(clone_app, name="clone")
auth_app.add_typer(auth_login_app, name="login")
app.add_typer(gdrive_app, name="gdrive")
app.add_typer(sharepoint_app, name="sharepoint")
app.add_typer(sharepoint_app, name="spo")
app.add_typer(s3_app, name="s3")


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
    from sharedrive.clients.googledrive import GoogleDriveClient

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


def _set_saved_scope(parsed: dict[str, Any], descriptor: Optional[Path], global_scope: bool) -> str:
    if global_scope and descriptor is not None:
        raise typer.BadParameter("Use either <descriptor> or --global, not both.")

    store = load_descriptor_defaults_store()
    if global_scope:
        target = "global"
        scope = store.setdefault("global", {})
    else:
        if descriptor is None:
            raise typer.BadParameter("Provide <descriptor> or use --global.")
        target = str(descriptor)
        descriptors = store.setdefault("descriptors", {})
        scope = descriptors.setdefault(target, {})

    if not isinstance(scope, dict):
        scope = {}
        if global_scope:
            store["global"] = scope
        else:
            store.setdefault("descriptors", {})[target] = scope

    scope.update(parsed)
    save_descriptor_defaults_store(store)
    return target


def _has_saved_global_descriptor() -> bool:
    store = load_descriptor_defaults_store()
    global_scope = store.get("global")
    if not isinstance(global_scope, dict):
        return False

    descriptor_value = global_scope.get("descriptor")
    return isinstance(descriptor_value, str) and bool(descriptor_value.strip())


def _set_active_descriptor(descriptor_path: Path) -> Path:
    if not check_descriptor_exists(descriptor_path):
        raise typer.BadParameter(f"Descriptor '{descriptor_path}' does not exist.")

    store = load_descriptor_defaults_store()
    global_scope = store.setdefault("global", {})
    if not isinstance(global_scope, dict):
        global_scope = {}
        store["global"] = global_scope

    global_scope["descriptor"] = descriptor_path.as_posix()
    save_descriptor_defaults_store(store)
    return descriptor_path


def _iter_resource_references(
    resources: list[dict[str, Any]],
    *,
    parent_path: str | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    references: list[tuple[str, dict[str, Any]]] = []
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        name = str(resource.get("name", "")).strip()
        if not name:
            continue

        selector_path = name if parent_path is None else f"{parent_path}.{name}"
        references.append((selector_path, resource))

        children = get_package_resources(resource)
        if children:
            references.extend(
                _iter_resource_references(
                    children,
                    parent_path=selector_path,
                )
            )

    return references


def _resolve_exact_resource_reference(
    resource_selector: str,
    resources: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    references = _iter_resource_references(resources)
    normalized_selector = resource_selector.strip().lower()
    if not normalized_selector:
        raise typer.BadParameter("Resource selector must be a non-empty string.")

    matches = [
        (path, resource)
        for path, resource in references
        if path.lower() == normalized_selector or path.split(".")[-1].lower() == normalized_selector
    ]

    if matches:
        unique_matches = {(path, id(resource)): (path, resource) for path, resource in matches}
        resolved_matches = list(unique_matches.values())
        if len(resolved_matches) > 1 and "." not in resource_selector:
            raise typer.BadParameter(
                f'Resource selector "{resource_selector}" is ambiguous. Use the full dot-path selector.'
            )
        return resolved_matches[0]

    raise typer.BadParameter(f'Resource selector "{resource_selector}" was not found.')


def _normalize_update_property(property_name: str, *, resource_target: bool) -> str:
    normalized = property_name.strip()
    if not normalized:
        raise typer.BadParameter("Property name must be a non-empty string.")

    normalized = {
        "service-type": "serviceType",
        "entity-type": "entityType",
        "sync-target": "syncTarget",
        "drive-service": "driveService",
    }.get(normalized, normalized)

    if not resource_target:
        return normalized

    aliases = {
        "source": "sources.0.path",
        "serviceType": "sources.0.serviceType",
        "driveService": "sources.0.serviceType",
        "entityType": "sources.0.entityType",
    }
    return aliases.get(normalized, normalized)


def _normalize_update_value(property_path: str, value: Any) -> Any:
    if property_path == "syncTarget" and isinstance(value, str):
        from sharedrive.descriptor import normalize_sync_target

        return normalize_sync_target(value)
    if property_path == "sources.0.serviceType" and isinstance(value, str):
        return normalize_service_type(value)
    if property_path == "sources.0.entityType" and isinstance(value, str):
        from sharedrive.descriptor import normalize_entity_type

        return normalize_entity_type(value)
    return value


def _set_nested_property(target: Any, property_path: str, value: Any) -> bool:
    parts = [part.strip() for part in property_path.split(".") if part.strip()]
    if not parts:
        raise typer.BadParameter("Property name must be a non-empty string.")

    current = target
    for segment in parts[:-1]:
        if isinstance(current, list):
            if not segment.isdigit():
                raise typer.BadParameter(
                    f"List segment '{segment}' in property '{property_path}' must be a numeric index."
                )
            index = int(segment)
            if index >= len(current):
                raise typer.BadParameter(
                    f"List index {index} is out of range for property '{property_path}'."
                )
            current = current[index]
            continue

        if not isinstance(current, dict):
            raise typer.BadParameter(
                f"Cannot descend into property '{segment}' while updating '{property_path}'."
            )

        next_value = current.get(segment)
        if next_value is None:
            next_value = {}
            current[segment] = next_value
        current = next_value

    leaf = parts[-1]
    if isinstance(current, list):
        if not leaf.isdigit():
            raise typer.BadParameter(
                f"List segment '{leaf}' in property '{property_path}' must be a numeric index."
            )
        index = int(leaf)
        if index >= len(current):
            raise typer.BadParameter(
                f"List index {index} is out of range for property '{property_path}'."
            )
        if current[index] == value:
            return False
        current[index] = value
        return True

    if not isinstance(current, dict):
        raise typer.BadParameter(f"Cannot set property '{property_path}' on a non-object value.")
    if current.get(leaf) == value:
        return False
    current[leaf] = value
    return True


def _exit_if_descriptor_missing(descriptor_path: Path) -> None:
    if check_descriptor_exists(descriptor_path):
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
    target_path: Path = typer.Argument(..., help="Target descriptor path for the clone."),
    descriptor: Optional[Path] = typer.Option(None, "--descriptor", help=DESCRIPTOR_DEFAULT_HELP),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be cloned without writing files."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing target descriptor."),
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

    document = load_descriptor_document(source_descriptor)
    from sharedrive.descriptor import save_descriptor_document

    save_descriptor_document(target_path, document)
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
    descriptor: Optional[Path] = typer.Option(None, "--descriptor", help=DESCRIPTOR_DEFAULT_HELP),
    resource: Optional[str] = typer.Option(None, "--resource", help="Exact resource name or dot-path to update."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be updated without writing files."),
) -> None:
    """Update descriptor-root or resource properties using flag-style field edits."""
    parsed = _parse_set_args(list(ctx.args))
    if not parsed:
        raise typer.BadParameter("Provide one or more field values to update.")

    descriptor_path = resolve_descriptor_path(descriptor)
    _exit_if_descriptor_missing(descriptor_path)

    document = load_descriptor_document(descriptor_path)
    target_label = str(descriptor_path)
    target: dict[str, Any] = document
    if resource is not None:
        resolved_path, target = _resolve_exact_resource_reference(
            resource,
            get_descriptor_resources(document),
        )
        target_label = f"{resolved_path} in {descriptor_path}"

    changed_properties: list[str] = []
    for property_name, raw_value in parsed.items():
        property_path = _normalize_update_property(property_name, resource_target=resource is not None)
        value = _normalize_update_value(property_path, raw_value)
        if _set_nested_property(target, property_path, value):
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

    from sharedrive.descriptor import save_descriptor_document

    save_descriptor_document(descriptor_path, document)
    for change in changed_properties:
        typer.echo(f"Updated {target_label}: {change}")


@app.command(
    "checkout",
    epilog=_examples_epilog(
        "sharedrive checkout resources/descriptor.yaml",
    ),
)
def checkout_command(
    descriptor: Path = typer.Argument(..., help="Descriptor path to activate for later commands."),
) -> None:
    """Activate a descriptor for later commands."""
    descriptor_path = _set_active_descriptor(descriptor)
    typer.echo(f"Checked out descriptor: {descriptor_path}")


def _run_download_command(
    descriptor: Path,
    include: str | list[str],
    output_dir: Path,
    dry_run: bool,
    check_auth: bool,
) -> None:
    summary = download_from_descriptor(
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
        None,
        help="Descriptor path to save defaults for.",
    ),
    global_scope: bool = typer.Option(
        False,
        "--global",
        help="Save params as global defaults for all descriptors.",
    ),
    descriptor: Optional[str] = typer.Option(
        None,
        "--descriptor",
        help="Default descriptor path to save.",
    ),
    output_dir: Optional[str] = typer.Option(
        None,
        "--output-dir",
        help="Default output directory to save.",
    ),
) -> None:
    """Set reusable key/value parameters for sharedrive descriptor workflows."""
    parsed = _parse_set_args(list(ctx.args))

    if descriptor_scope is not None and not check_descriptor_exists(descriptor_scope):
        raise typer.BadParameter(
            f"Descriptor '{descriptor_scope}' does not exist.",
            param_hint="<descriptor>",
        )

    if descriptor is not None:
        descriptor_path = Path(descriptor)
        if not check_descriptor_exists(descriptor_path):
            raise typer.BadParameter(
                f"Descriptor '{descriptor_path}' does not exist.",
                param_hint="--descriptor",
            )
        parsed["descriptor"] = descriptor_path.as_posix()
    if output_dir is not None:
        parsed["output_dir"] = output_dir
    if not parsed:
        raise typer.BadParameter("Provide one or more values to save.")

    target = _set_saved_scope(parsed, descriptor_scope, global_scope)
    typer.echo(
        f"Saved {len(parsed)} parameter(s) for '{target}' in {DESCRIPTOR_DEFAULTS_FILE}."
    )


@app.command(
    "add",
    epilog=_examples_epilog(
        "sharedrive add spec-workbook --path background/specs/spec-workbook.xlsx --source https://tenant.sharepoint.com/sites/Test/Shared%20Documents/spec.xlsx",
        "sharedrive add source-export --path background/exports/source-export.csv --source s3://my-bucket/source-export.csv --service-type S3",
        "sharedrive add census-docs --path downloads/census --source https://drive.google.com/drive/folders/<id> --service-type GoogleDrive --entity-type Directory --sync-target resources",
    ),
)
def add(
    name: str = typer.Argument(..., help="Resource name to store in the descriptor."),
    path: str = typer.Option(..., "--path", help="Resource path stored in the descriptor."),
    source: str = typer.Option(..., "--source", help="Source URL/URI/path for the resource."),
    title: Optional[str] = typer.Option(None, "--title", help="Optional resource title."),
    description: Optional[str] = typer.Option(None, "--description", help="Optional resource description."),
    service_type: Optional[str] = typer.Option(None, "--service-type", help="Source serviceType. If omitted, infer from source."),
    entity_type: Optional[str] = typer.Option(None, "--entity-type", help="Source entityType such as File, Directory, or Container."),
    sync_target: Optional[str] = typer.Option(None, "--sync-target", help="Descriptor syncTarget: 'path' or 'resources'."),
    profile: Optional[str] = typer.Option(None, "--profile", help="Optional metadata profile for the resource."),
    descriptor: Optional[Path] = typer.Option(None, "--descriptor", help=DESCRIPTOR_DEFAULT_HELP),
) -> None:
    """Add a resource entry to a descriptor."""
    descriptor_path = resolve_descriptor_path(descriptor)
    explicit_descriptor = descriptor is not None or _has_saved_global_descriptor()
    if explicit_descriptor:
        _exit_if_descriptor_missing(descriptor_path)

    try:
        resource = add_resource_to_descriptor(
            descriptor=descriptor_path,
            name=name,
            path=path,
            source=source,
            title=title,
            description=description,
            service_type=service_type,
            entity_type=entity_type,
            sync_target=sync_target,
            profile=profile,
            create_if_missing=not explicit_descriptor,
        )
    except (FileNotFoundError, NotImplementedError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    primary_source = resource["sources"][0]
    typer.echo(
        f"Added resource '{resource['name']}' to {descriptor_path} "
        f"with serviceType '{primary_source['serviceType']}', "
        f"entityType '{primary_source['entityType']}', and syncTarget '{resource['syncTarget']}'."
    )


@app.command(
    "fetch",
    epilog=_examples_epilog(
        "sharedrive fetch census-package --descriptor resources/descriptor.yaml --dry-run",
        "sharedrive fetch census-package --descriptor resources/descriptor.yaml",
    ),
)
def fetch(
    resource_name: str = typer.Argument(..., help="Top-level resource name whose metadata should be refreshed."),
    descriptor: Optional[Path] = typer.Option(None, "--descriptor", help=DESCRIPTOR_DEFAULT_HELP),
    dry_run: bool = typer.Option(False, help="Preview descriptor changes without writing them."),
    env_file: Optional[Path] = typer.Option(None, "--env-file", help="Path to .env file for credentials. Defaults to .env in the current directory."),
) -> None:
    """Fetch remote metadata for one resource into the descriptor."""
    _load_env_file(env_file)
    descriptor_path = resolve_descriptor_path(descriptor)
    _exit_if_descriptor_missing(descriptor_path)
    try:
        summary = fetch_resource_metadata_in_descriptor(
            descriptor=descriptor_path,
            resource_name=resource_name,
            dry_run=dry_run,
            log=None,
            googledrive_client_factory=lambda: _make_gdrive_client(None),
        )
    except (FileNotFoundError, NotImplementedError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    action = "Would fetch" if summary.dry_run else "Fetched"
    typer.echo(
        f"{action} metadata for {summary.generated_resources} resource(s) into resource '{summary.resource_name}' in {descriptor_path}."
    )


@app.command(
    "download",
    epilog=_examples_epilog(
        "sharedrive download resources/descriptor.yaml --dry-run",
        "sharedrive download resources/descriptor.yaml --include s3 --include sharepoint",
        "sharedrive download resources/descriptor.yaml --include spec-workbook --output-dir resources",
    ),
)
def download(
    descriptor: Optional[Path] = typer.Argument(
        None,
        exists=False,
        help=DESCRIPTOR_DEFAULT_HELP,
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
    output_dir: Optional[Path] = typer.Option(None, help="Base output directory for relative resource paths."),
    dry_run: bool = typer.Option(False, help="Print actions without downloading."),
    check_auth: bool = typer.Option(False, "--check-auth", help="Validate service credentials before downloading."),
    env_file: Optional[Path] = typer.Option(None, "--env-file", help="Path to .env file for credentials. Defaults to .env in the current directory."),
) -> None:
    """Download descriptor resources by adapter type or resource name filters."""
    _load_env_file(env_file)
    descriptor_path = resolve_descriptor_path(descriptor)
    _exit_if_descriptor_missing(descriptor_path)
    include_values = _parse_include_values(include)
    output_dir_path = resolve_output_dir(output_dir, descriptor=descriptor_path)
    _run_download_command(
        descriptor=descriptor_path,
        include=include_values,
        output_dir=output_dir_path,
        dry_run=dry_run,
        check_auth=check_auth,
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
    descriptor: Optional[Path] = typer.Argument(
        None,
        exists=False,
        help=DESCRIPTOR_DEFAULT_HELP,
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
    output_format: OutputFormat = typer.Option(OutputFormat.TEXT, "--format", help="Output format."),
    env_file: Optional[Path] = typer.Option(None, "--env-file", help="Path to .env file for credentials. Defaults to .env in the current directory."),
) -> None:
    """Validate credentials for the adapters selected by a descriptor."""
    _load_env_file(env_file)
    descriptor_path = resolve_descriptor_path(descriptor)
    _exit_if_descriptor_missing(descriptor_path)
    include_values = _parse_include_values(include)
    results = check_auth_for_descriptor(
        descriptor=descriptor_path,
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
