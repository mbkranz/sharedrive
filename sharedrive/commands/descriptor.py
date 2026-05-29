from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import typer
from dplib.error import Error

from sharedrive.commands.toolkit import (
    DESCRIPTOR_DEFAULT_HELP,
    OutputFormat,
    echo_json,
    examples_epilog,
    parse_set_args,
    prepare_descriptor_path,
)
from sharedrive.exceptions import GoogleApiError, GraphApiError
from sharedrive.helpers import has_saved_global_descriptor, set_active_descriptor
from sharedrive.models import (
    DriveCatalog,
    DriveRemoteResource,
    adapter_from_service_type,
    resolve_entity_type,
    resolve_service_type,
)



def _add_resource_to_descriptor(
    descriptor: Path | str,
    *,
    name: str,
    create_if_missing: bool = False,
    catalog: bool = False,
    package: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    descriptor_path = Path(descriptor)
    entity_name = name.strip()
    if not entity_name:
        raise ValueError("name must be a non-empty string")

    if descriptor_path.exists():
        document = DriveCatalog.from_path(str(descriptor_path))
    elif create_if_missing:
        document = DriveCatalog()
    else:
        raise FileNotFoundError(f"Descriptor '{descriptor_path}' does not exist.")

    normalized_name = entity_name.lower()
    top_level_entries = [*document.resources, *document.packages, *document.catalogs]
    if any(
        str(getattr(entry, "name", "") or "").strip().lower() == normalized_name
        for entry in top_level_entries
    ):
        raise ValueError(f"Entity '{entity_name}' already exists in the descriptor")

    # Map legacy aliases
    if "source" in kwargs:
        url = kwargs.pop("source")
        if catalog:
            kwargs.setdefault("accessURL", url)
        else:
            kwargs.setdefault("path", url)
            kwargs.setdefault("cache", url)
    if "access_url" in kwargs:
        kwargs.setdefault("accessURL", kwargs.pop("access_url"))
        
    url = kwargs.get("accessURL") if catalog else kwargs.get("path")
    if not url:
        raise ValueError("A source URL must be provided via --path, --accessURL, or --source")

    resolved_service_type = resolve_service_type(url, service_type=kwargs.get("serviceType"))
    
    kwargs["entityType"] = resolve_entity_type(
        url,
        service_type=resolved_service_type,
        entity_type=kwargs.get("entityType"),
    )

    kwargs["serviceType"] = resolved_service_type
    kwargs["name"] = entity_name

    if catalog:
        if kwargs["entityType"] not in {"Directory", "Container"}:
            raise ValueError("Catalog entries must use entityType Directory or Container.")
        entry = DriveCatalog.model_validate(kwargs)
        document.catalogs.append(entry)
    else:
        if kwargs["entityType"] != "File":
            raise ValueError("Non-file drive entries should be added as catalogs with accessURL.")
        
        # Backward compatibility translation of cache mapped correctly in BaseModel
        if "_cache" not in kwargs and "cache" in kwargs:
            kwargs["_cache"] = kwargs.pop("cache")
            
        entry = DriveRemoteResource.model_validate(kwargs)
        document.resources.append(entry)

    descriptor_path.parent.mkdir(parents=True, exist_ok=True)
    document.to_path(str(descriptor_path))
    return entry.to_dict()


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
            'sharedrive update --name file1 --title "Hello" --description "hello"',
            'sharedrive update --descriptor resources/descriptor.yaml --name file1 --title "Hello"',
        ),
    )
    def update_command(
        ctx: typer.Context,
        descriptor: Optional[Path] = typer.Option(
            None, "--descriptor", help=DESCRIPTOR_DEFAULT_HELP
        ),
        name: Optional[str] = typer.Option(
            None, "--name", help="Exact entity name or dot-path to update."
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
        if name is not None:
            try:
                descriptor_model.assert_valid_entity_paths()
            except Error as exc:
                raise typer.BadParameter(str(exc)) from exc
            resolved = getattr(descriptor_model, f"get_resource")(name) if descriptor_model.get_resource(name) else descriptor_model._find(name, (DrivePackageChild, DriveCatalog, DriveCatalogReference, DriveRemoteCatalog))
            if not resolved:
                raise typer.BadParameter(f'Entity selector "{name}" was not found.')
            
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
            property_path = property_name # exact match
            value = raw_value
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
        context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
        epilog=examples_epilog(
            "sharedrive add my-resource --path https://drive.google.com/file/d/123... --cache downloads/file.csv",
            "sharedrive add my-folder --catalog --accessURL https://drive.google.com/drive/folders/abc...",
        ),
    )
    def add(
        ctx: typer.Context,
        name: str = typer.Argument(
            ..., help="Resource name to store in the descriptor."
        ),
        catalog: bool = typer.Option(
            False, "--catalog", help="Treat as a catalog with accessURL."
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

        parsed = parse_set_args(list(ctx.args))
        
        try:
            resource = _add_resource_to_descriptor(
                descriptor=descriptor_path,
                name=name,
                catalog=catalog,
                create_if_missing=not explicit_descriptor,
                **parsed
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

__all__ = ["register_descriptor_commands"]
