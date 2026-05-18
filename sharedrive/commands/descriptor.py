from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import typer
import yaml
from dplib.error import Error

from sharedrive.commands.toolkit import (
    DESCRIPTOR_DEFAULT_HELP,
    OutputFormat,
    echo_json,
    examples_epilog,
    normalize_update_property,
    normalize_update_value,
    parse_set_args,
    prepare_descriptor_path,
    resolve_resource_reference,
)
from sharedrive.exceptions import GoogleApiError, GraphApiError
from sharedrive.helpers import has_saved_global_descriptor, set_active_descriptor
from sharedrive.models import (
    CATALOG_PROFILE,
    DriveCatalog,
    DriveResource,
    adapter_from_service_type,
    resolve_entity_type,
    resolve_service_type,
)


def _add_resource_to_descriptor(
    descriptor: Path | str,
    *,
    name: str,
    path: str | None = None,
    cache: str | None = None,
    source: str | None = None,
    access_url: str | None = None,
    title: str | None = None,
    description: str | None = None,
    service_type: str | None = None,
    entity_type: str | None = None,
    catalog: bool = False,
    package: bool = False,
    profile: str | None = None,
    create_if_missing: bool = False,
) -> dict[str, Any]:
    def non_empty(value: str, field_name: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field_name} must be a non-empty string")
        return normalized

    descriptor_path = Path(descriptor)
    entity_name = non_empty(name, "name")
    if descriptor_path.exists():
        document = DriveCatalog.from_path(str(descriptor_path))
    elif create_if_missing:
        document = DriveCatalog.empty()
    else:
        raise FileNotFoundError(f"Descriptor '{descriptor_path}' does not exist.")

    normalized_name = entity_name.lower()
    top_level_entries = [*document.resources, *document.packages, *document.catalogs]
    if any(
        str(getattr(entry, "name", "") or "").strip().lower() == normalized_name
        for entry in top_level_entries
    ):
        raise ValueError(f"Entity '{entity_name}' already exists in the descriptor")

    if source is not None and path is not None and cache is None and not catalog:
        cache = path
        path = source
    if source is not None and access_url is None and catalog:
        access_url = source
    if package:
        raise ValueError(
            "Remote folders are now catalogs. Use catalog=True/--catalog instead of package=True/--package."
        )

    if catalog:
        folder_url = non_empty(access_url or path or "", "accessURL")
        resolved_service_type = resolve_service_type(folder_url, service_type=service_type)
        resolved_entity_type = resolve_entity_type(
            folder_url,
            service_type=resolved_service_type,
            entity_type=entity_type or "Directory",
        )
        if resolved_entity_type not in {"Directory", "Container"}:
            raise ValueError("Catalog entries must use entityType Directory or Container.")

        payload: dict[str, Any] = {
            "name": entity_name,
            "accessURL": folder_url,
            "serviceType": resolved_service_type,
            "entityType": resolved_entity_type,
            "resources": [],
            "catalogs": [],
        }
        if title:
            payload["title"] = title.strip()
        if description:
            payload["description"] = description.strip()
        if profile:
            payload["profile"] = profile.strip()

        entry = DriveCatalog.model_validate(payload)
        document.catalogs.append(entry)
        descriptor_path.parent.mkdir(parents=True, exist_ok=True)
        document.to_path(str(descriptor_path))
        return entry.to_dict()

    resource_path = non_empty(path or "", "path")
    resource_cache = non_empty(cache or "", "cache")
    resolved_service_type = resolve_service_type(
        resource_path, service_type=service_type
    )
    resolved_entity_type = resolve_entity_type(
        resource_path,
        service_type=resolved_service_type,
        entity_type=entity_type or "File",
    )
    if resolved_entity_type != "File":
        raise ValueError(
            "Non-file drive entries should be added as catalogs with accessURL."
        )

    payload: dict[str, Any] = {
        "name": entity_name,
        "path": resource_path,
        "_cache": resource_cache,
        "serviceType": resolved_service_type,
        "entityType": resolved_entity_type,
    }
    if title:
        payload["title"] = title.strip()
    if description:
        payload["description"] = description.strip()
    if profile:
        payload["profile"] = profile.strip()

    entry = DriveResource.model_validate(payload)
    document.resources.append(entry)
    descriptor_path.parent.mkdir(parents=True, exist_ok=True)
    document.to_path(str(descriptor_path))
    return entry.to_dict()


