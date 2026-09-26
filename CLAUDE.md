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

`moon ci` runs everything.

## Python conventions

**No primitives.** Never use a primitive as a parameter type, field type, or return type. Wrap it in a Pydantic `RootModel`. Enforced by `noprim`.

**Every domain model gets `.fake()`** — a staticmethod returning a fully-populated default instance for tests. For an aggregate, build its defaults from its members' `.fake()`:

```python
class PersonName(RootModel[str]):
    @staticmethod
    def fake() -> PersonName:
        return PersonName("Ada")


class Greeting(RootModel[str]):
    @staticmethod
    def fake() -> Greeting:
        return Greeting(f"Hello, {PersonName.fake().root}!")
```

**No `tests/` folder.** Tests sit beside the code they test: `test_<module>.py` in the same directory.

**Never maintain `__all__`.** Use direct imports.

**Avoid constants.** When you reach for one, first ask whether it belongs as a parameter of the caller.

**Do not use `iterpy`.** If it appears as a direct dependency, propose a PR removing it.

**Default to no comments.** If code needs a comment to be understood, fix the code. When one is genuinely required, write a single line on *why* (constraint, invariant, bug) — never *what*.

**Tool settings live in each tool's own config file** — `pytest.toml`, `ruff.toml`, `pyrefly.toml`, `tach.toml`, `noprim.toml`. Never in `pyproject.toml`.

## CLI

Built with Typer, entry point `mb_workflow.cli:app`. Every command must accept `--quiet`, which sets the log level.

The `a_presentation/cli/` package is the Typer boundary, with one file per command group, and is the one place excluded from `noprim`, because Typer can only bind primitives. Keep it free of logic: bind the primitive, wrap it in its domain type on the first line of the body, delegate. Anything with behaviour belongs in another module, where `noprim` still applies.

## Tickets

`MB-<n>` identifiers are Linear issues. Read them with `mw ticket view`; modify them with `linear-cli`.

```bash
uv run mw ticket view MB-19
linear-cli issues update MB-19 --state Implementing
```

The team's statuses are the workflow states (`Grilling`, `Speccing`, `Specced`, `Implementing`, `QA`, `Review`, `Merging`, `Merged`), not Linear's defaults.

## Credentials

`mw` reads its Linear keys from `~/.config/mb-workflow/projects/<owner>/<repo>.toml`, where `<owner>/<repo>` comes from the `origin` remote, so every worktree of a repository shares one file:

```toml
[linear]
api_key = "lin_api_…"                   # the workspace this repository's issues live in
integration_test_api_key = "lin_api_…"  # only for `moon run test-linear-live`
```

## Commits

Pre-commit validation runs via lefthook. Run `uv run lefthook install` once per clone; Conductor does this via `.conductor/settings.toml`.

Use conventional commits. Never add Claude as a co-author.
