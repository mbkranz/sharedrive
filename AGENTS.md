# AGENTS.md

Instructions in this file apply to the full repository.

## Goal

Build and evolve reusable shared-drive adapters (SharePoint, Google Drive, S3-oriented retrieval workflows).

Goal is to create a quick and efficient system like git and uv both for quick development (so retrieve one or a group of files) with CLI, for more complex workflows (ETL etc)  that will use python API, and emphasis on standardized metadata to build a catalog of resources that can be easily searched and retrieved by users and agents. Currently, the DataPackage standard is followed for metdata (https://github.com/frictionlessdata/datapackage/tree/main/profiles) but this may evolve as we iterate on the metadata structure and retrieval patterns (for example: see Issue #4 for OpenMetadata standard)

## Fast context

- Read the code! The best way to understand the current state and patterns is to read through the existing code, especially the clients, auth strategies, and CLI.

## Preferred commands


- Install (CLI tool): `uv tool install .`
- Run scripts: `uv run python <script-path>`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`
- Tests: `uv run pytest`
- Safe retrieval dry-run for CLI: `uvx sharedrive <subcommands and options> --dry-run`

## Development guardrails

- Do not hard-code secrets or tenant-specific values.
- Keep `.env-sample` synchronized with variables read in code.
- Keep changes narrowly scoped; avoid broad refactors unless requested.

## When updating adapters

- Give warnings and ask for approval before breaking backward compatibility.
- Raise explicit exceptions with actionable error messages.
- Keep network calls and auth behavior obvious and testable.
- Add or update tests when behavior changes (especially URL parsing and download/export logic).


## Documentation rule

- Document any non-obvious behavior in docstrings and `README.md`.
- Update docs if any changes with: `uv run update_docs_markdown.py`