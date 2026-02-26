# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "sharedrive",
#   "boto3"
# ]
# [tool.uv.sources]
# sharedrive = { path = "../../sharedrive", editable = true }
# ///

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sharedrive.retrieve import resolve_default_descriptor, retrieve_from_descriptor


def _parse_include(values: list[str] | None) -> str | list[str]:
    if not values:
        return "all"
    tokens: list[str] = []
    for value in values:
        tokens.extend(part.strip() for part in value.split(","))
    normalized = [token for token in tokens if token]
    if not normalized or "all" in {token.lower() for token in normalized}:
        return "all"
    return normalized


def run(
    dry_run: bool,
    descriptor: Path | str,
    include_types: str | list[str] = "all",
    output_dir: Path = Path("resources"),
) -> int:
    summary = retrieve_from_descriptor(
        descriptor=descriptor,
        include=include_types,
        output_dir=output_dir,
        dry_run=dry_run,
        log=print,
    )
    return summary.failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Retrieve resources specified in a descriptor file"
    )
    parser.add_argument(
        "--descriptor",
        type=Path,
        default=resolve_default_descriptor(),
        help="Path to the resource descriptor JSON or YAML file",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=None,
        help=(
            "Adapter types and/or resource names to include. "
            "Repeat or comma-separate values; default is all."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("resources"),
        help="Directory to save retrieved resources",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without performing retrieval",
    )
    args = parser.parse_args()

    failures = run(
        dry_run=args.dry_run,
        descriptor=args.descriptor,
        include_types=_parse_include(args.include),
        output_dir=args.output_dir,
    )
    if failures:
        raise SystemExit(1)
