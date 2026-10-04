# mb-workflow

CLIs and libraries for workflow automation. Each lives in its own directory under `apps/`:

* [`apps/mb-workflow`](apps/mb-workflow) — the `mw` CLI.
* [`apps/mb-assertions`](apps/mb-assertions) — the `Assert.that` type-checked assertion builder.
* [`apps/hemolint`](apps/hemolint) — keeps new lint violations out while existing ones are fixed.

Custom lint rules live in [`packages/lint-rules`](packages/lint-rules) and run in every app through Fixit (`moon run :fixit`). The root `fixit.toml` enables them; an app or package extends it with its own `fixit.toml`. Existing violations are kept in each app's hemolint baseline, `.hemolint/`; `moon run <app>:fixit-baseline` records it again.

All checks run through moon: `moon ci`.
