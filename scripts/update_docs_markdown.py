from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import typer.rich_utils as rich_utils
from sharedrive.cli import app
from typer.testing import CliRunner

ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
CLI_WIDTH = 200
RUNNER = CliRunner()

CLI_COMMANDS: list[tuple[str, list[str]]] = [
    ("sharedrive --help", ["--help"]),
    ("sharedrive retrieve --help", ["retrieve", "--help"]),
    ("sharedrive gdrive --help", ["gdrive", "--help"]),
    ("sharedrive gdrive list --help", ["gdrive", "list", "--help"]),
    ("sharedrive gdrive get --help", ["gdrive", "get", "--help"]),
    ("sharedrive gdrive download --help", ["gdrive", "download", "--help"]),
    ("sharedrive gdrive export --help", ["gdrive", "export", "--help"]),
    ("sharedrive sharepoint --help", ["sharepoint", "--help"]),
    ("sharedrive sharepoint get --help", ["sharepoint", "get", "--help"]),
    ("sharedrive sharepoint download --help", ["sharepoint", "download", "--help"]),
    ("sharedrive s3 --help", ["s3", "--help"]),
    ("sharedrive s3 cp --help", ["s3", "cp", "--help"]),
    ("sharedrive s3 ls --help", ["s3", "ls", "--help"]),
    ("sharedrive s3 cat --help", ["s3", "cat", "--help"]),
]

API_SURFACE = [
    {
        "module": "sharedrive.retrieve",
        "path": ROOT / "sharedrive" / "retrieve.py",
        "functions": [
            "resolve_default_descriptor",
            "retrieve_from_descriptor",
            "retrieve_resources",
        ],
        "classes": {"RetrieveSummary": ["ok"]},
    },
    {
        "module": "sharedrive.azure",
        "path": ROOT / "sharedrive" / "azure.py",
        "functions": [],
        "classes": {"SpoConfig": ["to_client"]},
    },
    {
        "module": "sharedrive.aws",
        "path": ROOT / "sharedrive" / "aws.py",
        "functions": ["parse_s3_source_url", "download_s3_url"],
        "classes": {},
    },
    {
        "module": "sharedrive.googledrive",
        "path": ROOT / "sharedrive" / "googledrive.py",
        "functions": [],
        "classes": {
            "GoogleDriveClient": [
                "list_files",
                "get_file",
                "download_file",
                "download_from_weburl",
                "export_file",
                "export_from_weburl",
                "update_file",
                "update_from_weburl",
                "create_file",
                "create_folder",
            ]
        },
    },
    {
        "module": "sharedrive.sharepoint",
        "path": ROOT / "sharedrive" / "sharepoint.py",
        "functions": [],
        "classes": {
            "SharepointClient": [
                "get_from_weburl",
                "download_from_weburl",
                "get_file",
                "get_folder",
                "get_folder_contents",
                "upload_new_content",
                "update_content",
            ]
        },
    },
]


def _normalize_help_text(text: str) -> str:
    normalized = ANSI_PATTERN.sub("", text).replace("\r\n", "\n")
    normalized = normalized.encode("ascii", "ignore").decode()
    lines = [line.rstrip() for line in normalized.splitlines()]
    return "\n".join(lines).strip() + "\n"


def _run_help(args: list[str]) -> str:
    app.rich_markup_mode = None
    rich_utils.FORCE_TERMINAL = False
    rich_utils.COLOR_SYSTEM = None
    rich_utils.MAX_WIDTH = CLI_WIDTH
    result = RUNNER.invoke(app, args, prog_name="sharedrive", color=False)
    if result.exit_code != 0:
        raise RuntimeError(f"Failed: {' '.join(['sharedrive', *args])}\n{result.stdout}")
    return _normalize_help_text(result.stdout)


def _render_cli_markdown() -> str:
    lines = ["# CLI Reference", ""]
    lines.append("Auto-generated from live `sharedrive --help` output.")
    lines.append("")
    for title, args in CLI_COMMANDS:
        lines.append(f"## `{title}`")
        lines.append("")
        lines.append("```text")
        lines.append(_run_help(args).rstrip())
        lines.append("```")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _parse_module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _doc_first_line(node: ast.AST) -> str:
    doc = ast.get_docstring(node)
    if not doc:
        return ""
    return doc.strip().splitlines()[0].strip()


