
from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import unquote, urlparse

import typer
from dotenv import find_dotenv, load_dotenv

from sharedrive.actions.add import add_resource_to_descriptor, resolve_entity_type, resolve_service_type
from sharedrive.actions.download import check_auth_for_descriptor, download_from_descriptor
from sharedrive.actions.fetch import fetch_resource_metadata_in_descriptor
from sharedrive.helpers import (
    DESCRIPTOR_DEFAULTS_FILE,
    get_checked_out_entity,
    get_saved_params_for_descriptor,
    load_descriptor_defaults_store,
    resolve_descriptor_path,
    resolve_output_dir,
    save_descriptor_defaults_store,
)
from sharedrive.models import (
    CATALOG_PROFILE,
    DriveCatalog,
    load_drive_descriptor,
    normalize_entity_type,
    normalize_service_type,
    normalize_sync_target,
    save_drive_descriptor,
)

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


def load_descriptor_document(path: Path | str) -> dict[str, Any]:
    """Load descriptor file as a dict, optional fields for CLI manipulation."""
    descriptor_path = Path(path)
    if not descriptor_path.exists():
        return {"$schema": CATALOG_PROFILE, "resources": [], "packages": [], "catalogs": []}
    return load_drive_descriptor(descriptor_path).to_dict()


def save_descriptor_document(path: Path | str, document: dict[str, Any]) -> None:
    """Save descriptor dict back to file via dplib models."""
    save_drive_descriptor(path, DriveCatalog.model_validate(document))


def get_descriptor_resources(
    document: dict[str, Any],
    *,
    create: bool = False,
) -> list[dict[str, Any]]:
    """Get top-level resources array from descriptor dict."""
    resources = document.get("resources")
    if resources is None and create:
        document["resources"] = []
        resources = document["resources"]
    if not isinstance(resources, list):
        raise ValueError("Descriptor must contain a top-level 'resources' array")
    return resources


def get_descriptor_packages(
    document: dict[str, Any],
    *,
    create: bool = False,
) -> list[dict[str, Any]]:
    """Get top-level packages array from descriptor dict."""
    packages = document.get("packages")
    if packages is None and create:
        document["packages"] = []
        packages = document["packages"]
    if packages is None:
        return []
    if not isinstance(packages, list):
        raise ValueError("Descriptor must contain a top-level 'packages' array")
    return packages


def get_descriptor_catalogs(
    document: dict[str, Any],
    *,
    create: bool = False,
) -> list[dict[str, Any]]:
    """Get top-level catalogs array from descriptor dict."""
    catalogs = document.get("catalogs")
    if catalogs is None and create:
        document["catalogs"] = []
        catalogs = document["catalogs"]
    if catalogs is None:
        return []
    if not isinstance(catalogs, list):
        raise ValueError("Descriptor must contain a top-level 'catalogs' array")
    return catalogs


def get_package_resources(
    resource: dict[str, Any],
    *,
    create: bool = False,
) -> list[dict[str, Any]]:
    """Get nested resources array from a resource dict."""
    resources = resource.get("resources")
    if resources is None:
        if create:
            resource["resources"] = []
            return resource["resources"]
        return []
    if not isinstance(resources, list):
        raise ValueError("Resource must contain a 'resources' array")
    return resources


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


def _set_active_descriptor(descriptor_path: Path, *, entity: str | None = None) -> Path:
    if not descriptor_path.exists():
        raise typer.BadParameter(f"Descriptor '{descriptor_path}' does not exist.")

    store = load_descriptor_defaults_store()
    global_scope = store.setdefault("global", {})
    if not isinstance(global_scope, dict):
        global_scope = {}
        store["global"] = global_scope

    global_scope["descriptor"] = descriptor_path.as_posix()
    if entity is not None and entity.strip():
        global_scope["entity"] = entity.strip()
    else:
        global_scope.pop("entity", None)
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


