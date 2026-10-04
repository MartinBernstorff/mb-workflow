#!/usr/bin/env bash
# Lints the app's src with Fixit and compares the violations to the app's hemolint baseline.
# Extra arguments go to `hemolint check`, e.g. --prune or --baseline.
#
# Fixit exits 1 on any violation, so its exit code can't fail the run. It only warns when a rule
# fails to load, which would otherwise look like zero violations and empty the baseline on --prune.
set -euo pipefail

# Not `git rev-parse --show-toplevel`: the pre-commit hook sets GIT_DIR, which makes git report the
# current directory as the top level.
root="$(cd "$(dirname "$0")/.." && pwd)"
warnings="$(mktemp)"
trap 'rm -f "$warnings"' EXIT

fixit_code=0
violations="$(uv run --project "$root/packages/lint-rules" fixit lint src 2>"$warnings")" || fixit_code=$?
cat "$warnings" >&2

if ((fixit_code & 2)) || grep -q "Failed to load rules" "$warnings"; then
    echo "Fixit failed; the baseline was not compared." >&2
    exit 2
fi

printf '%s\n' "$violations" | uv run --project "$root/apps/hemolint" hemolint check --format fixit "$@"