def _ann_to_str(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _format_func_signature(node: ast.FunctionDef) -> str:
    args = node.args
    parts: list[str] = []

    pos_args = args.posonlyargs + args.args
    defaults = args.defaults
    default_start = len(pos_args) - len(defaults)

    for idx, arg in enumerate(pos_args):
        piece = arg.arg
        ann = _ann_to_str(arg.annotation)
        if ann:
            piece += f": {ann}"
        if idx >= default_start and default_start >= 0:
            piece += f" = {_ann_to_str(defaults[idx - default_start])}"
        parts.append(piece)

    if args.posonlyargs:
        parts.insert(len(args.posonlyargs), "/")

    if args.vararg:
        var_piece = f"*{args.vararg.arg}"
        ann = _ann_to_str(args.vararg.annotation)
        if ann:
            var_piece += f": {ann}"
        parts.append(var_piece)
    elif args.kwonlyargs:
        parts.append("*")

    for kwarg, kw_default in zip(args.kwonlyargs, args.kw_defaults):
        piece = kwarg.arg
        ann = _ann_to_str(kwarg.annotation)
        if ann:
            piece += f": {ann}"
        if kw_default is not None:
            piece += f" = {_ann_to_str(kw_default)}"
        parts.append(piece)

    if args.kwarg:
        kw_piece = f"**{args.kwarg.arg}"
        ann = _ann_to_str(args.kwarg.annotation)
        if ann:
            kw_piece += f": {ann}"
        parts.append(kw_piece)

    sig = f"def {node.name}({', '.join(parts)})"
    ret = _ann_to_str(node.returns)
    if ret:
        sig += f" -> {ret}"
    return sig


def _class_fields(node: ast.ClassDef) -> list[str]:
    fields: list[str] = []
    for item in node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            ann = _ann_to_str(item.annotation)
            if ann:
                fields.append(f"{item.target.id}: {ann}")
    return fields


def _render_api_markdown() -> str:
    lines = ["# Python API", ""]
    lines.append("Auto-generated from source signatures and docstrings.")
    lines.append("")

    for module_spec in API_SURFACE:
        module_name = module_spec["module"]
        module_ast = _parse_module(module_spec["path"])
        top_functions = {
            item.name: item for item in module_ast.body if isinstance(item, ast.FunctionDef)
        }
        top_classes = {
            item.name: item for item in module_ast.body if isinstance(item, ast.ClassDef)
        }

        lines.append(f"## `{module_name}`")
        lines.append("")

        function_names: list[str] = module_spec["functions"]
        if function_names:
            lines.append("### Functions")
            lines.append("")
            for name in function_names:
                node = top_functions.get(name)
                if node is None:
                    continue
                lines.append(f"- `{_format_func_signature(node)}`")
                doc = _doc_first_line(node)
                if doc:
                    lines.append(f"  - {doc}")
            lines.append("")

        class_specs: dict[str, list[str]] = module_spec["classes"]
        if class_specs:
            lines.append("### Classes")
            lines.append("")
            for class_name, methods in class_specs.items():
                class_node = top_classes.get(class_name)
                if class_node is None:
                    continue
                lines.append(f"#### `{class_name}`")
                class_doc = _doc_first_line(class_node)
                if class_doc:
                    lines.append(f"- {class_doc}")
                fields = _class_fields(class_node)
                if fields:
                    lines.append("- Fields:")
                    for field in fields:
                        lines.append(f"  - `{field}`")
                method_nodes = {
                    item.name: item
                    for item in class_node.body
                    if isinstance(item, ast.FunctionDef)
                }
                if methods:
                    lines.append("- Methods:")
                    for method_name in methods:
                        method_node = method_nodes.get(method_name)
                        if method_node is None:
                            continue
                        lines.append(f"  - `{_format_func_signature(method_node)}`")
                        method_doc = _doc_first_line(method_node)
                        if method_doc:
                            lines.append(f"    - {method_doc}")
                lines.append("")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    docs_dir = ROOT / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "cli.md").write_text(_render_cli_markdown(), encoding="utf-8")
    (docs_dir / "api.md").write_text(_render_api_markdown(), encoding="utf-8")
    print(f"Updated {docs_dir / 'cli.md'}")
    print(f"Updated {docs_dir / 'api.md'}")


if __name__ == "__main__":
    main()
