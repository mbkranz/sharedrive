# AGENTS.md

Instructions in this file apply to the full repository.

## Goal

Build and evolve reusable shared-drive adapters (SharePoint, Google Drive, S3-oriented retrieval workflows).

Goal is to create a quick and efficient system like git and uv both for quick development (so retrieve one or a group of files) with CLI, for more complex workflows (ETL etc)  that will use python API, and emphasis on standardized metadata to build a catalog of resources that can be easily searched and retrieved by users and agents. Currently, the DataPackage standard is followed for metdata (https://github.com/frictionlessdata/datapackage/tree/main/profiles) but this may evolve as we iterate on the metadata structure and retrieval patterns (for example: see Issue #4 for OpenMetadata standard)

## Fast context

- Read the code! The best way to understand the current state and patterns is to read through the existing code, especially the clients, auth strategies, and CLI.

- Also equally important! Study the REST APIs for the clients and authorizations:
    - Sharepoint: 
        - /fetch https://learn.microsoft.com/en-us/graph/api/resources/onedrive?view=graph-rest-1.0
    - Google drive: 
        - /fetch https://developers.google.com/workspace/drive/api/reference/rest/v3
        - /fetch https://developers.google.com/workspace/drive/api/reference/rest/v3/files
        - /fetch https://developers.google.com/workspace/drive/api/reference/rest/v3/drives


-  And equally important is to use metadata standards. Study these:
    - standard data package (/fetch https://github.com/frictionlessdata/datapackage/tree/main/profiles)
    - and see recipes for using (/fetch https://github.com/frictionlessdata/datapackage/tree/main/content/docs/recipes)
    - And OpenMetadata for drive services and where else applicable:
        - data assets and storage: /fetch https://github.com/open-metadata/OpenMetadataStandards/tree/main/docs/data-assets/storage
        - and see docs overall here: /fetch https://github.com/open-metadata/OpenMetadataStandards/tree/main/docs
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
- Keep changes narrowly scoped; avoid broad refactors unless requested BUT always notify when there is a better design or solution regardless of scope. 
- Always check and analyze the current codebase and the associated API documentation (for example, see Sharepoint and Google URLs in "Fast Context") for services when thinking about answers in terms of better solution 
- Don't be afraid to highlight any concerns with assumptions made in prompts.

## Current CLI contract

The current CLI model is intentional and should be preserved unless a breaking redesign is explicitly approved.

- `sharedrive checkout <descriptor>` activates the descriptor context.
- `sharedrive fetch <resource-name>` refreshes remote metadata into the descriptor for one explicit resource.
- `sharedrive download [descriptor] [--include ...]` downloads or materializes files locally.
- `sharedrive auth check [descriptor] [--include ...]` validates auth and defaults to the whole descriptor when `--include` is omitted.
- `sharedrive update [--descriptor PATH] [--resource NAME] [field flags...]` edits descriptor-root fields or exactly one resource.

The following removals are intentional and should not be casually reintroduced:

- `sync`
- `retrieve`
- `checkout resource`
- `checkout driveservice`
- `checkout show`
- `checkout clear`

## Command semantics guardrail

Prefer command meanings that stay consistent with common tools such as git, uv, and gh.

- `checkout` means selecting or activating descriptor context, not managing hidden sub-selections.
- `fetch` means metadata retrieval into the descriptor, not file download.
- File retrieval or materialization should use `download`.
- Mutating descriptor operations should require explicit targets unless there is a strong reason not to.
- Avoid hidden persisted selection state beyond the active descriptor.

## Update command rules

- `update` follows a GitHub CLI style: context plus field flags.
- Without `--resource`, update descriptor-root properties.
- With `--resource`, resolve exactly one resource by exact match.
- Do not add glob-based or implicit bulk edits unless explicitly requested and designed.
- Preserve `--dry-run` for edit previews.

## Compatibility surface

Backward compatibility includes both CLI behavior and Python import paths.

- Before removing or renaming modules, audit tests and public imports.
- Keep compatibility shims when moving public auth helpers or other public APIs.
- Example: `sharedrive.auth.sharepoint` should remain importable as a compatibility shim even if the implementation lives in Microsoft auth.
- If a breaking change is approved, update tests, docs, and public exports in the same change.

## When updating adapters

- Give warnings and ask for approval before breaking backward compatibility.
- Raise explicit exceptions with actionable error messages.
- Keep network calls and auth behavior obvious and testable.
- Add or update tests when behavior changes (especially URL parsing and download/export logic).

## Validation after CLI or auth refactors

After changing command semantics, public action modules, auth module layout, or descriptor-edit behavior:

1. Run focused tests for affected areas first.
2. Run the full suite with `uv run pytest`.
3. Run lint with `uv run ruff check .`.
4. Regenerate docs with `uv run python scripts/update_docs_markdown.py`.
5. Verify README examples and CLI help still match the implemented command model.

## Defaults and explicitness

Use these defaults consistently unless a change is explicitly approved:

- `download` and `auth check` may default to the whole descriptor.
- Metadata `fetch` should stay explicit per resource.
- Resource-targeted `update` should resolve one exact resource, not many.


## Documentation rule

- Document any non-obvious behavior in docstrings and `README.md`.
- Update docs if any changes with: `uv run update_docs_markdown.py`
- the __all__ variable is used to explicitly declare public API for each module. When adding new functions or classes that are intended to be part of the public API, make sure to include them in the __all__ list at the end of the module. This helps with clarity and maintainability of the codebase.
- Document design choices through doc strings. For example, the logic and source (like url and name of standard(s) or existing software like uv/git etc that provided either motivation of why property names were used)