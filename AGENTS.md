# AGENTS.md

Instructions in this file apply to the full repository.

## Goal

Build and evolve reusable shared-drive adapters (SharePoint, Google Drive, S3-oriented retrieval workflows) with minimal breakage for existing `pmd_utils`-style consumers.

## Fast context

- Main adapters live in `sharedrive/sharepoint.py` and `sharedrive/googledrive.py`.
- Retrieval workflow is in `scripts/retrieve_resources.py`.
- Manual adapter smoke checks are in `scripts/dev_adapters.py`.
- Current script lineage intentionally mirrors:
  - `allofus/ppsc-participant-tracks/scripts/retrieve_resources.py`
  - `allofus/ppsc-pmd-utils/scripts/dev/dev_adapters.py`

## Preferred commands

- Install (dev): `uv sync --extra dev --extra test`
- Install (docs): `uv sync --extra docs`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`
- Tests: `uv run pytest`
- Safe retrieval dry-run: `uv run python scripts/retrieve_resources.py --dry-run`

## Development guardrails

- Preserve descriptor compatibility in `scripts/retrieve_resources.py`:
  - top-level `resources` array
  - `sources[].path` and legacy `source`
  - `x-adapter` override support
- Treat remote write paths as high risk:
  - `GoogleDriveClient.update_file`
  - SharePoint upload/update methods
- Do not hard-code secrets or tenant-specific values.
- Keep `.env-sample` synchronized with variables read in code.
- Keep changes narrowly scoped; avoid broad refactors unless requested.

## When updating adapters

- Prefer backward-compatible method signatures.
- Raise explicit exceptions with actionable error messages.
- Keep network calls and auth behavior obvious and testable.
- Add or update tests when behavior changes (especially URL parsing and download/export logic).

## Documentation rule

If behavior changes in adapters or retrieval scripts, update `README.md` in the same change.
