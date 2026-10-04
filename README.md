# mb-workflow

CLIs for workflow automation. Each lives in its own directory under `apps/`:

* [`apps/mb-workflow`](apps/mb-workflow) — the `mw` CLI.

Custom lint rules live in [`packages/lint-rules`](packages/lint-rules) and run in every app through Fixit (`moon run :fixit`). The root `fixit.toml` enables them; an app extends it with its own `fixit.toml`.

All checks run through moon: `moon ci`.
