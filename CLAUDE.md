# CLAUDE.md

## Running tasks

Always go through moon, never the underlying tool. Moon runs the task's dependencies and caches aggressively — `moon run :test`, not `pytest`.

Each app lives in `apps/`. There is no default project, so every task needs a scope: `moon run :test` runs it in every app, `moon run mb-workflow:test` in one.

| Task | Purpose |
| --- | --- |
| `test` | pytest in each app |
| `types` | pyrefly type check |
| `modularity` | tach module-boundary check |
| `noprim` | fails on primitives in signatures |
| `lint` | ruff lint |
| `lint-fix` | ruff lint with `--fix` |
| `format` | ruff format check |
| `format-fix` | ruff format, writing changes |
| `phase-1` | fast checks with auto-fix; the pre-commit hook runs `moon run :phase-1` |
| `full` | every check, including tests, without auto-fix |

mb-workflow also has `actionlint` (lints the GitHub Actions workflows), `diagram`, and the live tests.

`moon ci` runs everything.

## Python conventions

Follow @CODE-CONVENTIONS.md. In addition:

**Tool settings live in each tool's own config file** — `pytest.toml`, `ruff.toml`, `pyrefly.toml`, `tach.toml`, `noprim.toml`. Never in `pyproject.toml`.
