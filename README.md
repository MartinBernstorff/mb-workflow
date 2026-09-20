# mb-workflow

Workflow automation CLI.

```sh
uv sync
uv run lefthook install
uv run mb-workflow review-workspaces
```

All checks run through moon: `moon ci`.

## The workflow state chart

`mw flow diagram` prints the development workflow as a mermaid state diagram. Pass `--output flow.png` to render an image instead; the extension picks the format, and Graphviz has to be on PATH.
