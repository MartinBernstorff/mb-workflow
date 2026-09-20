# mb-workflow

Workflow automation CLI.

```sh
uv sync
uv run lefthook install
uv run mb-workflow review-workspaces
```

All checks run through moon: `moon ci`.

## The workflow state chart

![The workflow state chart](docs/flow.svg)

`moon run diagram` regenerates the picture above, and lefthook runs it on every commit, so it tracks `flow.py` rather than drifting from it. Rendering needs Graphviz on PATH. `mw flow diagram` prints the same chart as a mermaid state diagram instead.
