# mb-assertions

A type-checked assertion builder. The expected value's type is fixed by the actual value's type, so a type checker rejects `Assert.that(1).matches("a")`.

```python
from assertions import Assert

Assert.that(order.total).matches(expected_total)
Assert.that(order.lines).container_exactly(expected_lines)
Assert.that(order).matches_populated_exactly(Order.model_construct(status=status))
```

## Install

It is not published to PyPI and has no tags. Install it from the git URL and pin a commit SHA:

```sh
uv add "mb-assertions @ git+https://github.com/MartinBernstorff/mb-workflow@<sha>#subdirectory=apps/mb-assertions"
```

Requires Python 3.12 or newer.

All checks run through moon from the repository root: `moon run mb-assertions:full`.