def _migrate_descriptor(
    descriptor: Path | str,
    *,
    output: Path | str | None = None,
    dry_run: bool = False,
) -> DriveCatalog:
    descriptor_path = Path(descriptor)
    text = descriptor_path.read_text(encoding="utf-8")
    document = (
        json.loads(text)
        if descriptor_path.suffix.lower() == ".json"
        else yaml.safe_load(text)
    )
    if not isinstance(document, dict):
        raise ValueError(f"Descriptor '{descriptor_path}' must contain an object.")

    def first_source(entry: dict[str, Any]) -> dict[str, Any]:
        sources = entry.get("sources")
        if isinstance(sources, list) and sources and isinstance(sources[0], dict):
            return sources[0]
        return {}

    def resource(entry: dict[str, Any]) -> dict[str, Any]:
        source = first_source(entry)
        cache = entry.get("_cache") or entry.get("path")
        migrated = {
            key: value
            for key, value in entry.items()
            if key not in {"sources", "syncTarget", "targets", "target", "resources"}
        }
        migrated["path"] = source.get("path") or entry.get("path")
        if cache:
            migrated["_cache"] = cache
        migrated["serviceType"] = entry.get("serviceType") or source.get("serviceType")
        migrated["entityType"] = (
            entry.get("entityType") or source.get("entityType") or "File"
        )
        return {key: value for key, value in migrated.items() if value is not None}

    def catalog(entry: dict[str, Any]) -> dict[str, Any]:
        source = first_source(entry)
        migrated = {
            key: value
            for key, value in entry.items()
            if key
            not in {
                "accessUrl",
                "sources",
                "syncTarget",
                "targets",
                "target",
                "path",
                "resources",
                "packages",
                "catalogs",
            }
        }
        migrated["accessURL"] = (
            entry.get("accessURL") or source.get("path") or entry.get("path")
        )
        migrated["serviceType"] = entry.get("serviceType") or source.get("serviceType")
        migrated["entityType"] = (
            entry.get("entityType") or source.get("entityType") or "Directory"
        )
        migrated["resources"] = [
            resource(item)
            for item in entry.get("resources", [])
            if isinstance(item, dict)
        ]
        migrated["catalogs"] = [
            catalog(item)
            for item in [*entry.get("catalogs", []), *entry.get("packages", [])]
            if isinstance(item, dict)
        ]
        return {key: value for key, value in migrated.items() if value is not None}

    migrated = {
        "$schema": document.get("$schema", CATALOG_PROFILE),
        "resources": [
            resource(item)
            for item in document.get("resources", [])
            if isinstance(item, dict)
        ],
        "packages": [],
        "catalogs": [
            catalog(item)
            for item in [*document.get("catalogs", []), *document.get("packages", [])]
            if isinstance(item, dict)
        ],
    }
    for key in ("name", "title", "description"):
        if key in document:
            migrated[key] = document[key]

    catalog = DriveCatalog.model_validate(migrated)
    if not dry_run:
        catalog.to_path(str(Path(output) if output is not None else descriptor_path))
    return catalog


