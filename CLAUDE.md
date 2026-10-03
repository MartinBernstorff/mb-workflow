# CLAUDE.md

## Running tasks

Always go through moon, never the underlying tool. Moon runs the task's dependencies and caches aggressively — `moon run test`, not `pytest`.

| Task | Purpose |
| --- | --- |
| `moon run test` | pytest over `src/` |
| `moon run types` | pyrefly type check |
| `moon run modularity` | tach module-boundary check |
| `moon run noprim` | fails on primitives in signatures |
| `moon run lint` | ruff lint |
| `moon run lint-fix` | ruff lint with `--fix` |
| `moon run format` | ruff format check |
| `moon run format-fix` | ruff format, writing changes |
| `moon run actionlint` | lint GitHub Actions workflows |
| `moon run phase-1` | fast checks with auto-fix; what the pre-commit hook runs |
| `moon run full` | every check, including tests, without auto-fix |

`moon ci` runs everything.

## Python conventions

Follow @CODE-CONVENTIONS.md. In addition:

**Tool settings live in each tool's own config file** — `pytest.toml`, `ruff.toml`, `pyrefly.toml`, `tach.toml`, `noprim.toml`. Never in `pyproject.toml`.
