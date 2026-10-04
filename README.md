# mb-workflow

CLIs for workflow automation. Each lives in its own directory under `apps/`:

* [`apps/mb-workflow`](apps/mb-workflow) — the `mw` CLI.
* [`apps/hemolint`](apps/hemolint) — keeps new lint violations out while existing ones are fixed.

All checks run through moon: `moon ci`.
