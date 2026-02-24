# CLAUDE.md

Use this file as the Claude Code entrypoint for repository-specific workflow.

## Start here

1. Read `AGENTS.md` first.
2. Follow its commands, guardrails, and compatibility expectations.

## Repo focus

- Adapters:
  - `src/sharedrive/sharepoint.py`
  - `src/sharedrive/googledrive.py`
- Descriptor retrieval script:
  - `scripts/retrieve_resources.py`
- Manual integration script:
  - `scripts/dev_adapters.py`

## Working style expectations

- Run fast checks before finishing:
  - `uv run ruff check .`
  - `uv run pytest` (if tests exist for changed area)
- Prefer dry-runs for retrieval operations:
  - `python scripts/retrieve_resources.py --dry-run`
- Flag any operation that will mutate remote files.
- Keep README and `.env-sample` aligned with code changes.
