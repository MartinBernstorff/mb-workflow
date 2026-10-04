# hemolint

Keeps new lint violations out while existing ones are fixed over time. A rewrite of [snaplint](https://github.com/GENWAY-AI/snaplint).

Record every current violation in the baseline:

```sh
fixit lint | uv run hemolint check --format fixit --baseline
```

The baseline lives in `.hemolint/`, one JSON file per source file per rule, at `<source path>/<linter>-<rule>.json`.

All checks run through moon from the repository root: `moon ci`.