def register_descriptor_commands(app: typer.Typer, clone_app: typer.Typer) -> None:
    @clone_app.command(
        "descriptor",
        epilog=examples_epilog(
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
        source_descriptor = prepare_descriptor_path(descriptor)
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
        epilog=examples_epilog(
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
        parsed = parse_set_args(list(ctx.args))
        if not parsed:
            raise typer.BadParameter("Provide one or more field values to update.")

        descriptor_path = prepare_descriptor_path(descriptor)

        descriptor_model = DriveCatalog.from_path(str(descriptor_path))
        document = descriptor_model.to_dict()
        target_label = str(descriptor_path)
        target: dict[str, Any] = document
        if resource is not None:
            try:
                descriptor_model.assert_valid_entity_paths()
            except Error as exc:
                raise typer.BadParameter(str(exc)) from exc
            resolved = resolve_resource_reference(resource, descriptor_model)
            target = DriveCatalog.get_json_pointer_value(
                document, resolved.json_pointer
            )
            if not isinstance(target, dict):
                raise typer.BadParameter(
                    f"Resolved resource '{resolved.name_path}' is not an object."
                )
            target_label = f"{resolved.name_path} in {descriptor_path}"

        changed_properties: list[str] = []
        for property_name, raw_value in parsed.items():
            property_path = normalize_update_property(
                property_name, resource_target=resource is not None
            )
            value = normalize_update_value(property_path, raw_value)
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
        epilog=examples_epilog(
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
        """Activate a descriptor and optionally an entity within it for later commands."""
        try:
            descriptor_path = set_active_descriptor(descriptor, entity=entity)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        if entity and entity.strip():
            typer.echo(f"Checked out entity '{entity.strip()}' in {descriptor_path}")
        else:
            typer.echo(f"Checked out descriptor: {descriptor_path}")

    @app.command(
        "list",
        epilog=examples_epilog(
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
        descriptor_path = prepare_descriptor_path(descriptor)

        try:
            model = DriveCatalog.from_path(str(descriptor_path))
            model.assert_valid_entity_paths()
            references = model.iter_entity_paths(include_self=False)
        except (FileNotFoundError, ValueError, Error) as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc

        def entity_dict(reference) -> dict[str, Any]:
            item = reference.model
            service_type = getattr(item, "serviceType", None)
            return {
                "name": reference.name_path.split(".")[-1],
                "path": reference.name_path,
                "jsonPointer": reference.json_pointer,
                "type": reference.entity_type,
                "resourcePath": getattr(item, "path", None),
                "_cache": getattr(item, "cache", None),
                "accessURL": getattr(item, "accessURL", None),
                "adapter": adapter_from_service_type(service_type),
                "serviceType": service_type,
                "entityType": getattr(item, "entityType", None),
            }

        if output_format == OutputFormat.JSON:
            echo_json({
                "descriptor": descriptor_path.as_posix(),
                "entities": [entity_dict(reference) for reference in references],
            })
            return

        from rich.console import Console
        from rich.tree import Tree

        root = Tree(descriptor_path.name)
        nodes: dict[str, Any] = {}
        for reference in references:
            entity = entity_dict(reference)
            parent_path = entity["path"].rpartition(".")[0]
            parent_node = nodes.get(parent_path, root) if parent_path else root
            label = (
                f"{entity['name']} ({entity['type']}) "
                f"[dim]{entity['path']} {entity['jsonPointer']}[/dim]"
            )
            node = parent_node.add(label)
            nodes[entity["path"]] = node
            details = []
            if entity["resourcePath"]:
                details.append(f"path={entity['resourcePath']}")
            if entity["_cache"]:
                details.append(f"_cache={entity['_cache']}")
            if entity["accessURL"]:
                details.append(f"accessURL={entity['accessURL']}")
            if entity["serviceType"]:
                details.append(f"serviceType={entity['serviceType']}")
            if entity["entityType"]:
                details.append(f"entityType={entity['entityType']}")
            if details:
                node.add("[dim]" + ", ".join(details) + "[/dim]")

        Console().print(root)

    @app.command(
        "add",
        epilog=examples_epilog(
            "sharedrive add my-resource --path https://drive.google.com/file/d/123... --cache downloads/file.csv",
            "sharedrive add my-folder --catalog --access-url https://drive.google.com/drive/folders/abc...",
        ),
    )
    def add(
        name: str = typer.Argument(
            ..., help="Resource name to store in the descriptor."
        ),
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
            False, "--catalog", help="Treat as a catalog with accessURL."
        ),
        profile: Optional[str] = typer.Option(
            None, "--profile", help="Optional metadata profile for the resource."
        ),
        descriptor: Optional[Path] = typer.Option(
            None, "--descriptor", help=DESCRIPTOR_DEFAULT_HELP
        ),
    ) -> None:
        """Add a standards-aligned resource or catalog entry to a descriptor."""
        descriptor_path = prepare_descriptor_path(
            descriptor,
            require_exists=descriptor is not None or has_saved_global_descriptor(),
        )
        explicit_descriptor = descriptor is not None or has_saved_global_descriptor()

        try:
            resource = _add_resource_to_descriptor(
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
        "migrate",
        epilog=examples_epilog(
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
            catalog = _migrate_descriptor(descriptor, output=output, dry_run=dry_run)
        except (FileNotFoundError, ValueError, Error) as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc

        if dry_run:
            echo_json(catalog.to_dict())
            return
        typer.echo(f"Migrated descriptor: {output or descriptor}")


__all__ = ["register_descriptor_commands"]