def _iter_catalog_references(
    document: dict[str, Any],
    *,
    parent_path: str | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    references = _iter_resource_references(
        get_descriptor_resources(document),
        parent_path=parent_path,
    )

    for package in get_descriptor_packages(document):
        if not isinstance(package, dict):
            continue
        name = str(package.get("name", "")).strip()
        if not name:
            continue

        selector_path = name if parent_path is None else f"{parent_path}.{name}"
        references.append((selector_path, package))
        references.extend(
            _iter_resource_references(
                get_package_resources(package),
                parent_path=selector_path,
            )
        )

    for catalog in get_descriptor_catalogs(document):
        if not isinstance(catalog, dict):
            continue
        name = str(catalog.get("name", "")).strip()
        if not name:
            continue

        selector_path = name if parent_path is None else f"{parent_path}.{name}"
        references.append((selector_path, catalog))
        references.extend(_iter_catalog_references(catalog, parent_path=selector_path))

    return references


def _resolve_exact_resource_reference(
    resource_selector: str,
    document: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    references = _iter_catalog_references(document)
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
        return normalize_sync_target(value)
    if property_path == "sources.0.serviceType" and isinstance(value, str):
        return normalize_service_type(value)
    if property_path == "sources.0.entityType" and isinstance(value, str):
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
            document,
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

    save_descriptor_document(descriptor_path, document)
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
    descriptor: Path = typer.Argument(..., help="Descriptor path to activate for later commands."),
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
    descriptor_path = _set_active_descriptor(descriptor, entity=entity)
    if entity and entity.strip():
        typer.echo(f"Checked out entity '{entity.strip()}' in {descriptor_path}")
    else:
        typer.echo(f"Checked out descriptor: {descriptor_path}")


def _run_download_command(
    descriptor: Path,
    package_name: str,
    output_dir: Path,
    dry_run: bool,
    check_auth: bool,
) -> None:
    summary = download_from_descriptor(
        descriptor=descriptor,
        include=package_name,
        output_dir=output_dir,
        dry_run=dry_run,
        check_auth=check_auth,
        log=typer.echo,
        sharepoint_client_factory=_make_sharepoint_client,
        googledrive_client_factory=lambda: _make_gdrive_client(None),
    )
    if not summary.ok:
        raise typer.Exit(code=1)


def _source_locator_parts(source_path: str) -> list[str]:
    parsed = urlparse(source_path)
    path_parts = [part for part in Path(unquote(parsed.path)).parts if part not in {"/", ""}]
    return path_parts


def _derive_source_resource_name(source_path: str, requested_name: str | None) -> str:
    if requested_name is not None and requested_name.strip():
        return requested_name.strip()

    parts = _source_locator_parts(source_path)
    if not parts:
        parsed = urlparse(source_path)
        if parsed.scheme == "s3" and parsed.netloc:
            return parsed.netloc
        raise typer.BadParameter("Could not derive a resource name from --source-path. Use --resource.")

    leaf = parts[-1]
    if leaf.lower() in {"edit", "view"} and len(parts) > 1:
        leaf = parts[-2]
    return leaf.strip() or "resource"


def _derive_descriptor_resource_path(
    source_path: str,
    *,
    resource_name: str,
    entity_type: str,
    sync_target: str,
) -> str:
    parts = _source_locator_parts(source_path)
    leaf = parts[-1] if parts else resource_name
    if leaf.lower() in {"edit", "view"} and len(parts) > 1:
        leaf = parts[-2]

    if sync_target == "resources":
        return (Path("downloads") / resource_name).as_posix()
    if entity_type in {"Directory", "Container"}:
        return (Path("downloads") / resource_name).as_posix()
    return (Path("downloads") / leaf).as_posix()


def _upsert_source_resource(
    descriptor_path: Path,
    *,
    source_path: str,
    resource_name: str,
    sync_target: str,
    dry_run: bool,
) -> tuple[dict[str, Any], str]:
    service_type = resolve_service_type(source_path)
    entity_type = resolve_entity_type(source_path, service_type=service_type)
    resource_path = _derive_descriptor_resource_path(
        source_path,
        resource_name=resource_name,
        entity_type=entity_type,
        sync_target=sync_target,
    )

    document = load_descriptor_document(descriptor_path)
    target_collection = (
        get_descriptor_packages(document, create=True)
        if sync_target == "resources"
        else get_descriptor_resources(document, create=True)
    )
    normalized_name = resource_name.strip().lower()
    existing = next(
        (
            resource
            for resource in [
                *get_descriptor_resources(document),
                *get_descriptor_packages(document),
            ]
            if isinstance(resource, dict)
            and str(resource.get("name", "")).strip().lower() == normalized_name
        ),
        None,
    )

    resource_payload = {
        "name": resource_name,
        "path": resource_path,
        "syncTarget": sync_target,
        "sources": [
            {
                "path": source_path,
                "serviceType": service_type,
                "entityType": entity_type,
            }
        ],
    }
    if sync_target == "resources":
        resource_payload["resources"] = []

    action = "updated" if existing is not None else "added"
    if existing is not None:
        existing.clear()
        existing.update(resource_payload)
        resource_ref = existing
    else:
        target_collection.append(resource_payload)
        resource_ref = resource_payload

    if not dry_run:
        save_descriptor_document(descriptor_path, document)

    return resource_ref, action


def _run_direct_source_download(
    *,
    descriptor_path: Path,
    source_path: str,
    resource_name: str | None,
    output_dir: Path,
    dry_run: bool,
    check_auth: bool,
) -> None:
    resolved_name = _derive_source_resource_name(source_path, resource_name)
    resource, action = _upsert_source_resource(
        descriptor_path,
        source_path=source_path,
        resource_name=resolved_name,
        sync_target="path",
        dry_run=dry_run,
    )
    if dry_run:
        typer.echo(
            f"Would {action} resource '{resolved_name}' in {descriptor_path} and download {source_path} to {output_dir / Path(str(resource['path']))}."
        )
        return

    typer.echo(f"{action.capitalize()} resource '{resolved_name}' in {descriptor_path}.")
    _run_download_command(
        descriptor=descriptor_path,
        include=[resolved_name],
        output_dir=output_dir,
        dry_run=False,
        check_auth=check_auth,
    )


def _run_direct_source_fetch(
    *,
    descriptor_path: Path,
    source_path: str,
    resource_name: str | None,
    dry_run: bool,
) -> None:
    resolved_name = _derive_source_resource_name(source_path, resource_name)
    _, action = _upsert_source_resource(
        descriptor_path,
        source_path=source_path,
        resource_name=resolved_name,
        sync_target="resources",
        dry_run=dry_run,
    )
    if dry_run:
        typer.echo(
            f"Would {action} resource '{resolved_name}' in {descriptor_path} and fetch remote metadata from {source_path}."
        )
        return

    typer.echo(f"{action.capitalize()} resource '{resolved_name}' in {descriptor_path}.")
    summary = fetch_resource_metadata_in_descriptor(
        descriptor=descriptor_path,
        resource_name=resolved_name,
        dry_run=False,
        log=None,
        googledrive_client_factory=lambda: _make_gdrive_client(None),
        sharepoint_client_factory=_make_sharepoint_client,
    )
    typer.echo(
        f"Fetched metadata for {summary.generated_resources} resource(s) into resource '{summary.resource_name}' in {descriptor_path}."
    )


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

@app.command(
    "add",
    epilog=_examples_epilog(
        "sharedrive add my-resource --path /data/file.csv --source https://drive.google.com/file/d/123...",
        "sharedrive add my-package --package --path /data/ --source https://drive.google.com/drive/folders/abc...",
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
    package: bool = typer.Option(False, "--package", help="Treat as a package (creates a resource with nested resources)."),
    catalog: bool = typer.Option(False, "--catalog", help="Treat as a catalog (alias for package, future extension)."),
    profile: Optional[str] = typer.Option(None, "--profile", help="Optional metadata profile for the resource."),
    descriptor: Optional[Path] = typer.Option(None, "--descriptor", help=DESCRIPTOR_DEFAULT_HELP),
) -> None:
    """Add a resource or package entry to a descriptor."""
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
            package=package or catalog,
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
        f"entityType '{primary_source['entityType']}'."
        + (" (package)" if "resources" in resource else "")
    )


@app.command(
    "fetch",
    epilog=_examples_epilog(
        "sharedrive fetch # get metadata for the default selector in the checked-out descriptor",
        "sharedrive fetch census-package --descriptor resources/descriptor.yaml --dry-run",
        "sharedrive fetch census-package --descriptor resources/descriptor.yaml",
        "sharedrive fetch --source-path https://drive.google.com/drive/folders/<id> --resource my-package",
    ),
)
def fetch(
    selector: Optional[str] = typer.Argument(None, help="Resource selector to fetch metadata for. If omitted, uses the checked-out descriptor."),
    descriptor: Optional[Path] = typer.Option(None, "--descriptor", help=DESCRIPTOR_DEFAULT_HELP),
    source_path: Optional[str] = typer.Option(None, "--source-path", help="Direct source URL/URI to add or update before fetching metadata."),
    resource: Optional[str] = typer.Option(None, "--resource", help="Resource name to use with --source-path."),
    dry_run: bool = typer.Option(False, help="Preview descriptor changes without writing them."),
    env_file: Optional[Path] = typer.Option(None, "--env-file", help="Path to .env file for credentials. Defaults to .env in the current directory."),
) -> None:
    """Fetch remote metadata for one selector into the descriptor."""
    _load_env_file(env_file)
    descriptor_path = resolve_descriptor_path(descriptor)

    if source_path is not None:
        _run_direct_source_fetch(
            descriptor_path=descriptor_path,
            source_path=source_path,
            resource_name=resource,
            dry_run=dry_run,
        )
        return

    _exit_if_descriptor_missing(descriptor_path)

    # Resolve the effective selector from the argument and the checked-out entity.
    # The checked-out entity (set via `sharedrive checkout DESCRIPTOR ENTITY`) acts
    # as the current scope:
    #   - No selector arg → operate on the whole checked-out entity.
    #   - Selector arg    → treat it as a path relative to the checked-out entity.
    #   - No entity and no selector arg → error.
    checked_out_entity = get_checked_out_entity()
    if selector is None:
        if checked_out_entity:
            selector_name = checked_out_entity
        else:
            typer.echo(
                "Error: a selector is required. Pass it as an argument or check out an entity with "
                "'sharedrive checkout DESCRIPTOR ENTITY'.",
                err=True,
            )
            raise typer.Exit(code=1)
    else:
        selector_name = f"{checked_out_entity}.{selector}" if checked_out_entity else selector

    try:
        summary = fetch_resource_metadata_in_descriptor(
            descriptor=descriptor_path,
            resource_name=selector_name,
            dry_run=dry_run,
            log=None,
            googledrive_client_factory=lambda: _make_gdrive_client(None),
            sharepoint_client_factory=_make_sharepoint_client,
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
        "sharedrive download --dry-run",
        "sharedrive download my-package --descriptor resources/descriptor.yaml",
        "sharedrive download my-package --output-dir resources",
    ),
)
def download(
    selector: Optional[str] = typer.Argument(None, help="Selector to download. If omitted, uses the checked-out descriptor."),
    descriptor: Optional[Path] = typer.Option(None, "--descriptor", help=DESCRIPTOR_DEFAULT_HELP),
    source_path: Optional[str] = typer.Option(None, "--source-path", help="Direct source URL/URI to add or update before downloading."),
    resource: Optional[str] = typer.Option(None, "--resource", help="Resource name to use with --source-path."),
    output_dir: Optional[Path] = typer.Option(None, help="Base output directory for relative resource paths."),
    dry_run: bool = typer.Option(False, help="Print actions without downloading."),
    check_auth: bool = typer.Option(False, "--check-auth", help="Validate service credentials before downloading."),
    env_file: Optional[Path] = typer.Option(None, "--env-file", help="Path to .env file for credentials. Defaults to .env in the current directory."),
) -> None:
    """Download resources from a selector in the descriptor."""
    _load_env_file(env_file)
    descriptor_path = resolve_descriptor_path(descriptor)

    # Resolve the effective selector from the argument and the checked-out entity.
    # Mirrors the fetch command: the checked-out entity provides the scope and a
    # selector argument is interpreted as a path relative to that entity.
    checked_out_entity = get_checked_out_entity()
    if selector is None:
        package_name = checked_out_entity  # may remain None → checked later
    else:
        package_name = f"{checked_out_entity}.{selector}" if checked_out_entity else selector

    output_dir_path = resolve_output_dir(output_dir, descriptor=descriptor_path)

    if source_path is not None:
        _run_direct_source_download(
            descriptor_path=descriptor_path,
            source_path=source_path,
            resource_name=resource,
            output_dir=output_dir_path,
            dry_run=dry_run,
            check_auth=check_auth,
        )
        return

    _exit_if_descriptor_missing(descriptor_path)

    if package_name is None:
        typer.echo(
            "Error: a selector is required. Pass it as an argument or check out an entity with "
            "'sharedrive checkout DESCRIPTOR ENTITY'.",
            err=True,
        )
        raise typer.Exit(code=1)

    _run_download_command(
        descriptor=descriptor_path,
        package_name=package_name,
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
