# hemolint

Keeps new lint violations out while existing ones are fixed over time. A rewrite of [snaplint](https://github.com/GENWAY-AI/snaplint).

Record every current violation in the baseline:

```sh
fixit lint | uv run hemolint check --format fixit --baseline
```

Fail when the baseline has drifted from the current violations:

```sh
fixit lint | uv run hemolint check --format fixit
```

It exits 1 on new violations, which it prints as the linter's own lines, and on fixed violations still in the baseline. It exits 0 when there is no drift.

Remove fixed violations from the baseline instead of failing on them:

```sh
fixit lint | uv run hemolint check --format fixit --prune
```

It still exits 1 on new violations, but never adds them to the baseline, so a pre-commit hook can run it to shrink the baseline as violations are fixed. The baseline directories of deleted source files are removed with their violations.

Ruff's JSON output works in all three modes. Its absolute paths are recorded relative to the current directory:

```sh
ruff check --output-format json | uv run hemolint check --format ruff-json
```

Tach's JSON output works too. Run it from the tach project root, since tach's paths are relative to it:

```sh
tach check --output json | uv run hemolint check --format tach
```

Each diagnostic kind, e.g. `UndeclaredDependency`, is a rule. Diagnostics for the whole project rather than a line are kept under `_global/`, fingerprinted by their details. Configuration diagnostics, skipped files and tach errors such as a circular dependency exit 2, since tach could not check everything.

The baseline lives in `.hemolint/`, one JSON file per source file per rule, at `<source path>/<linter>-<rule>.json`.

All checks run through moon from the repository root: `moon ci`.
